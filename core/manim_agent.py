from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from llm_providers import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_ZHIPU_ENDPOINT,
    generate_code_with_provider,
    normalize_chat_completions_endpoint,
    resolve_provider,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = PROJECT_ROOT / "prompts" / "system_prompt.md"
MANIM_KNOWLEDGE_PATH = PROJECT_ROOT / "prompts" / "manim_knowledge_pack.md"
PLACEHOLDER_KEYS = {
    "your_api_key_here",
    "your-api-key-here",
    "<your_api_key>",
    "changeme",
}


def detect_latex_available() -> bool:
    if not shutil.which("latex") or not shutil.which("dvisvgm"):
        return False

    kpsewhich = shutil.which("kpsewhich")
    if not kpsewhich:
        return False

    try:
        result = subprocess.run(
            [kpsewhich, "standalone.cls"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return result.returncode == 0 and bool(result.stdout.strip())


LATEX_AVAILABLE = detect_latex_available()


def read_file(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def load_system_prompt() -> str:
    prompt = read_file(PROMPT_PATH).strip()
    if MANIM_KNOWLEDGE_PATH.exists():
        knowledge = read_file(MANIM_KNOWLEDGE_PATH).strip()
        if knowledge:
            return f"{prompt}\n\n{knowledge}\n"
    return f"{prompt}\n"


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


def resolve_api_key(cli_api_key: str | None, provider_id: str | None = None) -> str | None:
    if cli_api_key and cli_api_key.strip():
        return cli_api_key.strip()

    provider = resolve_provider(provider_id)
    env_names_by_provider = {
        "zhipu": ("BIGMODEL_API_KEY", "ZHIPUAI_API_KEY", "ZHIPU_API_KEY"),
        "openai": ("OPENAI_API_KEY",),
        "codex-local-proxy": ("CODEX_API_KEY", "OPENAI_API_KEY"),
        "minimax-token-global": ("MINIMAX_API_KEY",),
        "minimax-token-cn": ("MINIMAX_API_KEY",),
        "minimax-coding-global": ("MINIMAX_API_KEY",),
        "minimax-coding-cn": ("MINIMAX_API_KEY",),
        "minimax-openai-cn": ("MINIMAX_API_KEY",),
    }
    env_names = (
        *env_names_by_provider.get(provider.id, ()),
        "LLM_API_KEY",
        "API_KEY",
    )
    for env_name in env_names:
        value = os.getenv(env_name)
        if value and value.strip():
            return value.strip()
    return None


def normalize_zhipu_endpoint(endpoint: str | None) -> str:
    return normalize_chat_completions_endpoint(endpoint)


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
    """Apply compatibility patches for generated Manim code."""
    patched = code
    notes: list[str] = []

    def convert_line_config_to_kwargs(match: re.Match[str]) -> str:
        plot_call = match.group(0)

        def convert_config(config_match: re.Match[str]) -> str:
            kwargs = []
            for entry in config_match.group(1).split(","):
                if ":" not in entry:
                    return config_match.group(0)
                key, value = entry.split(":", 1)
                key = key.strip().strip("\"'")
                value = value.strip()
                if not key.startswith("stroke_"):
                    return config_match.group(0)
                kwargs.append(f"{key}={value}")
            return ", ".join(kwargs)

        return re.sub(r"line_config\s*=\s*\{([^{}\n]*)\}", convert_config, plot_call)

    candidate = re.sub(r"\bMathTex\s*\(", "Text(", patched)
    if candidate != patched:
        notes.append("Replaced MathTex(...) with Text(...) for the default LaTeX-free product path.")
        patched = candidate

    candidate = re.sub(r"(?<!\w)Tex\s*\(", "Text(", patched)
    if candidate != patched:
        notes.append("Replaced Tex(...) with Text(...) for the default LaTeX-free product path.")
        patched = candidate

    candidate = re.sub(r"include_numbers\s*=\s*True", "include_numbers=False", patched)
    if candidate != patched:
        notes.append("Forced include_numbers=False to avoid LaTeX-dependent axis labels.")
        patched = candidate

    candidate = re.sub(r"([\"'])include_numbers\1\s*:\s*True", r"\1include_numbers\1: False", patched)
    if candidate != patched:
        notes.append("Forced axis_config include_numbers=False for LaTeX-free rendering.")
        patched = candidate

    brace_lines = []
    changed_brace_label = False
    for line in patched.splitlines():
        stripped = line.rstrip()
        trailing = line[len(stripped) :]
        if "BraceLabel(" in stripped and "label_constructor" not in stripped and stripped.endswith(")"):
            stripped = f"{stripped[:-1]}, label_constructor=Text)"
            changed_brace_label = True
        brace_lines.append(f"{stripped}{trailing}")
    if changed_brace_label:
        notes.append("Forced BraceLabel to use Text labels for the default LaTeX-free product path.")
        patched = "\n".join(brace_lines)

    candidate = re.sub(
        r"(?m)^([ \t]*)[A-Za-z_][A-Za-z0-9_]*\.add_coordinates\([^)]*\)[ \t]*(?:#.*)?$",
        r"\1# Removed numeric axis labels because they require LaTeX.",
        patched,
    )
    if candidate != patched:
        notes.append("Removed add_coordinates() because numeric axis labels require LaTeX.")
        patched = candidate

    candidate = re.sub(r"\.get_h_line\s*\(", ".get_horizontal_line(", patched)
    candidate = re.sub(r"\.get_v_line\s*\(", ".get_vertical_line(", candidate)
    if candidate != patched:
        notes.append("Replaced Axes get_h_line/get_v_line with current Manim line helpers.")
        patched = candidate

    candidate = re.sub(r"\.getHorizontalLine\s*\(", ".get_horizontal_line(", patched)
    candidate = re.sub(r"\.getVerticalLine\s*\(", ".get_vertical_line(", candidate)
    if candidate != patched:
        notes.append("Replaced Axes camelCase line helpers with current Manim snake_case helpers.")
        patched = candidate

    candidate = re.sub(r"axes\.plot\([\s\S]*?\)", convert_line_config_to_kwargs, patched)
    if candidate != patched:
        notes.append("Converted axes.plot line_config={...} to supported stroke keyword arguments.")
        patched = candidate

    candidate = re.sub(
        r"(?m)^([ \t]*)[A-Za-z_][A-Za-z0-9_]*\.set_style\([ \t]*stroke_dash[ \t]*=[ \t]*\[[^\]]*\][ \t]*\)[ \t]*(?:#.*)?$",
        r"\1# Removed unsupported dashed-line style.",
        patched,
    )
    if candidate != patched:
        notes.append("Removed unsupported VMobject.set_style(stroke_dash=...) call.")
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
    code, _provider, _resolved_endpoint = generate_code_with_provider(
        provider_id="zhipu",
        api_key=api_key,
        base_url=None,
        endpoint=endpoint,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
    )
    return code


def generate_code_with_llm(
    *,
    provider_id: str,
    api_key: str,
    base_url: str | None,
    endpoint: str | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> tuple[str, str, str]:
    code, provider, resolved_endpoint = generate_code_with_provider(
        provider_id=provider_id,
        api_key=api_key,
        base_url=base_url,
        endpoint=endpoint,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
    )
    return code, provider.name, resolved_endpoint


def run_manim(file_path: str, scene_name: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "manim",
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


def try_render_code(
    code: str,
    scene_name: str,
    media_dir: str = "media",
) -> tuple[bool, str]:
    """Try to render Manim code in a temp directory. Return (success, error_log)."""
    with tempfile.TemporaryDirectory(prefix="aegis-ritl-") as temp_dir:
        temp_path = Path(temp_dir) / "scene.py"
        temp_path.write_text(code + "\n", encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            "manim",
            "-ql",
            "--media_dir",
            str(Path(temp_dir) / media_dir),
            str(temp_path),
            scene_name,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode == 0:
            return True, ""
        # Collect stderr first, fallback to stdout
        error_log = (result.stderr or result.stdout or "").strip()
        return False, error_log


def build_ritl_feedback_prompt(
    original_prompt: str,
    current_code: str,
    error_log: str,
    attempt: int,
) -> str:
    """Build a feedback prompt for RITL retry."""
    # Truncate error log to avoid overwhelming the context window
    max_error_chars = 2_000
    truncated_error = error_log[:max_error_chars]
    if len(error_log) > max_error_chars:
        truncated_error += "\n...[error log truncated]"

    return f"""The following Manim Python code was generated for this request:

--- Original Request ---
{original_prompt}

--- Generated Code (Attempt {attempt}) ---
```python
{current_code}
```

--- Render Error ---
{truncated_error}

--- Task ---
Fix the code so it renders successfully. Preserve the educational content and narrative structure. Output ONLY the corrected Python code.
"""


def generate_code_with_ritl(
    *,
    provider_id: str,
    api_key: str,
    base_url: str | None,
    endpoint: str | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    scene_name: str = "GeneratedScene",
    max_retries: int = 3,
) -> tuple[str, int, list[str]]:
    """Generate Manim code with RITL (Renderer-in-the-Loop) feedback.

    Returns:
        (final_code, attempts_used, ritl_notes)
    """
    original_prompt = user_prompt
    ritl_notes: list[str] = []
    current_code = ""

    for attempt in range(1, max_retries + 1):
        # Adjust temperature: slightly increase on retry for exploration
        adjusted_temp = min(temperature + (attempt - 1) * 0.1, 0.7)

        raw_code, provider_name, used_endpoint = generate_code_with_llm(
            provider_id=provider_id,
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=adjusted_temp,
        )

        cleaned_code = extract_python_only(raw_code)
        patched_code, compat_notes = apply_runtime_compatibility_fixes(cleaned_code)
        current_code = patched_code

        if compat_notes:
            ritl_notes.extend(compat_notes)

        # Try rendering
        success, error_log = try_render_code(current_code, scene_name)

        if success:
            if attempt > 1:
                ritl_notes.append(f"RITL: Render succeeded on attempt {attempt}.")
            return current_code, attempt, ritl_notes

        # Render failed — prepare feedback for next attempt
        ritl_notes.append(
            f"RITL attempt {attempt} failed: {error_log[:200]}..."
            if len(error_log) > 200
            else f"RITL attempt {attempt} failed: {error_log}"
        )

        if attempt < max_retries:
            user_prompt = build_ritl_feedback_prompt(
                original_prompt=original_prompt,
                current_code=current_code,
                error_log=error_log,
                attempt=attempt,
            )

    # All retries exhausted
    ritl_notes.append(f"RITL: All {max_retries} attempts failed. Returning last code.")
    return current_code, max_retries, ritl_notes


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
        help=(
            "Provider API key. Env fallback: BIGMODEL_API_KEY, OPENAI_API_KEY, "
            "MINIMAX_API_KEY, LLM_API_KEY depending on --provider."
        ),
    )
    parser.add_argument("--llm_key", help="Backward-compatible alias for --api-key")
    parser.add_argument(
        "--provider",
        default=os.getenv("AEGIS_LLM_PROVIDER", DEFAULT_PROVIDER),
        help="LLM provider id, e.g. zhipu, openai, minimax-token-cn, custom-openai.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("BIGMODEL_MODEL", DEFAULT_MODEL),
        help=f"Model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("AEGIS_LLM_BASE_URL", ""),
        help="Provider base URL, e.g. https://api.openai.com/v1 or a local compatible proxy.",
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv("BIGMODEL_ENDPOINT", DEFAULT_ZHIPU_ENDPOINT),
        help="Backward-compatible OpenAI-compatible chat completions endpoint.",
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
    parser.add_argument(
        "--ritl",
        action="store_true",
        help="Enable Renderer-in-the-Loop: auto-retry on render failures",
    )
    parser.add_argument(
        "--ritl-retries",
        type=int,
        default=3,
        help="Max RITL retry attempts (default: 3)",
    )

    args = parser.parse_args()
    system_prompt = load_system_prompt()

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
        provider = resolve_provider(args.provider)
        api_key = resolve_api_key(args.api_key or args.llm_key, provider.id)
        if provider.requires_api_key and not api_key:
            print(
                f"Missing API key for {provider.name}. Set provider env key "
                "(BIGMODEL_API_KEY / OPENAI_API_KEY / MINIMAX_API_KEY / LLM_API_KEY) "
                "or pass --api-key.",
            )
            return 1
        if api_key and is_placeholder_api_key(api_key):
            print(
                "Detected placeholder API key. Please edit your local .env and set a real key.",
            )
            return 1
        try:
            if args.ritl:
                print(f"RITL enabled (max {args.ritl_retries} retries)...")
                cleaned_code, attempts, ritl_notes = generate_code_with_ritl(
                    provider_id=provider.id,
                    api_key=api_key or "",
                    base_url=args.base_url or None,
                    endpoint=args.endpoint if provider.id == "zhipu" else None,
                    model=args.model,
                    system_prompt=system_prompt,
                    user_prompt=args.prompt,
                    temperature=args.temperature,
                    scene_name=args.scene_name,
                    max_retries=args.ritl_retries,
                )
                print(f"RITL completed in {attempts} attempt(s).")
                notes = ritl_notes
            else:
                code, provider_name, resolved_endpoint = generate_code_with_llm(
                    provider_id=provider.id,
                    api_key=api_key or "",
                    base_url=args.base_url or None,
                    endpoint=args.endpoint if provider.id == "zhipu" else None,
                    model=args.model,
                    system_prompt=system_prompt,
                    user_prompt=args.prompt,
                    temperature=args.temperature,
                )
                print(f"Provider: {provider_name} ({resolved_endpoint})")
                cleaned_code = extract_python_only(code)
                cleaned_code, notes = apply_runtime_compatibility_fixes(cleaned_code)
        except Exception as exc:  # pragma: no cover - network errors are environment-specific.
            print(f"Failed to generate code from model: {exc}")
            return 1

    output_path = Path(args.output_file)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path

    if args.simulate:
        try:
            cleaned_code = extract_python_only(code)
        except RuntimeError as exc:
            print(f"Generated code validation failed: {exc}")
            return 1
        cleaned_code, notes = apply_runtime_compatibility_fixes(cleaned_code)

    if notes:
        print("Applied compatibility fixes / RITL notes:")
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
