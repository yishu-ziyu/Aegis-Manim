from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib import error


DEFAULT_BASE_URL = "https://manim.yishuziyu.cn"
DEFAULT_PROVIDER = "trial-kimi-priority"
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}
ECONOMICS_MARKERS = (
    "供给",
    "需求",
    "均衡",
    "价格",
    "数量",
    "福利",
    "消费者",
    "生产者",
    "垄断",
    "外部性",
    "曲线",
    "成本",
    "收益",
)


@dataclass(frozen=True)
class VisionAcceptanceResult:
    index: int
    image: str
    ok: bool
    vision_http: int | None
    generate_http: int | None
    render_http: int | None
    status: str
    suggested_prompt_chars: int
    job_id: str | None
    video_url: str | None
    duration_seconds: float | None
    video_bytes: int | None
    frame_path: str | None
    latency_ms: int
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "image": self.image,
            "ok": self.ok,
            "visionHttp": self.vision_http,
            "generateHttp": self.generate_http,
            "renderHttp": self.render_http,
            "status": self.status,
            "suggestedPromptChars": self.suggested_prompt_chars,
            "jobId": self.job_id,
            "videoUrl": self.video_url,
            "durationSeconds": self.duration_seconds,
            "videoBytes": self.video_bytes,
            "framePath": self.frame_path,
            "latencyMs": self.latency_ms,
            "errorType": self.error_type,
            "errorMessage": self.error_message,
        }


def infer_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def has_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def contains_economics_marker(text: str) -> bool:
    return any(marker in text for marker in ECONOMICS_MARKERS)


def _append_text_value(text_parts: list[str], value: object) -> None:
    if isinstance(value, str):
        text_parts.append(value)
    elif isinstance(value, list):
        text_parts.extend(str(item) for item in value)
    elif isinstance(value, dict):
        text_parts.extend(str(item) for item in value.values())


def extract_vision_text(payload: dict[str, object]) -> str:
    text_parts: list[str] = []
    for key in (
        "recognizedContent",
        "visualizationPlan",
        "suggestedPrompt",
        "keyElements",
        "uncertainties",
    ):
        _append_text_value(text_parts, payload.get(key))

    analysis = payload.get("analysis")
    if isinstance(analysis, dict):
        for key in (
            "recognized_content",
            "recognizedContent",
            "visualization_plan",
            "visualizationPlan",
            "recommended_prompt",
            "recommendedPrompt",
            "key_elements",
            "keyElements",
            "uncertainties",
            "auditable_analysis",
            "auditableAnalysis",
        ):
            _append_text_value(text_parts, analysis.get(key))

    return "\n".join(text_parts)


def extract_suggested_prompt(payload: dict[str, object]) -> str:
    direct = payload.get("suggestedPrompt")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    analysis = payload.get("analysis")
    if isinstance(analysis, dict):
        for key in ("recommended_prompt", "recommendedPrompt", "visualization_plan", "visualizationPlan"):
            value = analysis.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def read_http_error_detail(exc: error.HTTPError) -> str:
    return exc.read().decode("utf-8", errors="replace")[:1200]


def vision_payload_is_usable(payload: dict[str, object]) -> tuple[bool, str]:
    if payload.get("ok") is not True:
        return False, "vision response ok is not true"
    text = extract_vision_text(payload)
    suggested_prompt = extract_suggested_prompt(payload)
    if not suggested_prompt.strip():
        return False, "suggestedPrompt is empty"
    if not has_chinese(text):
        return False, "vision response has no Chinese text"
    if not contains_economics_marker(text):
        return False, "vision response has no recognizable economics marker"
    return True, ""


def post_json(
    url: str,
    payload: dict[str, object],
    timeout: int,
    api_key: str = "",
    *,
    retries: int = 0,
    retry_backoff: float = 1.5,
) -> tuple[int, dict[str, object]]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    for attempt in range(max(0, retries) + 1):
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return int(resp.status), json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = read_http_error_detail(exc)
            setattr(exc, "aegis_detail", detail)
            if exc.code in RETRYABLE_HTTP_STATUS and attempt < retries:
                time.sleep(retry_backoff * (attempt + 1))
                continue
            raise
    raise RuntimeError("post_json retry loop exhausted unexpectedly")


def get_json(url: str, timeout: int) -> tuple[int, dict[str, object]]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return int(resp.status), json.loads(resp.read().decode("utf-8"))


def encode_image(path: Path) -> str:
    return f"data:{infer_mime(path)};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def download_video(video_url: str, output_path: Path, timeout: int) -> int:
    with urllib.request.urlopen(video_url, timeout=timeout) as resp:
        data = resp.read()
    output_path.write_bytes(data)
    return len(data)


def probe_duration(video_path: Path) -> float | None:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return round(float(proc.stdout.strip()), 3)
    except Exception:
        return None


def extract_frame(video_path: Path, frame_path: Path) -> str | None:
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "2.2",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(frame_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return str(frame_path)
    except Exception:
        return None


def run_one(
    *,
    base_url: str,
    provider: str,
    image_path: Path,
    index: int,
    output_dir: Path,
    request_timeout: int,
    render_timeout: int,
    poll_interval: int,
    poll_attempts: int,
    skip_render: bool,
    api_key: str = "",
    vision_retries: int = 0,
    vision_retry_backoff: float = 1.5,
    gateway_retries: int = 0,
    gateway_retry_backoff: float = 1.5,
) -> VisionAcceptanceResult:
    started = time.perf_counter()
    stage = "vision"
    vision_http: int | None = None
    generate_http: int | None = None
    render_http: int | None = None
    suggested_prompt = ""
    try:
        stage = "vision"
        vision_http, vision = post_json(
            f"{base_url}/api/vision/analyze",
            {
                "imageData": encode_image(image_path),
                "mimeType": infer_mime(image_path),
                "prompt": "请按中文经济学考研题进行识别，并给出适合 Manim 可视化的中文方向。",
            },
            request_timeout,
            api_key,
            retries=vision_retries,
            retry_backoff=vision_retry_backoff,
        )
        usable, reason = vision_payload_is_usable(vision)
        suggested_prompt = extract_suggested_prompt(vision)
        if not usable:
            raise RuntimeError(reason)
        if skip_render:
            return VisionAcceptanceResult(
                index=index,
                image=str(image_path),
                ok=True,
                vision_http=vision_http,
                generate_http=None,
                render_http=None,
                status="vision-done",
                suggested_prompt_chars=len(suggested_prompt),
                job_id=None,
                video_url=None,
                duration_seconds=None,
                video_bytes=None,
                frame_path=None,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )

        stage = "generate"
        generate_http, generated = post_json(
            f"{base_url}/api/generate",
            {"prompt": suggested_prompt, "provider": provider, "sceneName": "GeneratedScene"},
            request_timeout,
            retries=gateway_retries,
            retry_backoff=gateway_retry_backoff,
        )
        code = str(generated.get("code") or "")
        stage = "render"
        render_http, render = post_json(
            f"{base_url}/api/render",
            {"code": code, "scene_name": generated.get("sceneName") or "GeneratedScene"},
            render_timeout,
            retries=gateway_retries,
            retry_backoff=gateway_retry_backoff,
        )
        job_id = str(render.get("job_id") or render.get("jobId") or "")
        if not job_id:
            raise RuntimeError("render response did not include job_id")

        status_payload: dict[str, object] = {}
        status = "unknown"
        for _ in range(poll_attempts):
            stage = "poll"
            _, status_payload = get_json(f"{base_url}/api/render/status/{job_id}", render_timeout)
            status = str(status_payload.get("status") or status_payload.get("stage") or "unknown")
            if status in {"done", "failed", "error"}:
                break
            time.sleep(poll_interval)

        video_url = str(status_payload.get("video_url") or status_payload.get("videoUrl") or "")
        video_bytes: int | None = None
        duration_seconds: float | None = None
        frame_path: str | None = None
        if status == "done" and video_url:
            video_path = output_dir / f"{index:02d}-{job_id}.mp4"
            stage = "download"
            video_bytes = download_video(video_url, video_path, render_timeout)
            duration_seconds = probe_duration(video_path)
            frame_path = extract_frame(video_path, output_dir / f"{index:02d}-{job_id}.png")

        return VisionAcceptanceResult(
            index=index,
            image=str(image_path),
            ok=status == "done" and bool(video_url) and bool(video_bytes),
            vision_http=vision_http,
            generate_http=generate_http,
            render_http=render_http,
            status=status,
            suggested_prompt_chars=len(suggested_prompt),
            job_id=job_id,
            video_url=video_url or None,
            duration_seconds=duration_seconds,
            video_bytes=video_bytes,
            frame_path=frame_path,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
    except error.HTTPError as exc:
        detail = str(getattr(exc, "aegis_detail", "") or "")
        message = f"{exc}; response={detail[:800]}" if detail else str(exc)
        return VisionAcceptanceResult(
            index=index,
            image=str(image_path),
            ok=False,
            vision_http=vision_http if stage != "vision" else exc.code,
            generate_http=generate_http if stage != "generate" else exc.code,
            render_http=render_http if stage != "render" else exc.code,
            status=f"{stage}-http-error",
            suggested_prompt_chars=len(suggested_prompt),
            job_id=None,
            video_url=None,
            duration_seconds=None,
            video_bytes=None,
            frame_path=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            error_type="HTTPError",
            error_message=message,
        )
    except Exception as exc:
        return VisionAcceptanceResult(
            index=index,
            image=str(image_path),
            ok=False,
            vision_http=vision_http,
            generate_http=generate_http,
            render_http=render_http,
            status=f"{stage}-error",
            suggested_prompt_chars=len(suggested_prompt),
            job_id=None,
            video_url=None,
            duration_seconds=None,
            video_bytes=None,
            frame_path=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 3-5 Chinese economics image understanding + Manim rendering acceptance cases."
    )
    parser.add_argument("images", nargs="+", type=Path, help="3-5 Chinese economics image files.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/aegis-vision-economics-acceptance"))
    parser.add_argument("--request-timeout", type=int, default=90)
    parser.add_argument("--render-timeout", type=int, default=90)
    parser.add_argument("--poll-interval", type=int, default=6)
    parser.add_argument("--poll-attempts", type=int, default=45)
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument(
        "--api-key",
        default=os.getenv("VISION_BACKEND_API_KEY", os.getenv("AEGIS_VISION_BACKEND_API_KEY", "")),
        help="Optional X-API-Key for the vision endpoint.",
    )
    parser.add_argument("--skip-render", action="store_true", help="Only verify /api/vision/analyze.")
    parser.add_argument("--vision-retries", type=int, default=2)
    parser.add_argument("--vision-retry-backoff", type=float, default=2.0)
    parser.add_argument("--gateway-retries", type=int, default=2)
    parser.add_argument("--gateway-retry-backoff", type=float, default=3.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_paths = [path.expanduser().resolve() for path in args.images]
    if not 3 <= len(image_paths) <= 5:
        print(json.dumps({"ok": False, "error": "provide 3 to 5 image files"}, ensure_ascii=False))
        return 2
    missing = [str(path) for path in image_paths if not path.is_file()]
    if missing:
        print(json.dumps({"ok": False, "error": "image files not found", "missing": missing}, ensure_ascii=False))
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = args.jsonl.open("w", encoding="utf-8") if args.jsonl else None
    results: list[VisionAcceptanceResult] = []
    try:
        for index, image_path in enumerate(image_paths, start=1):
            result = run_one(
                base_url=args.base_url.rstrip("/"),
                provider=args.provider,
                image_path=image_path,
                index=index,
                output_dir=args.output_dir,
                request_timeout=args.request_timeout,
                render_timeout=args.render_timeout,
                poll_interval=args.poll_interval,
                poll_attempts=args.poll_attempts,
                skip_render=args.skip_render,
                api_key=args.api_key.strip(),
                vision_retries=args.vision_retries,
                vision_retry_backoff=args.vision_retry_backoff,
                gateway_retries=args.gateway_retries,
                gateway_retry_backoff=args.gateway_retry_backoff,
            )
            results.append(result)
            line = json.dumps(result.to_dict(), ensure_ascii=False)
            print(line, flush=True)
            if jsonl_file:
                jsonl_file.write(line + "\n")
                jsonl_file.flush()
    finally:
        if jsonl_file:
            jsonl_file.close()

    passed = sum(1 for result in results if result.ok)
    print(json.dumps({"summary": {"passed": passed, "total": len(results)}}, ensure_ascii=False, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
