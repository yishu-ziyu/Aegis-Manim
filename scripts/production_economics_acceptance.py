from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib import error


DEFAULT_BASE_URL = "https://manim.yishuziyu.cn"
DEFAULT_PROVIDER = "trial-kimi-priority"
DEFAULT_PROMPTS = (
    "考研经济学题：用中文动画解释垄断厂商实行二部定价时的福利变化。假设需求曲线向下倾斜、边际成本为常数。请比较普通线性垄断定价与二部定价：说明为什么二部定价会把单价降到边际成本，并标出消费者剩余、固定入场费、厂商利润和效率产量。",
    "考研经济学题：用中文动画解释从量税如何形成税收楔子。请画出需求曲线、供给曲线、税前均衡、买方支付价格、卖方得到价格、税收收入和无谓损失，并说明交易量为什么下降。",
    "考研经济学题：用中文动画解释完全竞争市场中的消费者剩余和生产者剩余。请用供需图展示均衡价格、均衡数量、消费者剩余三角形、生产者剩余三角形，并说明总剩余最大化。",
    "考研经济学题：用中文动画解释价格上限低于均衡价格时的福利变化。请标出短缺、消费者剩余变化、生产者剩余损失、无谓损失，并说明为什么有效交易量减少。",
    "考研经济学题：用中文动画解释正外部性导致的市场失灵。请比较私人边际收益和社会边际收益，标出市场产量、社会最优产量、补贴方向和无谓损失。",
)


@dataclass(frozen=True)
class AcceptanceResult:
    index: int
    prompt_title: str
    ok: bool
    generate_http: int | None
    render_http: int | None
    status: str
    model: str | None
    endpoint: str | None
    job_id: str | None
    video_url: str | None
    code_chars: int
    play_count: int
    duration_seconds: float | None
    video_bytes: int | None
    frame_path: str | None
    latency_ms: int
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "promptTitle": self.prompt_title,
            "ok": self.ok,
            "generateHttp": self.generate_http,
            "renderHttp": self.render_http,
            "status": self.status,
            "model": self.model,
            "endpoint": self.endpoint,
            "jobId": self.job_id,
            "videoUrl": self.video_url,
            "codeChars": self.code_chars,
            "playCount": self.play_count,
            "durationSeconds": self.duration_seconds,
            "videoBytes": self.video_bytes,
            "framePath": self.frame_path,
            "latencyMs": self.latency_ms,
            "errorType": self.error_type,
            "errorMessage": self.error_message,
        }


def prompt_title(prompt: str) -> str:
    text = prompt.removeprefix("考研经济学题：")
    return text.split("。", 1)[0][:28]


def post_json(url: str, payload: dict[str, object], timeout: int) -> tuple[int, dict[str, object]]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout: int) -> tuple[int, dict[str, object]]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return int(resp.status), json.loads(resp.read().decode("utf-8"))


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
    prompt: str,
    index: int,
    output_dir: Path,
    generate_timeout: int,
    render_timeout: int,
    poll_interval: int,
    poll_attempts: int,
) -> AcceptanceResult:
    started = time.perf_counter()
    title = prompt_title(prompt)
    try:
        generate_http, generated = post_json(
            f"{base_url}/api/generate",
            {"prompt": prompt, "provider": provider, "sceneName": "GeneratedScene"},
            generate_timeout,
        )
        code = str(generated.get("code") or "")
        render_http, render = post_json(
            f"{base_url}/api/render",
            {"code": code, "scene_name": generated.get("sceneName") or "GeneratedScene"},
            render_timeout,
        )
        job_id = str(render.get("job_id") or render.get("jobId") or "")
        if not job_id:
            raise RuntimeError("render response did not include job_id")

        status_payload: dict[str, object] = {}
        status = "unknown"
        for _ in range(poll_attempts):
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
            video_bytes = download_video(video_url, video_path, render_timeout)
            duration_seconds = probe_duration(video_path)
            frame_path = extract_frame(video_path, output_dir / f"{index:02d}-{job_id}.png")

        latency_ms = round((time.perf_counter() - started) * 1000)
        return AcceptanceResult(
            index=index,
            prompt_title=title,
            ok=status == "done" and bool(video_url) and bool(video_bytes),
            generate_http=generate_http,
            render_http=render_http,
            status=status,
            model=str(generated.get("model") or ""),
            endpoint=str(generated.get("endpoint") or ""),
            job_id=job_id,
            video_url=video_url or None,
            code_chars=len(code),
            play_count=code.count("self.play("),
            duration_seconds=duration_seconds,
            video_bytes=video_bytes,
            frame_path=frame_path,
            latency_ms=latency_ms,
        )
    except error.HTTPError as exc:
        return AcceptanceResult(
            index=index,
            prompt_title=title,
            ok=False,
            generate_http=exc.code,
            render_http=None,
            status="http-error",
            model=None,
            endpoint=None,
            job_id=None,
            video_url=None,
            code_chars=0,
            play_count=0,
            duration_seconds=None,
            video_bytes=None,
            frame_path=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            error_type="HTTPError",
            error_message=str(exc),
        )
    except Exception as exc:
        return AcceptanceResult(
            index=index,
            prompt_title=title,
            ok=False,
            generate_http=None,
            render_http=None,
            status="error",
            model=None,
            endpoint=None,
            job_id=None,
            video_url=None,
            code_chars=0,
            play_count=0,
            duration_seconds=None,
            video_bytes=None,
            frame_path=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 3-5 public Chinese economics generation/render acceptance cases."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--limit", type=int, default=3, choices=range(3, 6))
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/aegis-economics-acceptance"))
    parser.add_argument("--generate-timeout", type=int, default=90)
    parser.add_argument("--render-timeout", type=int, default=90)
    parser.add_argument("--poll-interval", type=int, default=6)
    parser.add_argument("--poll-attempts", type=int, default=45)
    parser.add_argument("--jsonl", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = args.jsonl.open("w", encoding="utf-8") if args.jsonl else None
    results: list[AcceptanceResult] = []
    try:
        for index, prompt in enumerate(DEFAULT_PROMPTS[: args.limit], start=1):
            result = run_one(
                base_url=args.base_url.rstrip("/"),
                provider=args.provider,
                prompt=prompt,
                index=index,
                output_dir=args.output_dir,
                generate_timeout=args.generate_timeout,
                render_timeout=args.render_timeout,
                poll_interval=args.poll_interval,
                poll_attempts=args.poll_attempts,
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
