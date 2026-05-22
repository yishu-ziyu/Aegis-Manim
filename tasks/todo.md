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

# Public Gateway and Layout Stability Task

- [x] Reproduce and fix the Vercel gateway route mismatch that makes the public page submit to a missing API path.
- [x] Make the public gateway default to a cloud-usable provider instead of a local-only Codex provider.
- [x] Add Kimi Code as a cloud model provider using the official OpenAI-compatible API endpoint.
- [x] Add static guardrails for overlapping Manim text and missing text sizing.
- [x] Add readable formula rendering for prompt previews and synchronized teaching scripts.
- [x] Make generated Manim videos default to Chinese visible labels and explanations.
- [x] Verify with focused tests, gateway checks, local source/browser checks, and production smoke checks after deployment.

## Review

Stabilized the public learning flow for formula-heavy Chinese teaching prompts. The Web layer now renders Markdown/LaTeX-style formulas in the prompt preview and synchronized script panel, while the Manim generation path stays LaTeX-free for runtime stability. Generated scenes now default to Chinese visible titles, labels, captions, and teaching explanations unless the user explicitly asks for another language. The public gateway now defaults to a cloud-usable Kimi Code provider, submits to `/api/generate`, handles favicon HEAD/GET cleanly, and keeps local-only providers marked as unavailable in cloud mode.

Verified with Python compile checks, focused pytest suites, gateway verification, `git diff --check`, Vercel build, production deployment, live health/favicon checks, live page source checks, Chrome network/console checks, live MathJax prompt-preview DOM inspection, and a bad-key `/api/generate` smoke test proving the route reaches Kimi authentication instead of failing at routing.

# Render Backend Job Persistence Task

- [x] Read `docs/TECH_SPEC_JOB_PERSISTENCE.md` and map the persistence requirements.
- [x] Add regression tests for Supabase-first registration, Supabase-first reads, startup recovery, orphan reaping, forced Storage upload, upload-failure handling, retry behavior, and memory-only fallback.
- [x] Implement Supabase job listing and REST retry helpers without adding dependencies.
- [x] Make `render_backend/app.py` treat Supabase as the authoritative job source when configured.
- [x] Add startup recovery and an idempotent orphan reaper for stale running jobs.
- [x] Ensure async render success stores a Supabase Storage URL and upload failure marks the job failed.
- [x] Verify with focused backend tests, related Aegis regression tests, gateway verifier, compile checks, Ruff, and diff checks.
- [x] Complete independent code-reviewer review and address HIGH/CRITICAL findings.
- [x] Address follow-up code-reviewer HIGH about root CI collecting backend tests without Flask.
- [x] Complete final code-reviewer re-review after CI collection fix.
- [x] Run local memory-mode async API smoke through submit, poll, render, and download.
- [x] Add repeatable render persistence verifier for local smoke and read-only Supabase readiness.
- [x] Fix Supabase schema deployment helper so PL/pgSQL functions are not split on internal semicolons.
- [x] Confirm no local Supabase management token, database URL/password, or Supabase CLI is available to apply schema automatically.
- [x] Apply `supabase/schema.sql` to the configured Supabase project and re-run read-only readiness.

## Review

Implemented the first local closure for Supabase-backed Render Backend job persistence. Supabase-configured writes now persist first and only update the in-memory cache after success; reads fetch Supabase first and refresh the cache; pending/running jobs can be recovered on startup; stale pending/running jobs are reaped as failed with a user-facing restart message; terminal updates require a pending/running Supabase row so late render completions cannot overwrite orphan failures; async renders require Storage upload before reporting success; empty Supabase config remains memory-only; and `/download` returns Storage URL JSON for completed Supabase jobs. Backend tests are now dependency-gated so root `uv run pytest` does not fail collection when Flask is absent, while a backend-capable environment still runs the full suite. Public gateway coverage also now checks the frontend render/poll/download/playback wiring plus cold-start retry and friendly retry-failure messaging without making production calls. The backend README now documents the Supabase persistence mode, schema setup, memory fallback, and verifier commands. The cloud deploy helper now uses a quote-aware SQL splitter so `supabase/schema.sql` can be applied without corrupting PL/pgSQL function bodies. Local verification passed with 19 persistence tests, 4 deploy-schema tests, root-env 18 passed / 12 skipped across deploy-schema, persistence, and public gateway tests, 48 focused Aegis/render/deploy tests, Vercel gateway verification, a local memory-mode async API smoke through submit/poll/download with a real MP4 response, Python compile checks, Ruff, and `git diff --check`. Final code-reviewer re-review of the current terminal transition guard and expected-status filters reported APPROVE with no CRITICAL/HIGH blockers. Supabase readiness is now complete for the new Aegis-Manim project `lnbalcskhcnkrtlqpgku`: `supabase/schema.sql` was applied through the Supabase SQL Editor, `.env.local` now points at `https://lnbalcskhcnkrtlqpgku.supabase.co`, `SUPABASE_STORAGE_BUCKET` is `manim-videos`, and `python scripts/verify_render_persistence.py --external-read-only --env-file .env.local` returned 200 for `render_jobs`, `job_logs`, and the Storage bucket. The local env currently uses the legacy `service_role` backend key because that was the complete server key available from the dashboard; Supabase official docs prefer `sb_secret_...` for new backend work, and it can replace the same `SUPABASE_SERVICE_KEY` value later without code changes.

# Codex App Render Timeout Follow-up

- [x] Read `tasks/codex-app-handoff.md` and keep the existing Supabase project/env wiring intact.
- [x] Re-check Render `/health` after the reported timeout blocker.
- [x] Re-check Vercel `/api/render/status/not-a-real-job` proxy behavior.
- [x] Re-check Vercel `/api/health`.
- [x] Re-run Supabase read-only persistence readiness.
- [x] Re-run focused deploy/persistence/public-trial regression tests.
- [x] Attempt Render dashboard log inspection without printing secrets.

## Review

The reported Render timeout blocker recovered on 2026-05-22 17:51 CST. Render `/health` returned HTTP 200 in 2.576s with `supabase.ok=true`; Vercel `/api/render/status/not-a-real-job` returned the expected Render JSON 404 in 1.955s, proving proxy reachability and authentication; and Vercel `/api/health` returned HTTP 200 in 1.059s. `python scripts/verify_render_persistence.py --external-read-only --env-file .env.local` passed with 200 responses for `render_jobs`, `job_logs`, and the `manim-videos` bucket. `pytest -o addopts='' tests/test_deploy_cloud_schema.py tests/test_render_backend_persistence.py tests/test_aegis_public_trial.py -q` passed with 30 tests. Render dashboard logs were attempted in Chrome, but the current Codex App/Chrome accessibility surface did not expose readable log content; no local Render CLI or Render API token env was available for CLI/API log retrieval.

# Public Site End-to-End Acceptance

- [x] Confirm Render production env points to the new Supabase project.
- [x] Redeploy Vercel production after the playback fallback fix.
- [x] Confirm public `/api/health` is OK after redeploy.
- [x] Run live public `/api/generate` without a client API key.
- [x] Run live public `/api/render` from generated Manim code.
- [x] Poll production render status to `done`.
- [x] Confirm the final MP4 is reachable with HTTP 200 and `video/mp4`.
- [x] Confirm the MP4 URL uses Supabase ref `lnbalcskhcnkrtlqpgku` and not old ref `qrmmlolsslnxiamznicf`.
- [x] Record final production acceptance evidence in `tasks/codex-app-handoff.md`.

## Review

Production acceptance passed on 2026-05-22 18:18 CST. Render dashboard Events showed the env-update deploy live for service `srv-d8786u0g4nts73dkqicg` at 18:08 CST. Vercel production deploy `dpl_CDybstzBYL5SH8GygsWDmA8Hcfa6` is READY and aliased to `https://manim-main.vercel.app`. The live public generate endpoint returned HTTP 200 with generated code using `trial-minimax-direct` and no client API key. The generated code was submitted to live public render; job `c20b8fff...` reached `done`; the fallback download payload contained a `video_url`; and `HEAD` on that URL returned HTTP 200, `content-type: video/mp4`, `content-length: 34189`. The video URL used the new Supabase ref `lnbalcskhcnkrtlqpgku` and did not use old ref `qrmmlolsslnxiamznicf`. Focused regression tests passed with `28 passed in 1.24s`, and `git diff --check` passed.

# Local Acceleration and Render Timeout Hardening

- [x] Diagnose the screenshot timeout path from production health, proxy status, generated scene name, and job persistence state.
- [x] Fix public generation to return the detected generated `Scene` subclass instead of only the input scene name.
- [x] Fix production status polling to fall back to the Vercel proxy when direct Render status returns non-200.
- [x] Add Render backend hard timeout with process-group kill.
- [x] Make render timeout configurable and reduce default long-running-task window.
- [x] Add local one-click launcher for cloud generation plus local Manim rendering.
- [x] Add regression tests for cloud-generate local mode and detected scene-name responses.
- [x] Run focused regression tests, py_compile, and diff checks.

## Review

The screenshot timeout was not a Supabase schema problem. Render health and Vercel proxy health recovered, but the production page could still wait out the render loop because direct Render polling used the development API key and ignored non-200 responses instead of falling back to the Vercel proxy. The same request also exposed a scene-name mismatch: the generated Python class was `ParetoOptimalityScene` while the submitted input scene name was still `GeneratedScene`. Those two issues are fixed. A follow-up production run returned `sceneName=ParetoOptimalityScene` and Vercel status polling returned repeated HTTP 200, but the job `50f98770...` remained `running` in Supabase without stderr/error/video, pointing to an individual Render/Manim worker task running too long. The backend now launches Manim in its own process group, kills it on timeout, defaults render timeout to 180 seconds, and reaps orphan running jobs after timeout plus 60 seconds. `scripts/start_aegis_local.command` adds a friend-facing local acceleration path: it creates/uses a local venv, starts the render backend, starts Aegis Web, uses the production cloud `/api/generate` for no-key code generation, renders on the friend machine, and opens the local browser URL. Local launcher smoke passed on ports 8013/5013 with local `/api/health` OK. Verification passed with `43 passed`, `git diff --check`, Python compile checks, and script syntax checks. Commit `8e3dba6` was pushed to `origin/main`, and the Render deploy hook was triggered after the push.

# Public Render Failure and Windows Local Launcher Follow-up

- [x] Inspect the latest failed production render job from Supabase without printing secrets.
- [x] Identify the concrete Manim runtime error behind `Manim rendering failed`.
- [x] Add a runtime compatibility patch for the generated `Sector(outer_radius=...)` pattern.
- [x] Add regression coverage proving `Sector` is rewritten while `AnnularSector` remains unchanged.
- [x] Add a Windows double-click local launcher for cloud generation plus local rendering.
- [x] Add launcher safety coverage proving the Windows script does not embed Supabase/server secrets.
- [x] Diagnose the local launcher `渲染提交失败: Not found.` path.
- [x] Add local Web `/api/render`, `/api/render/status`, and `/api/render/download` proxy routes.
- [x] Make local render-browser requests use the configured render API key instead of a hard-coded value.
- [x] Make Mac and Windows launchers avoid stale occupied render ports.
- [x] Tighten generation prompts for short hosted-render scenes to reduce Render timeout risk.
- [x] Run focused regression tests, Python compile checks, script checks, and diff checks.

## Review

The 2026-05-22 screenshot failure is a generated-code compatibility failure, not a Supabase/Render connectivity failure. Render `/health` and Vercel `/api/health` were healthy, and the latest failed persisted job `4c66b30e...` showed `TypeError: AnnularSector.__init__() got multiple values for keyword argument 'outer_radius'` from generated `Sector(outer_radius=1.5, ...)`. The generation compatibility layer now rewrites `Sector(outer_radius=...)` to `Sector(radius=...)` for the current Manim API while leaving `AnnularSector(... outer_radius=...)` intact. The original failed job code was rechecked locally through the compatibility layer: it had `Sector(outer_radius=...)` before patching and no longer had it after patching. Vercel deploy `dpl_HwgD3JgkQShuV2ZBY2g3Rie3M3LH` proved the Sector fix reached production: a new public generate request `20260522-142925-vercel` contained no `Sector(outer_radius=...)` and `/api/render` accepted it with HTTP 202, but Render still timed out after 180s because the generated scene was too heavy for the free/small cloud worker. The prompt now asks for short hosted-render scenes: 15-35 seconds, 4-7 `self.play` calls, sparse objects, and no dense/long animation patterns by default.

The local launcher failure was a separate path issue. The user's current `127.0.0.1:8000` process was an old Web process without `/api/render`, while the `127.0.0.1:5001` render process rejected the browser's hard-coded API key, causing fallback to `POST /api/render` and then `Not found.`. Local Web now has server-side render submit/status/download proxy routes, browser-side direct calls use the configured render API key, and both Mac and Windows launchers avoid stale occupied render ports when possible. A fresh local smoke on ports 8016/5014 submitted a minimal animated scene through `/api/render`, polled to `done`, and downloaded `video/mp4` with 7160 bytes. `scripts/start_aegis_local_windows.bat` provides the Windows friend path: create/use a local venv, require Python 3 and ffmpeg, install render dependencies, start local Render Backend and local Aegis Web, use the production cloud `/api/generate` endpoint, render on the friend computer, and open `http://127.0.0.1:8000`. Verification passed with `62 passed`, `32 passed`, `git diff --check`, `python -m py_compile core/manim_agent.py core/web_app.py api/index.py`, and `bash -n scripts/start_aegis_local.command`.
