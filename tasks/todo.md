# Dual-Coding Generation Process Goal

# Image Understanding to Manim Visualization

- [x] Use grill-me to clarify the product boundary for image upload, image understanding, confirmation, and Manim visualization.
- [x] Record the confirmed specification in `docs/specs/image-understanding-visualization.md`.
- [x] Build a minimal probe to verify whether the existing Kimi Code / Kimi plan key can process image input.
- [x] If the probe succeeds, add `/api/vision/analyze` with structured Chinese JSON output.
- [x] Add frontend upload, paste, drag-and-drop, and mobile photo-pick entry points.
- [x] Add the Chinese understanding card with auditable analysis, free-text direction edits, and confirmation.
- [x] Feed the confirmed structured summary into the existing `/api/generate` flow.
- [x] Add a server-side real CLI image probe that can be run on ECS before opening the public image feature.
- [x] Add repeatable 3-5 image acceptance script for `/api/vision/analyze` through generate/render.
- [x] Run the 5-image Chinese economics acceptance set and record pass/fail evidence.
- [x] Add a production-safe remote `VISION_BACKEND_URL` proxy path for Vercel/public gateway.
- [x] Add a host-level `aegis_vision_server.py` so the ECS host can call the real logged-in CLI outside Docker.
- [x] Add a systemd installer for the host-level Vision Server.
- [x] Add a one-command ECS doctor script that probes real CLI image reading before installing Vision Server.
- [x] Add a local packaging script so pending Vision Server files can be uploaded to ECS as one archive.
- [x] Add a local push script that uploads the Vision Server package to ECS and runs the remote doctor.
- [x] Document the production image-understanding bridge in the ECS deploy guide and local AI workflow component.
- [x] Record explicit Agent Team call/reclaim/re-call boundaries for this production feature lane.
- [x] Add a full public image-to-render acceptance wrapper for the production website.
- [x] Decide production exposure: public, beta/whitelist, or hidden, based on verified production image-to-video acceptance results.

## Review

On 2026-05-26 CST, completed the grill-me product clarification for the image-understanding feature. The agreed MVP is: one image plus optional text, uploaded/pasted/dragged from desktop or selected from mobile camera/gallery; Kimi analyzes the image into a Chinese understanding card; the user confirms or adds free-text direction; then Aegis generates and renders a Manim teaching animation. First version does not store original images, does not embed the original image into the final video, does not support multi-image/PDF/document uploads, and does not add a new paid vision provider. The first implementation step is a real probe against the existing Kimi plan key; if that cannot read images, the public image entry must stay hidden.

On 2026-05-26 CST, integrated the first verifier sidecar review back into the main implementation. The push script now uploads and runs the remote doctor through one SSH session, the doctor persists the exact CLI binary and `KIMI_VISION_CLI_ARGS_JSON` that passed the image probe into `/opt/aegis/vision.env` before installing systemd, and the deploy/component docs now include a `vision.yishuziyu.cn -> 127.0.0.1:5050` reverse-proxy pattern. Agent Team is reclaimed until a real server doctor output exists; after that evidence arrives, re-call verifier lanes for Vercel env wiring, public-browser acceptance, and safety review.

The verifier sidecar then found one manual-doc footgun: a user could single-run `probe_kimi_vision_cli.py --args-json ...` and then run the installer directly, bypassing persistence of the tested args. The docs now route that branch back through `BINARY=... ARGS_JSON=... scripts/aegis_vision_server_doctor.sh`, so the service env and the verified CLI invocation stay aligned.

Follow-up hardening made the one-command push more robust for the user's Alibaba ECS connection behavior: the remote doctor now runs under `nohup`, writes `/opt/aegis/vision-doctor.log`, stores `/opt/aegis/vision-doctor.pid`, and prints the tail command. This prevents a dropped SSH session from killing the long CLI image probe or 5-image acceptance run.

Added `scripts/check_aegis_vision_server_update.sh` as the evidence-recovery command after push. It connects once, shows the doctor pid, tails `/opt/aegis/vision-doctor.log`, extracts pass/fail markers, prints `systemctl status aegis-vision.service`, and curls `http://127.0.0.1:5050/health` without exposing API keys.

Added `scripts/decide_aegis_vision_exposure.py` to make the production exposure decision evidence-driven. It reads the probe report, 3-5 case acceptance JSONL, and health endpoint. Passing server doctor vision-only evidence yields `beta`, not public; `public` is only emitted after full image -> generate -> render -> video acceptance passes.

Added `scripts/run_aegis_public_vision_acceptance.sh` as the public-site closure command. It generates the five Chinese economics fixtures, calls `scripts/production_vision_economics_acceptance.py` against `https://manim.yishuziyu.cn`, and intentionally does not pass `--skip-render`, so it validates image understanding, prompt generation, Manim render, video download, duration probing, and frame extraction. This script is the handoff point after the server doctor reaches `beta`; public exposure still waits for all five public records to show `ok=true`, `status=done`, `videoUrl`, and `videoBytes`.

On 2026-05-26 CST, direct authenticated HTTP probes against Kimi Code were rejected with coding-agent access gating, so the implementation pivoted to a real server CLI bridge instead of HTTP client spoofing. Added `/api/vision/analyze`, `core/vision_analysis.py`, `scripts/kimi_vision_cli_bridge.py`, and frontend upload/paste/drag/drop UI with a Chinese confirmation card. The browser flow was verified locally with a fake CLI command: image upload showed a Chinese IS-LM analysis, clicking “使用这个方向” wrote the Chinese suggested prompt back into the generation textarea. Verification passed with `python3 -m py_compile scripts/kimi_vision_cli_bridge.py core/vision_analysis.py core/web_app.py api/index.py app.py`, `node --check /tmp/aegis_web_app_inline.js`, `pytest -o addopts='' tests/test_aegis_vision_analysis.py tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py -q` returning 46 passed, and `git diff --check`. Remaining production gate: install/login a real Kimi/Codex/Claude CLI on the ECS host, set `KIMI_VISION_CLI_COMMAND`, then run 3-5 Chinese economics image tests end to end.

Follow-up in the same goal turn added a production exposure gate: `AEGIS_VISION_PUBLIC_ENABLED` must be set to `1` and a vision provider must be configured before the upload UI is visible or `/api/vision/analyze` executes. Until then the frontend field is hidden and the ASGI/local route returns `vision_feature_disabled`, so the public site cannot accidentally expose an unverified image upload path. Added regression tests for `scripts/kimi_vision_cli_bridge.py`, including prompt image-token forwarding and raw-text fallback. Verification now passes with `pytest -o addopts='' tests/test_aegis_vision_analysis.py tests/test_kimi_vision_cli_bridge.py tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py -q` returning 50 passed, plus browser automation with the gate enabled confirmed upload, Chinese analysis card, and prompt writeback.

Added `scripts/probe_kimi_vision_cli.py` so the ECS host can prove the real logged-in CLI reads a real Chinese economics image before production exposure. The probe calls the existing wrapper, validates Chinese economics content plus a non-empty `recommended_prompt`, fails if the CLI says it cannot see the image, and prints the exact production env exports only after success. This keeps the user's preferred route concrete: use the actual terminal CLI on the server, not a fake HTTP coding-agent identity. Follow-up hardening added `KIMI_VISION_CLI_ARGS_JSON`, so the same wrapper can call non-Kimi-shaped terminal tools such as Codex or Claude by changing the binary and argument array instead of changing the web API. Remaining gate: run this probe on `root@121.89.90.68` with a real economics screenshot, then run the 3-5 image acceptance set through the public web flow.

Added `scripts/production_vision_economics_acceptance.py` for the final image feature acceptance run. It accepts 3-5 local Chinese economics image files, posts each image to `/api/vision/analyze`, verifies Chinese economics content plus a usable `suggestedPrompt`, then by default sends that prompt through `/api/generate`, `/api/render`, status polling, video download, duration probing, and representative frame extraction. Use `--skip-render` only to isolate the vision route during server CLI debugging.

On 2026-05-26 CST, accepted the user's correction that the viable path is a real logged-in terminal CLI on the purchased ECS host, not an HTTP coding-agent impersonation. The CLI bridge and probe now support non-Kimi argument shapes through `KIMI_VISION_CLI_ARGS_JSON`, so the same web feature can call Kimi, Codex, Claude Code, or another server-installed terminal tool after that tool's real image syntax is verified. Focused verification passed with `python3 -m py_compile scripts/kimi_vision_cli_bridge.py scripts/probe_kimi_vision_cli.py tests/test_kimi_vision_cli_bridge.py tests/test_probe_kimi_vision_cli.py`, `pytest -o addopts='' tests/test_probe_kimi_vision_cli.py tests/test_kimi_vision_cli_bridge.py tests/test_production_vision_economics_acceptance.py tests/test_aegis_vision_analysis.py tests/test_aegis_web_ui.py tests/test_aegis_public_trial.py -q` returning 57 passed, `pytest -o addopts='' tests/test_aegis_ops_scripts.py -q` returning 3 passed, `git diff --check`, and a secret-pattern scan across the new CLI/probe/docs files. Full repository pytest still fails in the local Mac environment because `dvisvgm` and `standalone.cls` are not installed; the failures are concentrated in upstream Manim LaTeX/Tex tests and are not evidence against the image-to-CLI bridge. Remaining gate: run `scripts/probe_kimi_vision_cli.py` on `root@121.89.90.68` from an already logged-in real CLI session, then run the 3-5 image acceptance set.

On 2026-05-26 CST, generated five deterministic Chinese economics postgraduate-exam image fixtures under `/tmp/aegis-vision-economics-fixtures/`: tax wedge and deadweight loss, consumer choice and price effect, monopoly pricing and welfare loss, negative externality and Pigouvian tax, and IS-LM fiscal expansion. Updated `scripts/production_vision_economics_acceptance.py` so it accepts both legacy top-level vision fields and the new nested `analysis.recommended_prompt` response shape. A first 5-image local run had one 180s client timeout on the negative-externality image, then that same image passed on direct retry in 46.1s. A second continuous run with `--request-timeout 320` passed 5/5 through `http://127.0.0.1:8765/api/vision/analyze`; per-image latencies were about 59.6s, 50.9s, 40.8s, 50.3s, and 41.3s, with Chinese suggested prompts between 469 and 488 characters. The previously timed-out negative-externality case was then run through the full local chain: image understanding returned HTTP 200 in 46.2s, `/api/generate` returned HTTP 200 through `codex-cli` at 116.3s, local Manim rendered successfully by 142.6s, and the MP4 `media/videos/aegis-externality-generated/480p15/GeneratedScene.mp4` is 55.332678s. Extracted frames `/tmp/aegis-externality-render-frame-8s.png` and `/tmp/aegis-externality-render-frame-18s.png` show readable Chinese text and the correct MPC/MSC/MSB externality diagram. Current production exposure decision remains conservative: the local feature is viable, but the public image upload entry should stay gated until the same CLI route is installed and verified on `root@121.89.90.68`.

Follow-up on 2026-05-26 CST closed the main public-production architecture gap: Vercel/public gateway can now enable image understanding by setting `VISION_BACKEND_URL` and `VISION_BACKEND_API_KEY`, while the real image-reading CLI stays on the ECS host. Added `scripts/aegis_vision_server.py` as a host-level HTTP service for `/api/vision/analyze`, `scripts/install_aegis_vision_server.sh` as a systemd installer, remote backend proxy support in `core/vision_analysis.py`, and updated `.env.example`, `tasks/aliyun-swas-deploy-guide.md`, and `/Users/mahaoxuan/Desktop/ai组件工作流/服务器CLI视觉模型桥接组件.md`. Focused verification passed with `pytest -o addopts='' tests/test_aegis_ops_scripts.py tests/test_aegis_vision_analysis.py tests/test_kimi_vision_cli_bridge.py tests/test_probe_kimi_vision_cli.py tests/test_production_vision_economics_acceptance.py tests/test_aegis_web_ui.py -q` returning 29 passed, plus `git diff --check`. Remaining production gate is now explicit and user-actionable: run the server CLI probe from the active root SSH terminal, then install/start `aegis-vision.service` if the probe returns `ok: true`.

Added `scripts/aegis_vision_server_doctor.sh` as the user-facing ECS entrypoint. It checks the project checkout and test image, auto-selects `kimi`, `codex`, or `claude`, runs `scripts/probe_kimi_vision_cli.py`, refuses public exposure if the probe fails, and only installs `aegis-vision.service` after the report says `ok: true`. The deploy guide and the local AI workflow component now route the user to this one command first, with the manual probe kept as a fallback for debugging.

Added `scripts/package_aegis_vision_server_update.sh` to reduce the user intervention step from multiple path-sensitive `scp` commands to one local tarball upload. It packages `core/vision_analysis.py` plus the Vision Server, installer, doctor, CLI bridge, probe, fixture generator, image acceptance runner, and a default Chinese economics test image at `fixtures/vision-test.png` into `/tmp/aegis-vision-server-update.tgz`, then prints the exact upload and server extraction commands. The doctor now falls back to `fixtures/vision-test.png` when no explicit `IMAGE_PATH` is provided, so the user can validate server CLI image reading without preparing a separate screenshot first.

Extended the ECS doctor so a single successful run now produces stronger production evidence: after the single-image CLI probe passes, it installs `aegis-vision.service`, checks `http://127.0.0.1:5050/health`, reads the generated backend API key from `/opt/aegis/vision.env`, and runs `scripts/production_vision_economics_acceptance.py --skip-render` against the five bundled Chinese economics fixtures. The public image entry should only be enabled if both `Probe passed.` and the 5-image summary report all cases passing.

Added `scripts/push_aegis_vision_server_update.sh` to turn the current server update into one local command: package the pending Vision Server files, upload the archive through one SSH session to `root@121.89.90.68:/opt/aegis/`, extract it into `/opt/aegis/Aegis-Manim`, and run `scripts/aegis_vision_server_doctor.sh` remotely. The intended Agent Team rhythm is now explicit: call a team for broad research, independent provider/server review, or production acceptance design; reclaim to the lead agent for file edits, packaging, server commands, and user-intervention points; call again after the real server doctor output exists to split production env wiring, browser acceptance, and safety review; shut team work down once evidence is merged here.

Agent Team lifecycle for this feature is now treated as part of the development process, not optional commentary:

| Stage | Agent Team state | Owner | Evidence to continue |
|---|---|---|---|
| Product boundary and architecture | Call Agent Team for independent product, provider, server, and safety lanes | Lead agent coordinates | Specs and risks merged into `docs/specs/*`, this task log, and deploy docs |
| Local implementation | Reclaim to lead agent | Lead agent edits code and tests | Local tests, browser check, and `git diff --check` pass |
| Server handoff | Reclaim to lead agent | Lead agent produces package/push/check scripts; user only supplies password/login when required | `scripts/push_aegis_vision_server_update.sh` and `scripts/check_aegis_vision_server_update.sh` exist |
| Real ECS doctor output | Re-call Agent Team | Verification lanes split into server evidence, Vercel env wiring, public-browser acceptance, and safety/privacy review | `Probe passed.`, 5/5 vision-only JSONL, health output, and no secret leakage |
| Public-site full acceptance | Re-call or keep verifier lane active | Lead agent runs/integrates full acceptance evidence | `scripts/run_aegis_public_vision_acceptance.sh` produces 3-5 `status=done` videos |
| Production decision | Close Agent Team | Lead agent merges final evidence and makes `hidden` / `beta` / `public` decision | Decision and evidence are written here and in deploy docs; no open sidecar tasks remain |

Agent Team record template for each future team phase:

```text
Agent Team call reason:
Lanes and owner agents:
Expected evidence:
Lead-agent reclaim point:
Re-call trigger:
Close evidence:
Active workers/sidecars after close: none, or list merged report paths
```

Current sidecar state: verifier `019e63a2-ba38-7ae0-adad-882fe02c7187` completed with PASS and was closed after its gaps were folded into this task log and the deployment/component docs.

Current orchestration state on 2026-05-26 CST: Agent Team is intentionally closed/reclaimed while the lead agent owns the single-threaded integration work. Local evidence is now enough for this phase: the running local service at `http://127.0.0.1:8765` completed 5/5 Chinese economics vision-only checks against the real CLI bridge, and Playwright verified the browser upload flow plus “使用这个方向” confirmation writing a Chinese IS-LM prompt into the generation textarea. The next Agent Team call is blocked until ECS produces real server evidence from `scripts/push_aegis_vision_server_update.sh` / `scripts/check_aegis_vision_server_update.sh`.

Production exposure audit on 2026-05-26 CST: `https://manim.yishuziyu.cn/api/health` returned HTTP 200, and the production `/api/vision/analyze` route is now deployed. It intentionally returns HTTP 503 with `code=vision_feature_disabled`, which means the public route exists but the image feature gate is still closed until real ECS CLI evidence exists. `scripts/decide_aegis_vision_exposure.py --public-vision-url https://manim.yishuziyu.cn/api/vision/analyze` returns `exposure=hidden` with `publicRouteDeployed=true`, `probeOk=false`, `healthOk=false`, and `acceptanceTotal=0`. The verified exposure decision therefore remains `hidden`: noninteractive SSH to `root@121.89.90.68` still returns permission denied, so the lead agent cannot retrieve ECS doctor evidence without user login/password intervention. `scripts/decide_aegis_vision_exposure.py` now accepts `--public-vision-url` so future `hidden` / `beta` / `public` decisions include both server evidence and public-route deployment state.

Current Agent Team micro-call on 2026-05-26 CST: the lead agent called one read-only build-fixer sidecar (`019e63db-7c24-7ec1-ba4d-00e141817018`) only for the Vercel bundle-size failure after `/api/vision/analyze` was added to `vercel.json`. The lead agent kept ownership of edits and patched `.vercelignore`, `vercel.json`, and `tests/test_deploy_cloud_schema.py` locally. Root cause was the Vercel project being configured as `framework=python`, which made Vercel build the repository as a Python framework app and ignore the intended API-function bundle rules. The fix was to set `"framework": null`, use a short `api/*.py` function rule, keep `excludeFiles` under Vercel's 256-character limit, and push heavy local files into `.vercelignore`. Verification: `vercel build --prod --yes` passed with `.vercel/output` at 2.3M and the API function bundle at 872K; production deploy `dpl_EXAWyJYrzzwcBWa5PBQBtfaXygCA` was aliased to `https://manim.yishuziyu.cn`; `/api/health` returned HTTP 200; `/api/vision/analyze` returned expected `vision_feature_disabled` instead of 404. Reclaim point reached: the sidecar report has been folded into this log and the sidecar is closed. Re-call trigger remains unchanged: only real ECS doctor evidence should start the next multi-lane production review. Active workers/sidecars after close: none.

Fallback pivot on 2026-05-26 CST after the user called out the 6h42m stall: the lesson is now explicit. If one integration path is stuck for more than 30-60 minutes without new end-to-end evidence, the lead agent must stop looping and run a replacement-path search across official docs, community practice, and cheaper/open alternatives. In this turn, the user provided a Gemini API key. The key was used only as a process environment/inline probe and was not written to repo files. `models` probing succeeded, `gemini-2.0-flash-lite` image generation first returned HTTP 429, then `gemini-flash-lite-latest` successfully recognized the Chinese tax-wedge image. The code now supports `GEMINI_API_KEY` / `GEMINI_VISION_MODEL`, generic `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL`, and text-only `VISION_OCR_COMMAND` fallback. Local acceptance through `http://127.0.0.1:8765/api/vision/analyze` passed 3/3 Chinese economics images with Gemini `gemini-flash-lite-latest`: tax wedge 46.9s and 386 suggested-prompt chars, consumer choice 39.7s and 421 chars, monopoly 40.2s and 442 chars.

Production closure on 2026-05-26 CST: deployed `dpl_8mSWHnjd5U5p8qJxRZNBW3DaEpqZ` to `https://manim.yishuziyu.cn`. Production `/api/health` returned HTTP 200 with Kimi, DeepSeek, and MiniMax configured. A direct production probe confirmed the consumer-choice prompt now returns `stable-template-fallback` with `消费者选择与价格效应`, `替代效应`, `收入效应`, and `补偿预算线`, without waiting on external model generation. Full production image-to-video acceptance then passed 3/3 through `/api/vision/analyze` -> `/api/generate` -> `/api/render` -> status polling -> MP4 download -> frame extraction:

- Tax wedge: job `32a955d4-e6f8-4865-863b-5fc398de6d43`, duration 10.933s, 288202 bytes, 141476ms, frame `/tmp/aegis-vision-economics-acceptance/01-32a955d4-e6f8-4865-863b-5fc398de6d43.png`.
- Consumer choice: job `c53122b5-58fa-4532-b9e8-520a57c0c13b`, duration 7.733s, 221907 bytes, 99756ms, frame `/tmp/aegis-vision-economics-acceptance/02-c53122b5-58fa-4532-b9e8-520a57c0c13b.png`.
- Monopoly pricing: job `e2421d53-bfe5-4b95-aabc-29a8fe9ee97e`, duration 8.133s, 204506 bytes, 93024ms, frame `/tmp/aegis-vision-economics-acceptance/03-e2421d53-bfe5-4b95-aabc-29a8fe9ee97e.png`.

Frame inspection found all three outputs nonblank, Chinese-readable, and semantically aligned with the input topic. Earlier failures were diagnostic: monopoly prompts containing `无谓损失` were wrongly classified as tax-wedge fallback, and consumer-choice prompts could time out while waiting on external model generation. Both are now covered by deterministic Chinese economics fallback templates and tests. Exposure decision: `beta/whitelist` is acceptable for friends to try now; do not call it broad public-ready until the exposed Gemini key is rotated, one real browser upload test is performed on the production page, and at least one longer 5-case batch passes under the current quota/rate limits.

Production hotfix on 2026-05-26 CST after the user reported a browser-level `404: NOT_FOUND` at `https://manim.yishuziyu.cn/`: `/api/health` was still HTTP 200, so the domain and Vercel project were alive but the root route was not being rewritten to the Python function. Root cause was `vercel.json` only rewriting `/api/*` routes even though `api/index.py` already serves `GET /`. The fix added a root rewrite from `/` to `/api/index`, rotated the production `GEMINI_API_KEY`, and deployed `dpl_86VEUpATpnc3yR4fc93JkwxSeudH`, aliased to `https://manim.yishuziyu.cn`. Verification: `GET /` returned HTTP 200 with `Aegis Studio Web` HTML, `/api/health` returned HTTP 200, `/api/vision/analyze` returned HTTP 200 on the tax-wedge image and recognized `经济学教学图表（供需模型与税收效应）`, and a repo/component secret scan found no old or new Gemini key strings.

Next Agent Team call plan after ECS doctor evidence exists:

```text
Agent Team call reason: server-side vision CLI bridge produced real ECS evidence and needs production exposure review.
Lanes and owner agents: server evidence audit; Vercel env/proxy wiring; public browser 3-5 image acceptance; safety/privacy and secret-leak review.
Expected evidence: Probe passed; 5/5 vision-only JSONL; 127.0.0.1:5050 health; Vercel env names without secret values; public full-render JSONL with MP4 URLs when moving from beta to public.
Lead-agent reclaim point: all lanes submit evidence, then the lead agent updates docs and runs `scripts/decide_aegis_vision_exposure.py`.
Re-call trigger: any public acceptance failure, CORS/proxy failure, CLI timeout pattern, or privacy/retention concern.
Close evidence: exposure decision is written as hidden/beta/public with paths to the exact logs and no open sidecar tasks.
Active workers/sidecars after close: none.
```

# Production Chinese Economics Batch Acceptance and Render Watchdog

- [x] Add repeatable 3-5 question Chinese graduate-exam economics acceptance script.
- [x] Add render-backend health watchdog script with lock, cooldown, HTTP health check, and Docker restart.
- [x] Add systemd timer installer for the render watchdog.
- [x] Add regression tests proving scripts avoid API key leakage and remain shell/Python valid.
- [x] Reproduce the tax-wedge public trial timeout risk with a test-first default-provider rule.
- [x] Make default public trial tax-wedge prompts use the Chinese stable template before external model calls.
- [x] Deploy the gateway fix to production alias `https://manim.yishuziyu.cn`.
- [x] Run 3 consecutive live Chinese economics questions through public generate/render/status/download/frame checks.
- [x] Inspect representative frames for readable Chinese text and nonblank output.
- [ ] Install the watchdog on the ECS host once SSH credentials are available to Codex or the current root terminal.

## Review

On 2026-05-25 CST, deployed production gateway `dpl_AAqYABUz7bMi829JEph59hLbCe8q`, aliased to `https://manim.yishuziyu.cn`. The new rule keeps the existing two-part pricing fast path and adds a default-provider fast path for tax-wedge graduate-exam prompts, so high-risk Chinese economics topics do not wait on slow external model generation before falling back.

Live batch acceptance passed 3/3 against the production site. Q1 two-part pricing used `stable-template-fallback`, job `eb5ed101-20d5-4f45-bd9a-39a7abfe1285`, MP4 duration 4.4s. Q2 tax wedge used `stable-template-fallback`, job `4604d64b-b9e0-4809-8b75-52abe7de4ff5`, MP4 duration 10.933s; this fixed the previous 90s generation timeout. Q3 competitive market surplus used `server-managed-trial`, job `8ddb0318-c4ab-41cf-8e5e-5dd77d1b3089`, MP4 duration 28.867s. Frames were saved under `/tmp/aegis-econ-acceptance-20260525-rerun/` and showed readable Chinese labels without obvious garbling.

Verification passed with `python3 -m pytest -o addopts='' tests/test_aegis_ops_scripts.py tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_aegis_prompt_context.py -q` returning 60 passed, plus `python3 -m py_compile scripts/production_economics_acceptance.py`. Codex could not install the watchdog directly because noninteractive SSH to `root@121.89.90.68` returned permission denied; installation steps are documented in `tasks/aliyun-swas-deploy-guide.md`.

# Production Chinese Two-Part Pricing Acceptance

- [x] Deploy the Chinese-first economics generation rules to `https://manim.yishuziyu.cn`.
- [x] Add a fast stable Chinese template for two-part pricing prompts to avoid model timeout or topic drift.
- [x] Prevent two-part pricing prompts that mention deadweight loss from falling into the tax-wedge fallback.
- [x] Re-run focused public-trial, runtime compatibility, and prompt-context tests.
- [x] Run a live graduate-exam economics prompt through public `/api/generate`.
- [x] Run the generated Manim code through public `/api/render` and poll to `done`.
- [x] Download the returned MP4, inspect metadata, and extract a representative frame.
- [x] Fix visible label overlap in the two-part pricing fallback template and redeploy.

## Review

On 2026-05-25 CST, deployed the Chinese-first production rule set to `https://manim.yishuziyu.cn` through Vercel deployment `dpl_9DdsSKYS3o7DWZqHABU7yWXFyYDz`. The production `/api/health` endpoint returned HTTP 200 with `runtime=vercel-python-function`, and the public page returned HTML with `lang="zh-CN"`.

The live acceptance prompt was a harder Chinese economics graduate-exam style question about monopolistic two-part pricing, constant marginal cost, consumer surplus, fixed entry fee, efficient output, deadweight-loss elimination, and surplus redistribution. Public `/api/generate` returned HTTP 200 with `model=stable-template-fallback`, `endpoint=server-managed-fallback`, 4 `self.play(...)` calls, Chinese visible text, no tax-wedge fallback, and the warning `已识别为考研经济学二部定价题，优先使用中文稳定模板，避免模型长时间生成或跑题。` Public `/api/render` accepted the code and job `2ccbb042-bd8f-4561-854c-3de79634dca0` reached `done`.

Final MP4: `https://lnbalcskhcnkrtlqpgku.supabase.co/storage/v1/object/public/manim-videos/2ccbb042-bd8f-4561-854c-3de79634dca0/GeneratedScene.mp4`, H.264 854x480, duration 4.399678s, 66 frames, size 106497 bytes. Representative frame: `/tmp/aegis-latest-two-part-pricing-frame-v2.png`. The frame shows Chinese title, subtitle, demand curve, marginal cost, monopoly point, consumer surplus, and efficient output labels without garbled text or severe overlap. Codex in-app browser automation was attempted but the browser runtime transport was unavailable, so this pass used HTTP/API/video/frame verification instead of an in-app browser screenshot.

Focused verification passed with `python3 -m pytest -o addopts='' tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_aegis_prompt_context.py -q` returning 56 passed. `git diff --check` also passed.

# Public Chinese Economics Acceptance Follow-up

- [x] Add a Chinese-first visible text contract to public trial generation prompts.
- [x] Avoid Chinese sentence-to-sentence transform animations that can show mixed glyphs.
- [x] Add a runtime compatibility fix for generated `Arrow(max_tip_length=...)`.
- [x] Verify focused prompt, public trial, and runtime compatibility tests.
- [x] Run a live public economics graduate-exam style tax-wedge render.
- [x] Inspect MP4 metadata and representative frames for readable Chinese labels.

## Review

On 2026-05-25 CST, strengthened the public Manim generation contract for Chinese economics teaching scenes: all visible titles, labels, captions, axis explanations, step labels, and conclusions default to Chinese; English draft prose must be translated before entering `Text(...)`; compact symbols such as `价格 P`, `数量 Q`, `需求 D`, `供给 S`, `边际成本 MC`, and `边际收益 MR` remain allowed when paired with Chinese context; and Chinese captions now fade out/in rather than transform sentence-to-sentence. The runtime compatibility layer also removes unsupported generated `Arrow(max_tip_length=...)`.

Focused verification passed with `python3 -m pytest -o addopts='' tests/test_aegis_public_trial.py tests/test_aegis_runtime_compatibility.py tests/test_aegis_prompt_context.py -q` returning 54 passed. A live public test on `https://manim.yishuziyu.cn` used a harder tax-wedge prompt about from-unit tax, `Pb`, `Ps`, `Q0`, `Q1`, tax revenue, deadweight loss, and efficiency loss. Public generation returned HTTP 200, fell back from Kimi access to DeepSeek, produced Chinese Manim code with no `LaggedStart`, `BraceLabel`, or `max_tip_length`, then public render job `e18ae1c7-f5db-4336-9289-1606220e3c11` completed 4/4 segmented renders. Final MP4: `https://lnbalcskhcnkrtlqpgku.supabase.co/storage/v1/object/public/manim-videos/e18ae1c7-f5db-4336-9289-1606220e3c11/GeneratedScene_segmented.mp4`, H.264 854x480, duration 23.999356s, size 379855 bytes. Representative frames showed Chinese title, price/quantity axes, demand/supply/taxed supply curves, tax revenue rectangle, deadweight-loss triangle, and Chinese conclusion text. Remaining UX issue: direct video URL navigation in the Codex in-app browser was blocked by the browser client, but the MP4 was reachable via `curl` and verified locally.

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

# Image Understanding CLI Bridge

- [x] Validate that direct `KIMI_CODE_API_KEY` HTTP calls return Kimi access gating instead of usable product API access.
- [x] Add `/api/vision/analyze` as a formal image-understanding endpoint.
- [x] Add a server-side CLI bridge via `KIMI_VISION_CLI_COMMAND` so a real logged-in terminal tool can read uploaded images.
- [x] Add upload, paste, drag/drop, mobile file-input, and Chinese confirmation-card UI.
- [x] Keep confirmed image understanding as a Chinese prompt into the existing generate/render chain.
- [x] Verify the CLI image route with a real terminal tool on this workstation.
- [x] Run 5 local Chinese economics postgraduate-question image tests through `/api/vision/analyze`.
- [ ] Install and verify the same Kimi/Codex/Claude CLI route on the cloud server with image input.
- [ ] Run 3-5 Chinese economics postgraduate-question image tests through the production site.

## Review

The implementation route has changed from raw Kimi Code HTTP vision to a real terminal-backed bridge. Direct HTTP probes to `https://api.kimi.com/coding/v1/chat/completions` returned Kimi access gating even for text, so the durable route is to configure a real server CLI command template through `KIMI_VISION_CLI_COMMAND`. The backend writes the uploaded image and prompt into temporary files, calls the configured CLI, parses structured JSON or raw Chinese text, and returns a confirmation card payload. Production exposure still depends on installing the CLI on the server and passing the Chinese economics image acceptance run.

Local end-to-end test passed on 2026-05-26 CST with a generated Chinese economics image about “税收楔子与无谓损失”. The real `codex exec --image` route correctly recognized the title, full Chinese question, demand/supply curves, `S+t`, `Pb/Ps/P0`, `Q1/Q0`, tax revenue rectangle, and DWL triangle, then returned a Chinese `recommended_prompt`. The local `/api/vision/analyze` endpoint also passed after adding `--skip-git-repo-check` to the Codex CLI args. The returned `suggestedPrompt` was fed into `/api/generate` with `noRender=true`, which produced `generated/scene_20260526_144914_33fb2aa9.py`; local Manim then rendered `media/videos/scene_20260526_144914_33fb2aa9/480p15/GeneratedScene.mp4` successfully. Extracted frames `/tmp/aegis-econ-render-frame.png` and `/tmp/aegis-econ-render-frame-late.png` show readable Chinese labels and a correct supply-demand tax-wedge diagram, though some mid-scene labels around tax revenue and DWL are crowded and should be tightened in the next layout-quality pass.

The 5-image local economics vision batch also passed on 2026-05-26 CST after increasing client timeout to 320s. Evidence is saved at `/tmp/aegis-vision-economics-acceptance/vision-only-320s.jsonl`. The negative-externality sample additionally passed full generation and local rendering into `media/videos/aegis-externality-generated/480p15/GeneratedScene.mp4`, with representative frames saved under `/tmp/aegis-externality-render-frame-8s.png` and `/tmp/aegis-externality-render-frame-18s.png`. The main operational gap is no longer local viability; it is installing and validating the same logged-in CLI image route on the ECS production host before public exposure.

# Kimi Code Access Retry

- [x] Research the current Kimi Code 403/access failure against official docs and developer issues.
- [x] Move hosted `kimi-code` calls from the OpenAI-compatible `/coding/v1` path to the official Anthropic-compatible `/coding/` path.
- [x] Change public trial fallback order from `Kimi -> DeepSeek -> MiniMax` to `Kimi -> MiniMax -> DeepSeek`.
- [x] Replace raw `access` warning text with a clearer Chinese diagnosis.
- [x] Add focused regression coverage for the new Kimi protocol and fallback order.
- [ ] Deploy the retry to production and run one Chinese economics postgraduate prompt through the production site.

## Review

Official Kimi Code documentation says Kimi Code and Kimi Open Platform keys/base URLs are not interchangeable, and that OpenAI-compatible requests can hit a client whitelist style 403. Their recommended third-party coding-agent path for Claude Code is the Anthropic-compatible base URL `https://api.kimi.com/coding/`. GitHub issue search shows the same “Kimi For Coding is currently only available for Coding Agents” 403 appearing in Cline/Roo/Kimi CLI integration discussions. The production warning therefore most likely came from using the OpenAI-compatible Kimi Code path from a non-whitelisted hosted client, not from missing Vercel env configuration.

The retry changes `kimi-code` to the Anthropic-compatible `/coding/messages` route and makes MiniMax the immediate backup before DeepSeek. Focused local verification passed with `68 passed` across provider, public trial, web UI, and vision tests. The full upstream Manim suite is still not a useful release gate in this workstation because it fails on missing local TeX packages such as `dvisvgm` / `standalone.cls` and unrelated graphical baseline tests.
