# Dual-Coding Generation Process Goal

- [x] Build a real backend job/event state layer for generation, rendering, retry, and alignment.
- [x] Translate backend events into student-facing learning-process language.
- [x] Keep technical errors, attempts, and logs in a collapsible diagnostic layer.
- [x] Add a product knowledge substrate for Manim rules, local failure patterns, and verified repair recipes.
- [x] Add rule prechecks, error classification, and repair recipe prompts before retry.
- [x] Wire the Web UI to poll real job state instead of relying on timed placeholder progress.
- [x] Add focused tests for event translation, precheck, classification, repair prompts, and job snapshots.
- [x] Verify locally with tests, compile checks, and API smoke checks on `127.0.0.1:18011`.

## Review

Implemented the first event-driven dual-coding generation loop. Web generation now starts an async job, polls `/api/jobs/{id}`, shows real student-facing events, and keeps technical events in a collapsible diagnostics layer. Added a Manim product knowledge substrate with official-doc source anchors, local-failure source anchors, pre-render checks, render-error classification, and repair recipes used for retry prompts. Verified with 31 focused Aegis tests, compile checks, local health, async job success smoke, and async validation-failure smoke. Chrome visual automation was blocked by a local CDP authorization prompt, so browser-level visual QA remains to be rerun after Chrome debugging access is allowed.

# Manim Knowledge Layer Task

- [x] Inspect existing prompt and generation flow.
- [x] Verify local Manim runtime version.
- [x] Add a compact Manim syntax and pattern knowledge pack.
- [x] Load the knowledge pack through CLI and Web generation paths.
- [x] Add tests for prompt context injection.
- [x] Run lint, tests, compile checks, and a generation/render smoke test.

## Review

Implemented a prompt-level Manim knowledge layer loaded by both CLI and Web generation paths. Verified with lint, 18 focused tests, compile checks, and a real `codex-cli` Web request that generated and rendered `GeneratedScene`.

# Vercel Gateway Deployment Task

- [x] Add a Vercel Python Function entrypoint for the public web gateway.
- [x] Add Vercel routing and minimal dependency configuration.
- [x] Add focused verification for gateway health and render-offload behavior.
- [x] Run verification, commit, and push so Vercel can redeploy.

## Review

Added a minimal Vercel gateway for `manim.yishuziyu.cn`: FastAPI entrypoint, shared response builders, minimal dependency install, and gateway verification. `vercel build --yes` now completes locally; full Manim rendering remains intentionally offloaded to a future VPS/Render/Fly backend.

# Vercel Generate-Code UI Task

- [x] Replace the placeholder-only gateway page with a usable generation form.
- [x] Enable `/api/generate` to call remote LLM providers and return Manim code.
- [x] Hide local-only providers from the cloud UI.
- [x] Verify with gateway checks, compile checks, and `vercel build --yes`.

## Review

The subdomain can now do useful work: Vercel generates Manim code through remote providers while still making video rendering an explicit external-backend boundary.

# Local/Subdomain UI Consistency Task

- [x] Confirm the local checkout and GitHub remote.
- [x] Identify why `127.0.0.1:8000` did not match Aegis.
- [x] Start and verify the local Aegis Web app on an open port.
- [x] Make the Vercel gateway reuse the local Aegis Studio UI.
- [x] Keep Vercel-specific cloud/render limits visible in the page.
- [x] Run gateway checks, compile checks, and Vercel build.

## Review

The repository was correct. The mismatch came from a non-Aegis service occupying local port 8000 plus a separate Vercel-only gateway page. Local Aegis is verified on `127.0.0.1:8010`; the Vercel page now derives from `core/web_app.py` and only swaps cloud-mode copy and render-backend boundaries.

# Learning View and Complex Prompt Resilience Task

- [x] Add regression coverage for complex prompt brief planning and model-timeout retry.
- [x] Add a teaching brief layer before Manim code generation for complex prompts.
- [x] Retry recoverable model request failures instead of failing after the first timeout.
- [x] Rework the result surface so successful generation enters a learning-first view.
- [x] Keep generated code and technical logs available but secondary by default.
- [x] Verify with tests, compile checks, local API checks, and browser/source smoke checks.

## Review

Implemented the first bounded learning-view closure. Complex formula-heavy learning prompts now produce a compact teaching brief before code generation, recoverable model-call failures retry instead of failing immediately, and retry attempts can switch to a faster model variant when the provider exposes one. Successful generations now enter a learning-first result surface with video and synchronized script as the primary right-side view, while generated code remains available as a secondary toggle and technical events stay in diagnostics.
