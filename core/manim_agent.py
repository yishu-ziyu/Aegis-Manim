from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib import error, request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = PROJECT_ROOT / "prompts" / "system_prompt.md"
DEFAULT_ZHIPU_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-5"
LATEX_AVAILABLE = bool(shutil.which("latex")) and bool(shutil.which("dvisvgm"))
PLACEHOLDER_KEYS = {
    "your_api_key_here",
    "your-api-key-here",
    "<your_api_key>",
    "changeme",
}


def read_file(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def generate_simulation_prompt(system_prompt: str, user_input: str) -> str:
    return f"""
{system_prompt}

# User Request
{user_input}

# Python Code
"""


def resolve_api_key(cli_api_key: str | None) -> str | None:
    if cli_api_key and cli_api_key.strip():
        return cli_api_key.strip()
    for env_name in ("BIGMODEL_API_KEY", "ZHIPUAI_API_KEY", "ZHIPU_API_KEY"):
        value = os.getenv(env_name)
        if value and value.strip():
            return value.strip()
    return None


def normalize_zhipu_endpoint(endpoint: str | None) -> str:
    if endpoint is None:
        return DEFAULT_ZHIPU_ENDPOINT

    cleaned = endpoint.strip()
    if not cleaned:
        return DEFAULT_ZHIPU_ENDPOINT

    cleaned = cleaned.rstrip("/")
    lower = cleaned.lower()

    if lower.endswith("/chat/completions"):
        return cleaned
    if lower == "https://open.bigmodel.cn/api":
        return DEFAULT_ZHIPU_ENDPOINT
    if lower.endswith("/paas/v4"):
        return f"{cleaned}/chat/completions"

    return cleaned


def is_placeholder_api_key(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDER_KEYS


def strip_code_fences(code: str) -> str:
    cleaned = code.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned.replace("```python", "").replace("```", "").strip()


def is_valid_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def extract_python_only(code: str) -> str:
    """
    Try to keep only valid Python source from model output.
    Handles common cases where explanation text is appended after code.
    """
    candidate = strip_code_fences(code)
    if is_valid_python(candidate):
        return candidate

    lines = candidate.splitlines()

    # Prefer content starting at "from manim import *" if available.
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("from manim import"):
            start_idx = i
            break

    sliced = lines[start_idx:]
    for end in range(len(sliced), 0, -1):
        trial = "\n".join(sliced[:end]).strip()
        if not trial:
            continue
        if is_valid_python(trial):
            return trial

    raise RuntimeError(
        "Generated content is not valid Python code after cleanup. "
        "Please retry or adjust prompt constraints.",
    )


def apply_runtime_compatibility_fixes(code: str) -> tuple[str, list[str]]:
    """
    Apply compatibility patches for environments without LaTeX.
    """
    patched = code
    notes: list[str] = []

    if LATEX_AVAILABLE:
        return patched, notes

    candidate = re.sub(r"\bMathTex\s*\(", "Text(", patched)
    if candidate != patched:
        notes.append("Replaced MathTex(...) with Text(...) because LaTeX is unavailable.")
        patched = candidate

    candidate = re.sub(r"(?<!\w)Tex\s*\(", "Text(", patched)
    if candidate != patched:
        notes.append("Replaced Tex(...) with Text(...) because LaTeX is unavailable.")
        patched = candidate

    candidate = re.sub(r"include_numbers\s*=\s*True", "include_numbers=False", patched)
    if candidate != patched:
        notes.append("Forced include_numbers=False to avoid LaTeX-dependent axis labels.")
        patched = candidate

    candidate = re.sub(r"([\"'])include_numbers\1\s*:\s*True", r"\1include_numbers\1: False", patched)
    if candidate != patched:
        notes.append("Forced axis_config include_numbers=False for LaTeX-free rendering.")
        patched = candidate

    direction_aliases = {
        "UP_RIGHT": "UR",
        "UP_LEFT": "UL",
        "DOWN_RIGHT": "DR",
        "DOWN_LEFT": "DL",
    }
    for bad, good in direction_aliases.items():
        candidate = re.sub(rf"\b{bad}\b", good, patched)
        if candidate != patched:
            notes.append(f"Replaced unsupported direction constant {bad} with {good}.")
            patched = candidate

    return patched, notes


def extract_assistant_text(response_json: dict) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"Unexpected API response (missing choices): {response_json}")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError(f"Unexpected API response (missing message): {response_json}")

    content = message.get("content")
    if isinstance(content, str):
        return content

    # Some OpenAI-compatible providers return segmented content.
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts)

    raise RuntimeError(f"Unexpected API response (missing text content): {response_json}")


def generate_code_with_zhipu(
    *,
    api_key: str,
    endpoint: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> str:
    endpoint = normalize_zhipu_endpoint(endpoint)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }

    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Zhipu API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Cannot reach Zhipu API: {exc}") from exc

    parsed = json.loads(body)
    if isinstance(parsed, dict) and "error" in parsed:
        raise RuntimeError(f"Zhipu API error: {parsed['error']}")
    return extract_assistant_text(parsed)


def run_manim(file_path: str, scene_name: str) -> None:
    cmd = [
        ".venv/bin/manim",
        "-ql",
        "--media_dir",
        "media",
        file_path,
        scene_name,
    ]
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError("Manim render failed.")


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Aegis Manim Generator")
    parser.add_argument("prompt", help="Natural language description of the animation")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Print prompt and ask for code input manually",
    )
    parser.add_argument(
        "--api-key",
        help="Zhipu API key (or set BIGMODEL_API_KEY / ZHIPUAI_API_KEY / ZHIPU_API_KEY)",
    )
    parser.add_argument("--llm_key", help="Backward-compatible alias for --api-key")
    parser.add_argument(
        "--model",
        default=os.getenv("BIGMODEL_MODEL", DEFAULT_MODEL),
        help=f"Model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv("BIGMODEL_ENDPOINT", DEFAULT_ZHIPU_ENDPOINT),
        help="Chat completions endpoint (default: /paas/v4/chat/completions)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature",
    )
    parser.add_argument(
        "--output-file",
        default="gen_scene.py",
        help="Path to save generated scene code",
    )
    parser.add_argument(
        "--scene-name",
        default="GeneratedScene",
        help="Scene class name to render",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Only generate code and skip Manim rendering",
    )

    args = parser.parse_args()
    system_prompt = read_file(PROMPT_PATH)

    if args.simulate:
        full_prompt = generate_simulation_prompt(system_prompt, args.prompt)
        print("\n" + "=" * 40)
        print("SIMULATION MODE: COPY THE TEXT BELOW TO YOUR LLM")
        print("=" * 40 + "\n")
        print(full_prompt)
        print("\n" + "=" * 40)
        print("PASTE THE GENERATED PYTHON CODE BELOW (End with lines containing only 'EOF'):")
        print("=" * 40 + "\n")

        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "EOF":
                    break
                lines.append(line)
            except EOFError:
                break
        code = "\n".join(lines)
    else:
        api_key = resolve_api_key(args.api_key or args.llm_key)
        if not api_key:
            print(
                "Missing API key. Set BIGMODEL_API_KEY (or ZHIPUAI_API_KEY / ZHIPU_API_KEY), "
                "or pass --api-key.",
            )
            return 1
        if is_placeholder_api_key(api_key):
            print(
                "Detected placeholder API key. Please edit your local .env and set a real key.",
            )
            return 1
        try:
            code = generate_code_with_zhipu(
                api_key=api_key,
                endpoint=normalize_zhipu_endpoint(args.endpoint),
                model=args.model,
                system_prompt=system_prompt,
                user_prompt=args.prompt,
                temperature=args.temperature,
            )
        except Exception as exc:  # pragma: no cover - network errors are environment-specific.
            print(f"Failed to generate code from model: {exc}")
            return 1

    output_path = Path(args.output_file)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path

    try:
        cleaned_code = extract_python_only(code)
    except RuntimeError as exc:
        print(f"Generated code validation failed: {exc}")
        return 1

    cleaned_code, notes = apply_runtime_compatibility_fixes(cleaned_code)
    if notes:
        print("Applied compatibility fixes:")
        for note in notes:
            print(f"- {note}")

    output_path.write_text(cleaned_code + "\n", encoding="utf-8")
    print(f"\nSaved generated code to {output_path}")

    if args.no_render:
        return 0

    try:
        run_manim(str(output_path), args.scene_name)
    except Exception as exc:
        print(f"Render step failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
