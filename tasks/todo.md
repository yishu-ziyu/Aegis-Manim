# Dual-Coding Generation Process Goal

# Trial Provider Stability and Community Works MVP

- [x] Dispatch subagents for provider stability, cache/community structure, and community works architecture.
- [x] Run live custom-domain provider sampling without printing secrets or generated code.
- [x] Add a repeatable provider stability measurement script.
- [x] Fix the stale Vercel gateway verifier default-provider assertions.
- [x] Add MiniMax Coding CN endpoint regression coverage.
- [x] Record the community works MVP technical specification.
- [x] Implement Supabase community work tables in a reviewable migration.
- [x] Add Render community search/publish/rate/reuse APIs.
- [x] Add Vercel proxy routes for community APIs.
- [x] Add frontend search-before-generate, reuse, publish, and rating UI.
- [ ] Run production acceptance: cache hit skips generate/render; cache miss still renders; published work can be reused.

## Review

Provider sampling on 2026-05-23 CST showed MiniMax direct is the safer public default: `trial-minimax-direct` returned 3/3 live successes with latencies about 9s, 33s, and 58s, all through `server-managed-trial` and no stable fallback. `trial-kimi-priority` returned 2/3 live successes and one 90s client timeout; the two successes were slow at about 58s and 89s. The current default should remain MiniMax direct, with Kimi treated as an optional higher-variance path. Added `scripts/measure_trial_provider_stability.py` so future checks can measure HTTP success, true model success, stable fallback rate, latency, and render-budget counts without printing secrets or generated code. Added `docs/TECH_SPEC_COMMUNITY_WORKS.md` for the MVP community works layer: search existing high-quality works first, reuse existing code/video on hit, fall back to current generate/render on miss, and let users publish/rate completed renders.

Implemented the code-side community works MVP on 2026-05-23 CST. Added Supabase `community_works`, `community_work_ratings`, and `community_work_events` schema; Render `/community/search`, `/community/works`, `/community/works/{id}/rating`, and `/community/works/{id}/reuse`; Vercel and local Web proxy routes; and frontend search-before-generate, reuse, publish, and rating controls. Also removed browser-visible Render API key usage: both cloud and local UI now call same-origin `/api/render` and `/api/community/*` proxies. `.env.prod` and `.env.vercel` were removed from Git tracking without deleting local files, `.env.*` is now ignored, and the Vercel env sync workflow no longer pushes Supabase service credentials to Vercel.

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
- [x] Add a Vercel generation budget gate that regenerates over-budget public trial code before returning it.
- [x] Run focused regression tests, Python compile checks, script checks, and diff checks.

## Review

The 2026-05-22 screenshot failure is a generated-code compatibility failure, not a Supabase/Render connectivity failure. Render `/health` and Vercel `/api/health` were healthy, and the latest failed persisted job `4c66b30e...` showed `TypeError: AnnularSector.__init__() got multiple values for keyword argument 'outer_radius'` from generated `Sector(outer_radius=1.5, ...)`. The generation compatibility layer now rewrites `Sector(outer_radius=...)` to `Sector(radius=...)` for the current Manim API while leaving `AnnularSector(... outer_radius=...)` intact. The original failed job code was rechecked locally through the compatibility layer: it had `Sector(outer_radius=...)` before patching and no longer had it after patching. Vercel deploy `dpl_HwgD3JgkQShuV2ZBY2g3Rie3M3LH` proved the Sector fix reached production: a new public generate request `20260522-142925-vercel` contained no `Sector(outer_radius=...)` and `/api/render` accepted it with HTTP 202, but Render still timed out after 180s because the generated scene was too heavy for the free/small cloud worker. The prompt now asks for short hosted-render scenes: 15-35 seconds, 4-7 `self.play` calls, sparse objects, and no dense/long animation patterns by default.

The local launcher failure was a separate path issue. The user's current `127.0.0.1:8000` process was an old Web process without `/api/render`, while the `127.0.0.1:5001` render process rejected the browser's hard-coded API key, causing fallback to `POST /api/render` and then `Not found.`. Local Web now has server-side render submit/status/download proxy routes, browser-side direct calls use the configured render API key, and both Mac and Windows launchers avoid stale occupied render ports when possible. A fresh local smoke on ports 8016/5014 submitted a minimal animated scene through `/api/render`, polled to `done`, and downloaded `video/mp4` with 7160 bytes. `scripts/start_aegis_local_windows.bat` provides the Windows friend path: create/use a local venv, require Python 3 and ffmpeg, install render dependencies, start local Render Backend and local Aegis Web, use the production cloud `/api/generate` endpoint, render on the friend computer, and open `http://127.0.0.1:8000`. After Vercel deploy `dpl_Canz83k9urfUE7PTvM4oVHurZjMF`, production health was OK, but a new generated Pareto scene still had 23 `self.play` calls and 2 `LaggedStart` calls. The Vercel gateway now detects over-budget public trial code and automatically asks the same provider to regenerate under hosted-render limits before returning code. Verification passed with `63 passed`, `33 passed`, `32 passed`, `git diff --check`, `python -m py_compile core/manim_agent.py core/web_app.py api/index.py`, and `bash -n scripts/start_aegis_local.command`.

# Segmented Render Quality Recovery

- [x] Treat short-scene prompting as a temporary guard, not the final quality strategy.
- [x] Add Render Backend `render_mode` support: `auto`, `single`, and `segmented`.
- [x] Plan render segments from generated Manim `self.play(...)` / `self.wait(...)` events.
- [x] Render over-budget scenes in animation ranges with Manim `-n start,end`.
- [x] Concatenate segment MP4 files with `ffmpeg` and upload only the final MP4.
- [x] Persist segment progress in the existing `render_jobs.metadata` JSON field.
- [x] Expose render mode, stage, progress, and segment state through `/status/<job_id>`.
- [x] Forward `render_mode: auto` through the Vercel gateway and local Web proxy.
- [x] Relax hosted generation limits from short previews to segmented-render friendly teaching scenes.
- [x] Add focused regression tests for segment planning, command ranges, concat manifests, final-only upload, and proxy compatibility.
- [x] Run focused regression tests, Python compile checks, and diff checks.

## Review

The Render timeout path is now treated as a worker-budget problem rather than a Supabase schema problem or a reason to permanently cut teaching quality. Async render submissions default to `render_mode=auto`: short scenes still use the existing single Manim render path, while longer scenes are split into Manim animation ranges, rendered in separate subprocesses, concatenated into one MP4 with `ffmpeg`, and then uploaded as a single final video. Segment progress is stored in the existing Supabase `render_jobs.metadata` JSON field, so `/status/<job_id>` can report `render_mode`, `stage`, `progress`, and per-segment state without a schema migration. Vercel and the local Web proxy now explicitly forward `render_mode: auto`. The public generation safety gate was relaxed from a 4-7 play short-preview limit to a segmented-render friendly 24-play hard ceiling, and the prompt now targets 45-120 second multi-step teaching scenes instead of forcing a minimal preview. Verification passed with `68 passed`, `python -m py_compile render_backend/app.py render_backend/supabase_client.py api/index.py core/web_app.py`, `git diff --check`, and a local real segmented render smoke that produced a 15561-byte MP4. Commit `262c14c` was pushed; Vercel production deploy `dpl_9cQ6oEpkQhgL2v6x5ZWPvvEbkiWy` reached READY; Render deploy hook returned HTTP 202; Render `/health` returned HTTP 200 with `supabase.ok=true`; and live public job `c91b6fef-5e99-4db1-8025-99978affb6eb` completed as `render_mode=segmented` with progress `0/2 -> 1/2 -> done 2/2` and a final downloadable video URL.

# Public Cloud Friend-Usable Closure

- [x] Bound server-managed trial model calls so Vercel generation does not hang behind slow providers.
- [x] Change public default provider to MiniMax direct and reset browser storage key.
- [x] Add deterministic stable-template fallback when trial providers are slow or unavailable.
- [x] Remove loop-expanded animations from the fallback template.
- [x] Restart recovered pending/running Supabase jobs after Render worker startup.
- [x] Add one automatic browser resubmission for Render restart/resubmit failures.
- [x] Lower default automatic render segmentation threshold for constrained Render workers.
- [x] Re-run focused cloud/render/model/provider regression tests.
- [x] Deploy Vercel production and trigger Render deploy.
- [x] Run a real production generate -> render -> status -> MP4 HEAD closed-loop.
- [x] Run a fallback-template production render smoke.

## Review

Closed the public friend-facing cloud path on 2026-05-23 CST. The system now uses bounded model calls, MiniMax direct by default, a loop-free stable fallback, Render startup job recovery, one UI retry after Render restart failures, and more aggressive event segmentation for constrained workers. Regression verification passed with `76 passed`, Python compile checks, and `git diff --check`. Commits `f58fca8` and `d392e1b` were pushed to `origin/main`. Vercel deployment `dpl_7ySJjZppppHrNjhpfDD638JHomqf` is READY and aliased to `https://manim-main.vercel.app`; Render deploy hook returned 202 and `/health` returned HTTP 200 with `supabase.ok=true`. Final live closed-loop passed: `/api/generate` request `20260522-162045-vercel` used `trial-minimax-direct`, generated `LinearGrowthGap`, `/api/render` job `5bbfac97-c75f-4edc-a71c-09f630e4c86c` ran as `render_mode=segmented`, progressed `0/2 -> 1/2 -> concatenating -> done`, and the final Supabase MP4 returned `HEAD 200 video/mp4` with 134467 bytes. The stable fallback template was also submitted to production render as job `4c5e740f-c3cc-4cee-b75a-bea272065034` and returned `HEAD 200 video/mp4` with 37144 bytes. Remaining strategic risk is Render free/small-worker capacity; the next production-grade architecture should move the worker layer to a queue/job platform such as Cloud Run Jobs or Modal while preserving the current async job-status-output contract.

# Production Chinese Font Quality Fix

- [x] Reproduce the reported poor-quality MP4 from production and extract frames.

# Custom Domain Render Closure

- [x] Move `manim.yishuziyu.cn` off the stale `aegis-manim` Vercel project and onto the canonical `manim-main` project.
- [x] Verify the custom domain reaches `manim-main` health and Render proxy instead of the unconfigured duplicate project.
- [x] Fix render submission scene-name normalization for both `sceneName` and `scene_name`.
- [x] Re-run focused regression tests and compile checks.
- [x] Deploy production and re-run custom-domain generate -> render -> MP4 closed-loop.
- [x] Record final evidence in `tasks/codex-app-handoff.md`.
- [x] Confirm the bad video was not merely low resolution: Chinese labels rendered as tofu/codepoint boxes.
- [x] Identify the root cause at the production image boundary: Render was using the repo-root `Dockerfile`, which did not install CJK fonts.
- [x] Install `fontconfig`, `fonts-noto-cjk`, and `fonts-noto-color-emoji` in the root Render image.
- [x] Add safe `/health` render diagnostics proving the runtime can match `Noto Sans CJK SC`.
- [x] Deploy Render and verify `/health` reports `render.cjk_font.ok=true`.
- [x] Run a live production font-probe render and visually confirm Chinese text is readable.
- [x] Run a live production prompt -> render -> MP4 -> frame extraction check for `可视化帕累托最优过程。`.

## Review

The "successful but terrible quality" result was a real production defect. The previous production MP4 completed, but extracted frames showed Chinese labels as missing-glyph boxes even though the generated code contained the Aegis CJK font patch. The root cause was that the live Render service can build from the repository root `Dockerfile`; that file did not install CJK fonts or set `MANIM_CJK_FONT`, while `render_backend/Dockerfile` had already been fixed. Commit `184295d` synchronizes the root image with the render backend image for CJK font support and adds non-sensitive font diagnostics to Render `/health`. Focused regression tests passed with `59 passed`, Python compile checks passed, and `git diff --check` passed. After pushing and triggering Render deploy, production `/health` returned `render.quality=-ql`, `render.cjk_font.ok=true`, and matched `NotoSansCJK-Regular.ttc`.

Post-deploy live checks passed. The production font probe job `a511d7ab-58d3-41c9-ac6c-b404bfb73b2f` rendered a readable Chinese MP4; frame extraction at `/tmp/aegis-font-probe-fixed/font_probe.png` shows default, sans, Noto, and serif Chinese text all readable. The full friend-flow prompt `可视化帕累托最优过程。` generated request `20260522-174814-vercel`, returned the stable Pareto fallback with 6 `self.play(...)`, 6 `self.wait(...)`, and the CJK patch, then rendered job `2b70b836-e8b6-4756-93b2-584d92464b01` through production as `render_mode=segmented`, progressing `0/2 -> 1/2 -> concatenating -> done`. The final Supabase MP4 returned HTTP 200, `content-type: video/mp4`, `content-length: 184325`, duration about 10.07s, and extracted frames at `/tmp/aegis-pareto-fixed/frame_5s.png` and `/tmp/aegis-pareto-fixed/frame_9s.png` show readable Chinese labels and a clear Pareto feasible-set/frontier explanation.

Custom-domain closure also passed on 2026-05-23 CST. `manim.yishuziyu.cn` was moved from the stale/unconfigured `aegis-manim` Vercel project to the canonical `manim-main` project. Production deploy `dpl_Cq2xGXKESTtx5VbH6CK2djCGzbdA` was aliased to `https://manim.yishuziyu.cn`. Live checks returned `/api/health` HTTP 200 and `/api/render/status/not-a-real-job` HTTP 404 from Render, proving the domain reaches the configured gateway and Render proxy. A full custom-domain prompt `可视化帕累托最优过程。` generated request `20260523-060807-vercel`, submitted render job `fd693826-882c-4c88-8cd3-963aa5d61809` as `render_mode=segmented`, progressed `0/2 -> 1/2 -> done 2/2`, and produced a Supabase MP4 with `HEAD 200`, `content-type: video/mp4`, `content-length: 184325`, duration about 10.07s at 854x480. Extracted frame `/tmp/aegis-fd693826-frame.png` shows readable Chinese title, axis labels, and explanation text.

# Community Works MVP Cloud Closure

- [x] Add community search-before-generate, publish, rating, and reuse APIs.
- [x] Keep Render credentials server-side by routing community calls through same-origin Vercel/local proxies.
- [x] Add dedicated Supabase community schema for the target design.
- [x] Add a compatibility fallback that stores published works in existing `render_jobs.metadata` when the community tables are not migrated yet.
- [x] Re-run focused backend/frontend/deploy regression tests and syntax checks.

## Review

The community works MVP now has two persistence paths. The preferred path uses the new `community_works`, `community_work_ratings`, and `community_work_events` tables. The production-safe fallback uses the already-deployed `render_jobs` table by marking completed jobs with `metadata.community_status = "published"` and storing prompt, score, ratings, and reuse counters in metadata. This matters because the live Supabase project currently has `render_jobs` but does not yet expose the new community tables through PostgREST. Focused verification passed with `65 passed`, Python compile checks, frontend JavaScript syntax checks, and `git diff --check`.

Render production closure passed after commit `bfb1af1`: direct Render `/health` returned HTTP 200 with `supabase.ok=true` and CJK font ok, direct Render `/community/works` published completed render job `fd693826-882c-4c88-8cd3-963aa5d61809` with HTTP 201, direct Render `/community/search?q=可视化帕累托最优过程。` returned `hit=true`, and direct Render reuse/rating calls both returned HTTP 200. The remaining cloud blocker is Vercel production deployment, not Render or Supabase: `manim.yishuziyu.cn/api/community/works` still returns the Vercel gateway JSON 404 because `vercel.json` had been missing community rewrites. Commit `2a7274a` adds those rewrites and a regression test, but both local Vercel CLI deploy and GitHub Actions Deploy Pipeline are blocked by an invalid Vercel token/secret. Once the Vercel token is rotated, redeploy production and rerun the same custom-domain publish/search/reuse/rating check.

# Three-Round Production Closure

- [x] Fix custom-domain Vercel ASGI community routes so `/api/community/*` reaches Render.
- [x] Restart pending/running Render jobs after instance restarts instead of failing immediately.
- [x] Expose non-sensitive Render recovery/storage diagnostics through `/health`.
- [x] Retry Supabase Storage upload after completed renders.
- [x] Add compatibility repairs for generated `Axes(..., x_label=..., y_label=...)` and `.set.stroke(...)`.
- [x] Redeploy Vercel production and Render production.
- [x] Run three consecutive production closed-loop tests from `https://manim.yishuziyu.cn`.

## Review

Production closure passed on 2026-05-23 CST after commit `52def3f`. Vercel production deploy `dpl_BbKuDdPCGv5yXKqAdu3ob9XEKxsF` is READY and aliased to `https://manim.yishuziyu.cn`. Render production `/health` confirmed `render.recovery.max_restart_attempts=2`, `render.storage.upload_retries=3`, CJK font OK, and Supabase OK. Local regression verification passed with `91 passed`, Python compile checks, and `git diff --check`.

The required three-round production closed-loop test passed in 481 seconds. Each round called production `/api/health`, `/api/generate` with `trial-kimi-priority`, `/api/render`, polled `/api/render/status` to `done`, verified the produced Supabase MP4 with a byte-range request, published the completed render to the community repository, searched it back by title, recorded reuse, and saved a rating. Passing jobs and works were `33ac63ba-988d-4f2b-b559-14a1f96cbb09`, `aa708609-f8bf-47e2-9f16-e85c4cf25847`, and `21a47b18-14c6-4a1d-b85c-ddc3962f3046`.

# Cloud Run Jobs Render Executor

- [x] Add a Cloud Run Jobs executor that preserves the current Vercel/Supabase async render contract.
- [x] Keep the existing local/Render thread executor as the default fallback.
- [x] Add a Cloud Run worker entrypoint that pulls a Supabase `render_jobs` row by `job_id`, renders Manim, uploads the MP4, and updates status.
- [x] Expose non-secret executor diagnostics through `/health`.
- [x] Document required Cloud Run env vars and deployment flow.
- [x] Add focused regression tests for dispatch payloads, fallback behavior, and worker completion/failure status.
- [x] Run focused tests, compile checks, and diff checks.

## Review

The render backend now has a production-shaped Cloud Run Jobs execution path while preserving the existing public contract. `MANIM_EXECUTOR=local` remains the default, so current Render behavior is unchanged unless the env is explicitly switched. With `MANIM_EXECUTOR=cloud_run`, `/render-async` still writes the Supabase `render_jobs` row and returns the same `job_id` / `/status` / `/download` contract, but dispatches an existing Cloud Run Job through the Cloud Run Jobs API. The dispatch payload passes only `AEGIS_RENDER_JOB_ID` and `AEGIS_RENDER_MODE`; generated Manim code stays in Supabase instead of being pushed into env vars. The Cloud Run Job container runs `python cloud_run_worker.py`, fetches the persisted job, renders through the existing Manim path, uploads to Supabase Storage, and updates the same status row.

The current machine does not have `CLOUD_RUN_PROJECT`, `CLOUD_RUN_REGION`, `CLOUD_RUN_JOB_NAME`, or Google credentials configured, so no real Google Cloud job was created from this workstation. Verification covered the code path without touching production credentials: `pytest -o addopts='' tests/test_render_backend_persistence.py -q` passed with `42 passed`; the broader Aegis regression set passed with `109 passed`; `python -m py_compile render_backend/app.py render_backend/cloud_run_executor.py render_backend/cloud_run_worker.py render_backend/supabase_client.py` passed; and `git diff --check` passed.

# Economics Fallback Quality Fix

- [x] Reproduce the poor production quality with a real economics prompt through the visible in-app browser.
- [x] Verify the old production result completed but used `vercel-generated-fallback` and rendered a generic step-card instead of a supply-demand diagram.
- [x] Add a tax-wedge/deadweight-loss fallback scene with supply and demand curves, buyer/seller prices, tax revenue rectangle, and deadweight-loss triangle.
- [x] Add regression coverage for the topic-specific fallback.
- [x] Render the new fallback locally with Manim and inspect an extracted frame.
- [x] Deploy Vercel production and rerun the custom-domain browser closed-loop.

## Review

The visible in-app browser production test on 2026-05-24 CST reproduced the real issue: the site could return an MP4, but the generated code fell back to `vercel-generated-fallback` and produced a generic "问题/变量/关系/变化/结论" card. That passed the technical render path but failed the teaching-quality bar for the economics prompt. The production MP4 for job `f58ef980-0ee4-4b30-89dc-d5ef0206f616` was 854x480, about 7.0s, and frame extraction showed the title truncated to "tax wedge de" with no supply-demand diagram.

Commit-in-progress adds a deterministic tax-wedge fallback in `api/index.py`. When the trial model is slow or unavailable and the prompt mentions tax wedge, deadweight loss, supply/demand, buyer price, seller price, or Chinese equivalents, the fallback now renders a real economics diagram: demand curve, supply curve, pre-tax equilibrium, tax wedge, buyer/seller price lines, tax revenue rectangle, and deadweight-loss triangle. Focused verification passed with `tests/test_aegis_public_trial.py` at `19 passed`; `python -m py_compile api/index.py` passed; and a direct local Manim render produced a 854x480, about 10.93s MP4 with a correct extracted frame at `/tmp/aegis-tax-wedge-media/tax_wedge_frame_6s.png`.

Vercel production deploy `dpl_8KnWbkHtk9wNTznrQR3nfCAPEDAR` is READY and aliased to `https://manim.yishuziyu.cn`. Post-deploy production `/api/generate` returned the new fallback code containing "税收楔子与无谓损失", "需求 D", "供给 S", "税收收入", and "无谓损失". The final visible in-app browser test on `https://manim.yishuziyu.cn` submitted the same real economics prompt, generated request `20260523-180319-vercel`, rendered job `6435fc8a-9dc5-4249-9292-cb232e640dc1`, completed in the page, and produced Supabase MP4 `GeneratedScene_segmented.mp4` with HTTP 200, `content-type: video/mp4`, 288202 bytes, 854x480, about 10.93s. Extracted frame `/tmp/aegis-fixed-prod/frame_6s.png` shows the intended supply-demand tax-wedge diagram.

# Kimi/MiniMax Trial Tuning

- [x] Use parallel subagents to research Kimi Coding Plan integration and MiniMax quality tuning.
- [x] Switch Kimi Coding Plan to the official OpenAI-compatible `https://api.kimi.com/coding/v1/chat/completions` path with `kimi-for-coding`.
- [x] Add non-sensitive Kimi request cache/safety identifiers.
- [x] Increase provider output budgets and provider-specific public trial timeouts.
- [x] Feed every public trial generation through a teaching brief and static precheck/repair before fallback.
- [x] Keep MiniMax on the documented Anthropic-compatible CN endpoint.
- [x] Expose safe `/api/health` diagnostics for provider configured state and timeout values.
- [x] Add regression tests for provider endpoints, Kimi metadata, timeout routing, precheck repair, and safe diagnostics.
- [x] Deploy production and run API plus in-app browser closed-loop tests with a real economics prompt.

## Review

Kimi Coding Plan and MiniMax are now separated as two explicit reliability lanes. Kimi Code uses the official OpenAI-compatible coding endpoint and model ID, with non-secret `prompt_cache_key` and `safety_identifier`; MiniMax remains on the Anthropic-compatible `https://api.minimaxi.com/anthropic/v1/messages` endpoint and gets a larger default output budget. Public trial prompts now always include the local teaching brief, plus a hosted-quality contract requiring a real teaching scene instead of placeholder animation. Generated code is checked with the existing Manim static precheck and a topic-quality gate for tax-wedge prompts; blocking issues trigger a repair request before the system drops to fallback. The fallback remains necessary as the final safety net because production diagnostics after deploy `dpl_7gxrvHXVoCs3wBTeWd1g3mzM6hdX` showed both keys configured, while repeated live Kimi attempts still returned `access`.

Focused verification passed with `41 passed` across provider, public trial, Manim knowledge, and prompt-context tests; `python -m py_compile core/llm_providers.py api/index.py` passed; and `git diff --check` passed. A full `pytest -o addopts='' -q` run was intentionally stopped after entering broad Manim upstream tests with many unrelated failures and slow cases. Production `/api/health` now reports `trialProviders.configured.kimiCode=true`, `trialProviders.configured.miniMax=true`, and timeouts `{kimi:55, kimiRepair:35, miniMax:120, miniMaxRepair:90}` without exposing secrets. Public soft render budget is now 24 `self.play` calls, with a 40-play hard gate for extreme scripts.

Closed-loop production acceptance passed through both paths. The durable fallback-quality path passed with API render job `d1f53c4a-2963-43e9-aeaa-de349fb090c6`, which completed as segmented `0/2 -> 1/2 -> done 2/2`, produced a Supabase MP4 with 288202 bytes, 854x480, about 10.93s, and extracted frame `/tmp/aegis-model-tuned-frame-6s.png` shows the intended tax-wedge supply/demand diagram. The visible in-app browser test on `https://manim.yishuziyu.cn` also passed: request `20260524-042530-vercel` rendered video URL `https://lnbalcskhcnkrtlqpgku.supabase.co/storage/v1/object/public/manim-videos/17b56d24-281c-4eb6-b860-d8db7d743171/GeneratedScene_segmented.mp4`, duration about 10.93s, and extracted frame `/tmp/aegis-browser-frame-6s.png` shows readable Chinese labels and the correct economics diagram. After relaxing MiniMax timeout and soft budget, live request `20260524-050844-vercel` showed Kimi failing with `access` but MiniMax backup returning `server-managed-trial` / `vercel-generated-code` with 24 `self.play` calls and all required tax-wedge objects. A later repeat still fell back after `kimi-code:access, minimax-coding-cn:timeout`, so the friend-facing experience is usable, but Kimi remains an upstream access problem and MiniMax remains variable under live latency.
