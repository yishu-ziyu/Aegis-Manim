# Aegis-Manim 阿里云轻量服务器部署手册

目标：把 `render_backend` 跑成 Docker 服务，先用 `http://YOUR_HOST:5000/health` 验证，稳定后再接域名和 HTTPS。

## 服务器信息

- 实例：Docker-iirl
- 地域：华北6（乌兰察布）
- 公网 IP：YOUR_HOST
- 镜像：Docker 26.1.3
- 规格：2 vCPU / 4 GiB / 50 GiB ESSD

## 1. 先解决登录

如果本地执行下面命令返回 `Permission denied (publickey...)`，说明服务器还没有绑定可用 SSH 凭据：

```bash
ssh root@YOUR_HOST
```

处理方式二选一：

1. 在阿里云控制台点击实例卡片里的“设置密码”，设置 root 登录密码，按提示重启后再试 SSH。
2. 更推荐：在阿里云控制台绑定 SSH 密钥对，然后用本机私钥登录。

## 2. 登录后基础检查

```bash
docker --version
docker compose version || true
uname -a
df -h
free -h
```

如果 4 GiB 内存构建 Docker 镜像时失败，先加 4 GiB swap：

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 3. 拉代码并构建镜像

```bash
dnf install -y git curl openssl || yum install -y git curl openssl

mkdir -p /opt/aegis
cd /opt/aegis
git clone https://github.com/yishu-ziyu/Aegis-Manim.git
cd Aegis-Manim

docker build -t aegis-manim-render -f render_backend/Dockerfile render_backend
```

如果仓库是私有的，不要把 GitHub token 发到聊天里；改用 GitHub SSH deploy key 或在服务器上手动完成认证。

## 4. 生成并保存后端 API Key

```bash
openssl rand -hex 32
```

把输出值只保存在服务器和 Vercel 环境变量里，不要提交到 Git，不要发到聊天里。

## 5. 启动渲染服务

```bash
export MANIM_API_KEY='填刚才生成的随机值'

mkdir -p /opt/aegis/outputs

docker rm -f aegis-manim-render 2>/dev/null || true

docker run -d \
  --name aegis-manim-render \
  --restart unless-stopped \
  -p 5000:5000 \
  -e MANIM_API_KEY="$MANIM_API_KEY" \
  -e MANIM_CJK_FONT="Noto Sans CJK SC" \
  -e MANIM_RENDER_QUALITY="-ql" \
  -e MANIM_RENDER_TIMEOUT_SECONDS="300" \
  -v /opt/aegis/outputs:/app/outputs \
  aegis-manim-render
```

## 6. 验证

服务器内验证：

```bash
docker ps
docker logs --tail=80 aegis-manim-render
curl http://127.0.0.1:5000/health
```

本机验证：

```bash
curl http://YOUR_HOST:5000/health
```

看到 JSON 健康检查结果以后，才进入域名和 HTTPS。

## 7. 安装健康守护和自动恢复

渲染容器已经使用 `--restart unless-stopped`，但这只能覆盖进程退出，不能覆盖“容器还活着但 HTTP 健康检查失败”的情况。部署后建议安装 systemd timer，每分钟检查一次 `/health`，失败时自动重启容器。

在服务器上执行：

```bash
cd /opt/aegis/Aegis-Manim
chmod +x scripts/aegis_render_watchdog.sh scripts/install_aegis_render_watchdog.sh
scripts/install_aegis_render_watchdog.sh
```

安装后验证：

```bash
systemctl status aegis-render-watchdog.timer --no-pager
systemctl start aegis-render-watchdog.service
tail -n 30 /var/log/aegis-render-watchdog.log
```

守护脚本默认值：

- 容器名：`aegis-manim-render`
- 健康检查：`http://127.0.0.1:5000/health`
- 检查频率：每 60 秒
- 重启冷却：180 秒，避免连续重启
- 日志：`/var/log/aegis-render-watchdog.log`

脚本不会读取或打印 `MANIM_API_KEY`，健康检查也不需要 API Key。

## 8. 安装图片理解 Vision Server

图片上传理解不能直接放在 Vercel 里调用本机 CLI。生产链路采用：

```text
用户网页 -> Vercel /api/vision/analyze -> ECS Vision Server -> 服务器已登录 CLI -> 返回中文理解和可视化方向
```

如果本地改动还没推到 GitHub，优先用本机一键推送脚本。它会打包、通过一个 SSH 会话上传、远程解包并运行 doctor；密码登录时通常只需要输入一次密码：

```bash
cd /Users/mahaoxuan/Desktop/AI产品经理/实验探索/vibe/manim-main
scripts/push_aegis_vision_server_update.sh
```

这个脚本会在服务器上用 `nohup` 后台运行 doctor，并把证据写到 `/opt/aegis/vision-doctor.log`。如果 SSH 中途断开，测试仍会继续；重新连接后查看：

```bash
scripts/check_aegis_vision_server_update.sh
```

检查脚本末尾会运行 `scripts/decide_aegis_vision_exposure.py --public-vision-url https://manim.yishuziyu.cn/api/vision/analyze`，同时检查 ECS 证据和公网路由状态，给出机器可读的曝光建议：

- `hidden`：probe、服务健康或 3-5 图验收缺证据/失败，继续隐藏入口。
- `beta`：服务器读图和 5 图 vision-only 验收通过，可以进入小范围白名单，但还不能公开。
- `public`：完整 image -> generate -> render -> video 验收通过，才进入公开入口配置。

如果需要手动拆开执行，再使用：

```bash
cd /Users/mahaoxuan/Desktop/AI产品经理/实验探索/vibe/manim-main
scripts/package_aegis_vision_server_update.sh
scp /tmp/aegis-vision-server-update.tgz root@YOUR_HOST:/opt/aegis/aegis-vision-server-update.tgz

cd /opt/aegis/Aegis-Manim
tar -xzf /opt/aegis/aegis-vision-server-update.tgz -C /opt/aegis/Aegis-Manim
chmod +x scripts/aegis_vision_server.py scripts/install_aegis_vision_server.sh scripts/aegis_vision_server_doctor.sh
scripts/aegis_vision_server_doctor.sh
```

先确认服务器上有可用 CLI：

```bash
command -v kimi || true
command -v codex || true
command -v claude || true
```

更新包内置了一张中文经济学测试图 `fixtures/vision-test.png`，优先直接跑一键 doctor：

```bash
cd /opt/aegis/Aegis-Manim
scripts/aegis_vision_server_doctor.sh
```

doctor 会自动选择服务器上已安装的 `kimi`、`codex` 或 `claude`，先验证 CLI 能读图并生成中文可视化方向；通过后再安装并启动 `aegis-vision.service`，然后对包内 5 张中文经济学图跑 vision-only 批量验收。输出里应该同时看到：

- `Probe passed.`
- `summary` 里的 `passed` 等于 `total`，通常是 `5/5`

如果你要用自己的真实截图覆盖内置测试图，先上传后显式指定 `IMAGE_PATH`：

```bash
scp ./你的中文经济学题截图.png root@YOUR_HOST:/opt/aegis/vision-test.png
IMAGE_PATH=/opt/aegis/vision-test.png scripts/aegis_vision_server_doctor.sh
```

排查时可以跳过 5 图批量验收：

```bash
RUN_BATCH_ACCEPTANCE=0 scripts/aegis_vision_server_doctor.sh
```

如果需要手动排查，再单独跑探针：

```bash
cd /opt/aegis/Aegis-Manim

python3 scripts/probe_kimi_vision_cli.py \
  --image /opt/aegis/vision-test.png \
  --binary kimi \
  --timeout 320 \
  --report /opt/aegis/vision-probe-report.json
```

如果实际可读图的是 `codex` 或 `claude`，把 `--binary kimi` 改成对应命令；必要时加 `--args-json` 适配该 CLI 的参数格式。探针返回 `ok: true` 后再安装服务：

```bash
cd /opt/aegis/Aegis-Manim
BINARY=codex \
ARGS_JSON='["exec","--skip-git-repo-check","{prompt}","--image","{image_path}"]' \
scripts/aegis_vision_server_doctor.sh
```

不要在自定义 `--args-json` 调试通过后直接运行 `scripts/install_aegis_vision_server.sh`。真正安装必须回到 doctor，因为 doctor 会把刚验证通过的 `BINARY` 和 `ARGS_JSON` 写入 `/opt/aegis/vision.env`，避免 systemd 服务启动后又退回默认 `kimi` 参数。

服务器内验证：

```bash
systemctl status aegis-vision.service --no-pager
curl -sS http://127.0.0.1:5050/health
```

对外接入有两种方式：

1. 临时公测：阿里云安全组开放 `5050`，Vercel 配置 `VISION_BACKEND_URL=http://YOUR_HOST:5050`。
2. 正式发布：用 Caddy 或 Nginx 给 `vision.yishuziyu.cn` 配 HTTPS，再设置 `VISION_BACKEND_URL=https://vision.yishuziyu.cn`。

正式发布的 Caddy 反代可以和渲染后端并列配置：

```caddy
render.yishuziyu.cn {
  encode zstd gzip
  reverse_proxy 127.0.0.1:5000
}

vision.yishuziyu.cn {
  encode zstd gzip
  reverse_proxy 127.0.0.1:5050
}
```

只有在 doctor 输出 `Probe passed.` 且 5 图验收全通过后，才把公网变量切到 `https://vision.yishuziyu.cn`。

同时在 Vercel 设置：

```text
AEGIS_VISION_PUBLIC_ENABLED=1
VISION_BACKEND_URL=http://YOUR_HOST:5050
VISION_BACKEND_API_KEY=读取 /opt/aegis/vision.env 里的 AEGIS_VISION_BACKEND_API_KEY
VISION_BACKEND_TIMEOUT_SECONDS=360
```

注意：`VISION_BACKEND_API_KEY` 不要发到聊天里，也不要提交到 Git。

## 9. 下一阶段

1. DNS 增加 A 记录：`render.yishuziyu.cn -> YOUR_HOST`
2. 用 Caddy 或 Nginx 做 HTTPS 反向代理到 `127.0.0.1:5000`
3. Vercel 设置：
   - `RENDER_BACKEND_URL=https://render.yishuziyu.cn`
   - `RENDER_BACKEND_API_KEY=同一个 MANIM_API_KEY`
   - `AEGIS_VISION_PUBLIC_ENABLED=1`
   - `VISION_BACKEND_URL=https://vision.yishuziyu.cn`
   - `VISION_BACKEND_API_KEY=Vision Server 的 API Key`
4. 重新部署 Vercel 后做一次真实生成和视频下载测试。

公开入口的最终验收不要复用服务器 doctor 的 `--skip-render` 结果。公网配置完成后，在本机仓库运行：

```bash
cd /Users/mahaoxuan/Desktop/AI产品经理/实验探索/vibe/manim-main
scripts/run_aegis_public_vision_acceptance.sh
```

这个脚本固定走 `https://manim.yishuziyu.cn`，自动生成 5 张中文经济学考研图，并跑完整链路：图片理解、生成、渲染、下载 MP4、探测时长、抽取代表帧。只有 JSONL 中所有记录都满足 `ok=true`、`status=done`、有 `videoUrl` 和 `videoBytes`，才把图片上传入口从小范围测试扩大到公开。

## 10. Agent Team 调度边界

这条部署线采用“主 agent 集成、Agent Team 分段介入”的节奏：

| 阶段 | 是否调用 Agent Team | 主 agent 什么时候收回 | 进入下一步的证据 |
|---|---|---|---|
| 需求和方案边界 | 调用：拆产品、provider、服务器、验收、安全并行线 | 并行结论合并成一个最小方案后收回 | 规格、风险和验收门槛写入 `tasks/todo.md` 与本手册 |
| 本地代码和脚本 | 不调用或只保留短验证线 | 代码落地、打包、密钥边界和用户操作说明由主 agent 集成 | 本地测试、脚本语法检查、打包清单、`git diff --check` |
| ECS doctor 执行 | 主 agent 收回 | 需要用户输入 SSH 密码或 CLI 登录时，主 agent 明确给单条命令；不让团队分散操作服务器 | `/opt/aegis/vision-doctor.log`、pid、health、5 图 vision-only JSONL |
| doctor 出真实结果后 | 再调用：拆 Vercel 环境变量、浏览器端 3-5 题验收、安全/隐私复核 | 每条验证线给出证据后收回，由主 agent 改文档和决定曝光级别 | `hidden` / `beta` / `public` 决策 JSON |
| 公网完整验收 | 调用 verifier 或测试线；主 agent 运行/整合 `scripts/run_aegis_public_vision_acceptance.sh` | 全部公开视频记录闭环后收回 | 3-5 条 `status=done`、MP4 可下载、代表帧可读 |
| 结束阶段 | 关闭 Agent Team | 证据落到 `tasks/todo.md`、本手册和组件文档后关闭 | 没有悬空 worker、没有未合并报告、没有未说明风险 |

原则：Agent Team 只处理可并行、可验证的分支；密钥、生产命令、最终曝光决策由主 agent 收回统一处理。

关闭前必须写明 active worker/sidecar 状态：如果没有未完成团队线程，记录 `none`；如果有报告被合并，列出对应报告路径或 agent id，并说明主 agent 已收回哪些后续动作。

当前阶段记录：本地代码、脚本、浏览器上传确认、5 图 vision-only 验收已经由主 agent 收回并完成；不要在没有 ECS doctor 真实输出前继续开团队分支。下一次调用 Agent Team 的触发条件是服务器日志里出现 `Probe passed.`、5 图 JSONL 和 `127.0.0.1:5050/health` 结果。调用后只拆四条线：服务器证据复核、Vercel 环境变量和反代接入、公网 3-5 图完整渲染验收、安全/隐私复核。四条线都给出证据后，主 agent 立即收回，运行 `scripts/decide_aegis_vision_exposure.py`，并把 hidden/beta/public 决策写回本手册和 `tasks/todo.md`。

当前公网事实：`https://manim.yishuziyu.cn/api/vision/analyze` 仍返回 404，说明图片理解路由尚未部署到生产站；在 ECS doctor 和 Vercel route/env 都通过前，生产曝光保持 `hidden`。
