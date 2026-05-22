# Codex App Handoff: Aegis-Manim Backend Wiring

## Current Architecture

- Vercel is the public gateway for `manim-main`.
- Render is the long-running Manim rendering backend at `https://aegis-manim.onrender.com`.
- Supabase stores async render job state and rendered videos.
- Supabase project is `Aegis-Manim`, ref `lnbalcskhcnkrtlqpgku`.

## What Is Done

- Supabase schema was applied in the Supabase SQL Editor.
- Supabase readiness passed from local env:
  - `render_jobs`: 200
  - `job_logs`: 200
  - `manim-videos` bucket: 200
- Local `.env.local` now points at `https://lnbalcskhcnkrtlqpgku.supabase.co`.
- Render `/health` previously returned `{"supabase":{"ok":true,"status":200}}`, proving Render can reach Supabase.
- The correct Render `MANIM_API_KEY` was captured from Render Dashboard and written locally as `RENDER_BACKEND_API_KEY`.
- That key was verified directly against Render: `/status/not-a-real-job` returned 404 instead of 403, proving authentication is valid.
- Vercel production env was updated:
  - `RENDER_BACKEND_URL=https://aegis-manim.onrender.com`
  - `RENDER_BACKEND_API_KEY` set to the Render `MANIM_API_KEY`
- Vercel was redeployed:
  - deployment `dpl_3n55LxP1PjYvw14WdsXZKTrGzvU1`
  - URL `https://manim-main-7c8i6zt5v-sheldons-projects-6ef373e4.vercel.app`
  - alias `https://manim-main.vercel.app`
- Vercel `/api/health` returned ok after redeploy.

## Current Status

Updated 2026-05-22 17:51 CST from Codex App.

The previous 30-second timeout blocker has recovered on live checks:

- `https://manim-main.vercel.app/api/render/status/not-a-real-job`
- `https://aegis-manim.onrender.com/health`

Current verified behavior:

- Render `/health` returned HTTP 200 in 2.576s with `status=ok` and `supabase.ok=true`.
- Vercel `/api/render/status/not-a-real-job` returned HTTP 404 in 1.955s with `{"error": "Job not found"}`, which proves the Vercel proxy reaches Render and authenticates.
- Vercel `/api/health` returned HTTP 200 in 1.059s.
- Supabase read-only readiness still passes for `render_jobs`, `job_logs`, and the `manim-videos` bucket.
- Focused regression tests passed: `30 passed in 1.40s`.

Render dashboard logs were attempted in Chrome at `https://dashboard.render.com/web/srv-d8786u0g4nts73dkqicg/logs?r=1h`, but the page did not expose readable log content through the current Codex App/Chrome accessibility surface. No local `render` CLI or `RENDER_API_KEY`/`RENDER_TOKEN` env was available, so logs were not fetched from CLI/API in this pass.

## Latest Production Acceptance

Updated 2026-05-22 18:18 CST from Codex App.

Goal checked: a public user can use `https://manim-main.vercel.app` without entering a model key, generate Manim code, send it to Render, and receive a playable MP4.

Verified production state:

- Render dashboard Events showed the env-update deploy went live for service `srv-d8786u0g4nts73dkqicg` at 2026-05-22 18:08 CST.
- Render production env now points to the new Supabase project ref `lnbalcskhcnkrtlqpgku`; do not revert to the old ref.
- Vercel production redeployed successfully:
  - deployment `dpl_CDybstzBYL5SH8GygsWDmA8Hcfa6`
  - alias `https://manim-main.vercel.app`
- Vercel `/api/health` returned HTTP 200 after redeploy.
- Live public generation check passed:
  - `POST https://manim-main.vercel.app/api/generate`
  - provider `trial-minimax-direct`
  - result HTTP 200 with generated code, no client API key required.
- Live public render check passed:
  - `POST https://manim-main.vercel.app/api/render`
  - job prefix `c20b8fff`
  - final status `done`
  - fallback download response contained a `video_url`
  - `HEAD` on the video URL returned HTTP 200, `content-type: video/mp4`, `content-length: 34189`
  - video URL used Supabase ref `lnbalcskhcnkrtlqpgku`
  - video URL did not use old ref `qrmmlolsslnxiamznicf`
- A direct render smoke also passed after the Render env update:
  - job prefix `e4f26a9f`
  - final status `done`
  - video `HEAD` returned HTTP 200, `content-type: video/mp4`, `content-length: 27263`

Fix applied during this pass:

- Vercel public HTML fallback now parses `/api/render/download/<job_id>` JSON and uses `video_url` instead of assigning JSON directly to `<video src>`.
- Vercel gateway has a defensive helper to extract safe `http(s)` video URLs from Render download payloads.
- Focused regression tests passed after the fix: `28 passed in 1.24s`.
- `git diff --check` passed.

Remaining note:

- Render `/status/<job_id>` currently may still omit `video_url`; the public page now handles that by reading the download payload. A local backend-side improvement also exposes `video_url` on completed status responses, but the production acceptance above does not depend on it.

## 2026-05-22 Render Timeout Follow-up

Observed issue:

- Browser showed `渲染超时，请稍后手动刷新检查。`
- The visible request was `20260522-125248-vercel`.
- The generated class was `ParetoOptimalityScene`, while the scene input still showed `GeneratedScene`.

Findings:

- Render `/health` recovered and returned HTTP 200 with `supabase.ok=true`.
- Vercel `/api/render/status/not-a-real-job` returned the expected Render JSON 404, so proxy auth/reachability was healthy.
- The production page had been trying Render direct status first with the development API key; non-200 direct responses were ignored instead of falling back to `/api/render/status/<job_id>`, causing front-end timeout behavior.
- The public generate API returned the user-entered scene name rather than the actual generated `Scene` subclass, so generated classes such as `ParetoOptimalityScene` could be submitted as `GeneratedScene`.
- After fixing those two issues, a new production check returned `sceneName=ParetoOptimalityScene` and status polling through Vercel returned repeated HTTP 200.
- That new job `50f98770...` stayed `running`; Supabase showed `scene_name=ParetoOptimalityScene`, no `stderr`, no `error_message`, and no `video_path`, with `updated_at` stuck near job start. This points to a Render/Manim worker task running too long rather than a front-end polling failure.

Fixes queued:

- Public generation now detects the actual generated `Scene` subclass and returns it as `sceneName`.
- Public page status polling now falls back to `/api/render/status/<job_id>` whenever direct Render polling returns non-200.
- Render backend now launches Manim in its own process group and kills the group on timeout.
- Render backend timeout is configurable through `MANIM_RENDER_TIMEOUT_SECONDS` and defaults to 180 seconds.
- Orphan running-job threshold now defaults to render timeout + 60 seconds.
- Added `scripts/start_aegis_local.command` for a friend-friendly local acceleration path: cloud generation, local Manim rendering, browser auto-open.

Verification:

- `pytest -o addopts='' tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py tests/test_render_backend_persistence.py tests/test_deploy_cloud_schema.py tests/test_aegis_manim_knowledge.py -q` passed with `43 passed`.
- `git diff --check` passed.
- `python -m py_compile core/web_app.py render_backend/app.py api/index.py scripts/deploy_cloud.py scripts/verify_vercel_gateway.py scripts/verify_render_persistence.py` passed.
- `bash -n scripts/start_aegis_local.command` passed.
- Local launcher smoke passed on ports 8013/5013 with local `/api/health` OK.
- Commit `8e3dba6` was pushed to `origin/main`.
- Render deploy hook was triggered after pushing `8e3dba6`; Render `/health` returned HTTP 200 with `supabase.ok=true` after the trigger.

## Latest Follow-up: Manim Sector Failure and Windows Launcher

Latest screenshot status:

- Production page returned `渲染失败: Manim rendering failed`.
- Visible request was `20260522-141057-vercel`.
- Generated scene was `ParetoOptimalityScene`.

Findings:

- Render `/health` and Vercel `/api/health` remained healthy.
- Supabase job `4c66b30e...` failed with Manim runtime error from generated `Sector(outer_radius=1.5, ...)`.
- Concrete error: `AnnularSector.__init__() got multiple values for keyword argument 'outer_radius'`.
- The failing pattern is a current-Manim API compatibility issue: `Sector` should receive `radius=...`, while `AnnularSector` can still receive `outer_radius=...`.

Fixes queued:

- `apply_runtime_compatibility_fixes()` now rewrites `Sector(outer_radius=...)` to `Sector(radius=...)`.
- Regression coverage verifies `Sector` is rewritten and `AnnularSector` is not changed.
- Added `scripts/start_aegis_local_windows.bat` for Windows friends: cloud generation plus local Manim rendering, with no Supabase/server secrets embedded.
- Local Web now proxies `/api/render`, `/api/render/status/<job_id>`, and `/api/render/download/<job_id>` to the local Render Backend.
- Browser-side local Render calls now use the configured render API key instead of a hard-coded key.
- Mac and Windows launchers avoid a stale occupied render port when the user did not explicitly choose one.
- Generation prompts now require short, cloud-renderable scenes by default: 15-35 seconds, 4-7 `self.play` calls, sparse objects, and no dense/long animation patterns.

Verification so far:

- The original failed job code was passed through the local compatibility function: before patch it had `Sector(outer_radius=...)`; after patch it no longer had that pattern and did have `Sector(radius=...)`.
- Vercel deployment `dpl_HwgD3JgkQShuV2ZBY2g3Rie3M3LH` reached READY and was aliased to `https://manim-main.vercel.app`.
- Production `/api/generate` request `20260522-142925-vercel` returned generated code without `Sector(outer_radius=...)`.
- Production `/api/render` accepted that generated code with HTTP 202 and job `9d35adec...`, but Render failed after 180s with `Rendering timed out after 180s`, showing the remaining cloud risk is scene complexity/runtime budget.
- Fresh local proxy smoke on ports 8016/5014 submitted a minimal animated scene through `/api/render`, polled to `done`, and downloaded `video/mp4` with 7160 bytes.
- `pytest -o addopts='' tests/test_aegis_runtime_compatibility.py tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py -q` passed with `31 passed`.
- `pytest -o addopts='' tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_render_backend_persistence.py tests/test_deploy_cloud_schema.py tests/test_aegis_manim_knowledge.py -q` passed with `61 passed`.
- After local proxy and prompt-budget fixes, `pytest -o addopts='' tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_render_backend_persistence.py tests/test_deploy_cloud_schema.py tests/test_aegis_manim_knowledge.py -q` passed with `62 passed`.
- `python -m py_compile core/manim_agent.py core/web_app.py api/index.py` passed.
- `git diff --check` passed.
- `bash -n scripts/start_aegis_local.command` passed.

## Do Not Reopen These Questions

- Do not create another Supabase project unless the current project is deleted or explicitly rejected.
- Do not put Supabase service keys into Vercel unless there is new code that directly calls Supabase from Vercel. Current design keeps Supabase credentials in Render only.
- Do not use the old personal-site Supabase ref `qrmmlolsslnxiamznicf`.
- Do not print secrets in chat or terminal output.

## Next Checks

1. If the timeout recurs, check Render service logs for timeout, boot loop, worker hang, or cold start:
   - service id `srv-d8786u0g4nts73dkqicg`
   - dashboard URL `https://dashboard.render.com/web/srv-d8786u0g4nts73dkqicg`
2. Re-run:
   - `curl -sS -m 90 https://aegis-manim.onrender.com/health`
   - `curl -sS -m 90 https://manim-main.vercel.app/api/render/status/not-a-real-job`
3. Expected final healthy behavior:
   - Render `/health` returns status ok and `supabase.ok=true`.
   - Vercel proxy status for a fake job returns a JSON 404 from Render, not 403 and not timeout.
4. If Render is healthy but Vercel still times out, inspect Vercel logs for the latest deployment and confirm env values are present without trailing literal `\n`.

## Useful Verification Commands

```bash
python scripts/verify_render_persistence.py --external-read-only --env-file .env.local
pytest -o addopts='' tests/test_deploy_cloud_schema.py tests/test_render_backend_persistence.py tests/test_aegis_public_trial.py -q
git diff --check
vercel inspect manim-main-7c8i6zt5v-sheldons-projects-6ef373e4.vercel.app
```
