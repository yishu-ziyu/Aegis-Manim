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
- Vercel public trial generation now checks returned code against hosted-render limits and automatically regenerates if it has too many `self.play(...)` or `LaggedStart(...)` calls.

Verification so far:

- The original failed job code was passed through the local compatibility function: before patch it had `Sector(outer_radius=...)`; after patch it no longer had that pattern and did have `Sector(radius=...)`.
- Vercel deployment `dpl_HwgD3JgkQShuV2ZBY2g3Rie3M3LH` reached READY and was aliased to `https://manim-main.vercel.app`.
- Production `/api/generate` request `20260522-142925-vercel` returned generated code without `Sector(outer_radius=...)`.
- Production `/api/render` accepted that generated code with HTTP 202 and job `9d35adec...`, but Render failed after 180s with `Rendering timed out after 180s`, showing the remaining cloud risk is scene complexity/runtime budget.
- Fresh local proxy smoke on ports 8016/5014 submitted a minimal animated scene through `/api/render`, polled to `done`, and downloaded `video/mp4` with 7160 bytes.
- `pytest -o addopts='' tests/test_aegis_runtime_compatibility.py tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py -q` passed with `31 passed`.
- `pytest -o addopts='' tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_render_backend_persistence.py tests/test_deploy_cloud_schema.py tests/test_aegis_manim_knowledge.py -q` passed with `61 passed`.
- After local proxy and prompt-budget fixes, `pytest -o addopts='' tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_render_backend_persistence.py tests/test_deploy_cloud_schema.py tests/test_aegis_manim_knowledge.py -q` passed with `62 passed`.
- After adding the Vercel budget regeneration gate, `pytest -o addopts='' tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_render_backend_persistence.py tests/test_deploy_cloud_schema.py tests/test_aegis_manim_knowledge.py -q` passed with `63 passed`.
- `python -m py_compile core/manim_agent.py core/web_app.py api/index.py` passed.
- `git diff --check` passed.
- `bash -n scripts/start_aegis_local.command` passed.

## 2026-05-22 Segmented Render Quality Recovery

User direction:

- Do not permanently reduce teaching quality just to fit a small Render worker.
- Prefer either a better rendering platform later, or split large renders into smaller batches and recombine them.

Implementation queued:

- Render Backend async jobs now accept `render_mode`: `auto`, `single`, or `segmented`.
- Vercel and local Web proxy now submit `render_mode: auto` by default.
- `auto` keeps short scenes on the existing single-render path.
- Longer scenes are split by generated Manim event count (`self.play(...)` / `self.wait(...)`), rendered with Manim `-n start,end`, then concatenated with `ffmpeg` into one final MP4.
- Only the final MP4 is copied/uploaded; partial segment files remain temporary.
- Segment state is stored in the existing `render_jobs.metadata` JSON field, so no Supabase schema migration is needed.
- `/status/<job_id>` now exposes `render_mode`, `stage`, `progress`, and `segments`.
- Public generation limits were relaxed from short-preview limits to segmented-render friendly limits:
  - hard gate: at most 24 `self.play(...)`
  - hard gate: at most 3 `LaggedStart(...)`
  - target: 45-120 second multi-step teaching scenes

Verification:

- `pytest -o addopts='' tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_render_backend_persistence.py tests/test_deploy_cloud_schema.py tests/test_aegis_manim_knowledge.py -q` passed with `68 passed`.
- `python -m py_compile render_backend/app.py render_backend/supabase_client.py api/index.py core/web_app.py` passed.
- `git diff --check` passed.
- Local real segmented render smoke passed: a 9-animation scene rendered through `render_mode=segmented`, concatenated successfully, and produced `render_backend/outputs/segmented-smoke_GeneratedScene.mp4` with 15561 bytes.

Remaining deployment check:

- Completed. Commit `262c14c` was pushed to `origin/main`.
- Vercel production deployment `dpl_9cQ6oEpkQhgL2v6x5ZWPvvEbkiWy` reached READY and was aliased to `https://manim-main.vercel.app`.
- Render deploy hook returned HTTP 202.
- Render `/health` returned HTTP 200 with `supabase.ok=true`.
- Vercel `/api/render/status/not-a-real-job` returned the expected Render JSON 404.
- Live segmented public render passed:
  - job `c91b6fef-5e99-4db1-8025-99978affb6eb`
  - submit payload used `renderMode=auto`
  - submit response returned `render_mode=segmented`
  - status reported `stage=rendering_segment`, progress `0/2`, then `1/2`, then `done 2/2`
  - download payload contained a final `video_url`

## 2026-05-23 Production Closure: Friend-Usable Cloud Rendering

User direction:

- Treat the public site as not done until a friend can open it, generate an explanation, render video, and receive a playable MP4 without configuring keys.
- Compare against ManimCat/community-style architecture and stop relying on one long synchronous request.

Root causes confirmed:

- A previous full closed-loop attempt failed because Render restarted while an async job was running; pending/running Supabase jobs were restored into cache but not restarted.
- A second attempt showed `/api/generate` could wait too long on a trial model response before render even started.
- A fallback scene with a Python `for` loop looked short by static `self.play(...)` count but expanded to many runtime animations and timed out after 180 seconds on Render.

Fixes shipped:

- Public trial model calls now use bounded HTTP timeouts:
  - normal generation: `PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS`, default 25 seconds
  - budget-repair generation: `PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS`, default 15 seconds
- Public default provider is now `trial-minimax-direct`; browser provider storage key moved to `aegis.provider.public.v4` so old Kimi-priority browser state does not keep users on the slower path.
- If all server-managed trial providers are missing/slow/failing, `/api/generate` now returns a deterministic stable Manim template instead of failing the user flow.
- Stable fallback template is loop-free and uses short `FadeIn/Create` animations, so static event counting matches runtime behavior more closely.
- Render Backend startup recovery now restarts recovered pending/running Supabase jobs through a deduped background render thread.
- The Web UI auto-resubmits once when a render job fails with the Render restart/resubmit message.
- Automatic segmentation defaults were tightened for constrained workers:
  - `MANIM_SEGMENT_RENDER_THRESHOLD` default: 2 events
  - `MANIM_SEGMENT_RENDER_SIZE` default: 2 events

Local verification:

- `pytest -o addopts='' tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_render_backend_persistence.py tests/test_deploy_cloud_schema.py tests/test_aegis_manim_knowledge.py tests/test_aegis_llm_providers.py -q` passed with `76 passed`.
- `python -m py_compile core/llm_providers.py core/manim_agent.py api/index.py core/web_app.py render_backend/app.py render_backend/supabase_client.py` passed.
- `python -m py_compile api/index.py render_backend/app.py` passed after the fallback/threshold tightening.
- `git diff --check` passed.

Deployment:

- Commit `f58fca8` pushed to `origin/main`.
- Commit `d392e1b` pushed to `origin/main`.
- Vercel production deployment `dpl_7ySJjZppppHrNjhpfDD638JHomqf` reached READY and was aliased to `https://manim-main.vercel.app`.
- Render deploy hook returned HTTP 202.
- Render `/health` returned HTTP 200 with `supabase.ok=true`.

Final live public closed-loop:

- `POST https://manim-main.vercel.app/api/generate`
  - request `20260522-162045-vercel`
  - provider `trial-minimax-direct`
  - model `MiniMax 稳定试用`
  - generated scene `LinearGrowthGap`
  - generated code: 2112 chars, 6 `self.play(...)`, 5 `self.wait(...)`, 0 `LaggedStart(...)`
- `POST https://manim-main.vercel.app/api/render`
  - job `5bbfac97-c75f-4edc-a71c-09f630e4c86c`
  - response `render_mode=segmented`
  - status progressed `rendering_segment 0/2 -> rendering_segment 1/2 -> concatenating 2/2 -> done 2/2`
  - final MP4 URL: `https://lnbalcskhcnkrtlqpgku.supabase.co/storage/v1/object/public/manim-videos/5bbfac97-c75f-4edc-a71c-09f630e4c86c/LinearGrowthGap_segmented.mp4`
  - `HEAD` returned HTTP 200, `content-type: video/mp4`, `content-length: 134467`

Fallback live render smoke:

- Submitted the new stable fallback template directly through production `/api/render`.
- Job `4c5e740f-c3cc-4cee-b75a-bea272065034` reached `done`.
- Final MP4 URL: `https://lnbalcskhcnkrtlqpgku.supabase.co/storage/v1/object/public/manim-videos/4c5e740f-c3cc-4cee-b75a-bea272065034/GeneratedScene.mp4`
- `HEAD` returned HTTP 200, `content-type: video/mp4`, `content-length: 37144`

Conclusion:

- As of this check, the public cloud path is usable for the intended friend flow: open `https://manim-main.vercel.app`, use the server-managed trial model, render through Render, and receive a playable Supabase-hosted MP4.
- Remaining product risk is Render free/small-worker capacity. For stronger production reliability, the next architecture step should be a queue/worker platform such as Cloud Run Jobs or Modal, following the same async job-status-output pattern used by ManimCat-like systems.

## 2026-05-23 Production Quality Fix: Chinese Font Runtime

Problem:

- A later production run technically succeeded, but the MP4 was not acceptable: extracted frames showed Chinese text as missing-glyph boxes/tofu.
- The generated code already contained the Aegis CJK font patch, so this was not a prompt or Supabase issue.

Root cause:

- Render can build from the repository root `Dockerfile`.
- The root `Dockerfile` did not install `fontconfig`/`fonts-noto-cjk` or set `MANIM_CJK_FONT`; only `render_backend/Dockerfile` had those packages.
- Manim/Pango therefore had no CJK glyphs in the live container, even when the code requested a CJK font.

Fix:

- Commit `184295d` pushed to `origin/main`.
- Root `Dockerfile` now installs:
  - `fontconfig`
  - `fonts-noto-cjk`
  - `fonts-noto-color-emoji`
  - `fc-cache -f`
- Root `Dockerfile` now sets:
  - `MANIM_CJK_FONT=Noto Sans CJK SC`
  - `MANIM_RENDER_QUALITY=-ql`
- Render `/health` now includes safe, non-secret render diagnostics:
  - `render.quality`
  - `render.cjk_font.configured`
  - `render.cjk_font.matched`
  - `render.cjk_font.ok`

Verification:

- Focused tests passed: `pytest -o addopts='' tests/test_render_backend_persistence.py tests/test_aegis_runtime_compatibility.py tests/test_aegis_public_trial.py -q` -> `59 passed`.
- Compile and diff checks passed:
  - `python -m py_compile render_backend/app.py api/index.py core/manim_agent.py`
  - `git diff --check`
- Render deploy hook returned HTTP 202.
- Production `/health` returned:
  - `render.quality=-ql`
  - `render.cjk_font.ok=true`
  - `render.cjk_font.matched=NotoSansCJK-Regular.ttc: "Noto Sans CJK SC" "Regular"`
- Production font probe job `a511d7ab-58d3-41c9-ac6c-b404bfb73b2f` reached `done`; extracted frame `/tmp/aegis-font-probe-fixed/font_probe.png` shows Chinese text readable for default/sans/Noto/serif rows.
- Full production friend-flow check passed:
  - prompt: `可视化帕累托最优过程。`
  - generate request: `20260522-174814-vercel`
  - model: `stable-template-fallback`
  - code: 6 `self.play(...)`, 6 `self.wait(...)`, CJK patch present
  - render job: `2b70b836-e8b6-4756-93b2-584d92464b01`
  - status: `rendering_segment 0/2 -> rendering_segment 1/2 -> concatenating -> done`
  - final MP4: HTTP 200, `content-type: video/mp4`, `content-length: 184325`, duration about 10.07s
  - extracted frames `/tmp/aegis-pareto-fixed/frame_5s.png` and `/tmp/aegis-pareto-fixed/frame_9s.png` show readable Chinese and a clear Pareto feasible-set/frontier explanation.

Current conclusion:

- The cloud site is no longer only "technically successful"; the production video is now visually readable for Chinese text.
- Render still runs at `-ql` because the small/free worker has repeatedly failed or stalled under heavier quality/scene budgets. Higher-resolution production should move to a stronger worker platform or paid Render capacity rather than hiding the issue by forcing medium quality on the current worker.

## 2026-05-23 Custom Domain Production Closure

User-facing goal:

- A friend should be able to open the shared custom domain, submit a natural-language prompt, and receive a playable rendered MP4 without configuring model keys, Supabase, or Render.

Domain finding:

- `manim.yishuziyu.cn` was still attached to a stale/unconfigured Vercel project named `aegis-manim`.
- The canonical project with the configured production env is `manim-main`.
- The custom domain was moved onto `manim-main`; do not move it back to `aegis-manim`.

Fixes shipped in this pass:

- Vercel and local proxy render submissions now normalize both `sceneName` and `scene_name`.
- The gateway detects the actual generated `Scene` subclass before submitting to Render.
- Render backend MP4 discovery now handles segmented Manim output filenames and falls back to the latest final MP4 outside `partial_movie_files`.
- Generated `axes.get_axis_labels(x_label="...", y_label="...")` string labels are rewritten to explicit `Text(...)` labels so cloud Manim does not require `dvisvgm`/LaTeX for axis labels.

Deployment:

- Vercel production deploy `dpl_Cq2xGXKESTtx5VbH6CK2djCGzbdA` reached READY.
- `https://manim.yishuziyu.cn` is aliased to that `manim-main` deployment.
- Render health is live at `https://aegis-manim.onrender.com/health` with `supabase.ok=true` and CJK font diagnostics healthy.

Final custom-domain closed-loop:

- `GET https://manim.yishuziyu.cn/api/health` returned HTTP 200.
- `GET https://manim.yishuziyu.cn/api/render/status/not-a-real-job` returned the expected Render JSON 404, proving the proxy reaches Render and authenticates.
- `POST https://manim.yishuziyu.cn/api/generate`
  - prompt: `可视化帕累托最优过程。`
  - request: `20260523-060807-vercel`
  - provider path: stable fallback after server-managed trial model slowdown/unavailability
  - scene: `GeneratedScene`
- `POST https://manim.yishuziyu.cn/api/render`
  - job: `fd693826-882c-4c88-8cd3-963aa5d61809`
  - render mode: `segmented`
  - status progress: `0/2 -> 1/2 -> done 2/2`
  - final MP4 URL is in the Supabase `manim-videos` bucket under project ref `lnbalcskhcnkrtlqpgku`
- MP4 verification:
  - `HEAD` returned HTTP 200
  - `content-type: video/mp4`
  - `content-length: 184325`
  - `ffprobe`: 854x480, duration about 10.07s
  - extracted frame `/tmp/aegis-fd693826-frame.png` shows readable Chinese title, axis labels, and explanation text.

Current conclusion:

- The custom-domain cloud path is usable now for the intended friend flow.
- The successful custom-domain run used the stable fallback because the server-managed trial model was slow/unavailable during that request. That is intentional resilience: the user still gets a rendered teaching video instead of a failed flow. Richer model-specific scene quality still depends on provider responsiveness.
- GitHub Actions deploy forcing is not reliable yet because Vercel and Render deploy-hook secrets are currently missing/empty in GitHub. Local Vercel deploy was used for this closure; Render remains reachable and healthy. If future backend changes must be force-deployed through CI, configure those GitHub secrets or trigger Render from the dashboard.

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
