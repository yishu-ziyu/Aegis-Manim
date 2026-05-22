# 渲染任务持久化技术文档

> **目标读者**：Codex（代码实现）+ Claude（验收）
> **版本**：v1.0
> **日期**：2026-05-22

---

## 1. 问题定义（我们要解决什么）

### 1.1 现状

当前架构三层：

```
用户浏览器 → Vercel Gateway (api/index.py) → Render Backend (render_backend/app.py)
```

Render Backend 使用**双层存储**：
- **主存储**：内存字典 `_jobs: dict[str, RenderJob]` —— 读写快，但实例重启即丢失
- **辅存储**：Supabase PostgreSQL —— 已配置，但当前代码逻辑中只是"可选备份"

### 1.2 故障场景

Render free tier 有两个致命限制：
- **15分钟无活动休眠**：HTTP 层无法响应，需冷启动唤醒（已部分解决）
- **512MB 内存上限**：Manim 渲染复杂场景时易 OOM，实例直接崩溃重启

当实例崩溃或休眠后重启：
1. 内存 `_jobs` 全部清空 → 用户轮询返回 `"Job not found"`
2. 本地 `OUTPUT_DIR` 中的视频文件丢失 → 即使任务标记为 done 也下载不了
3. Supabase 中的状态可能是过时的（如 `running`，实际上进程已死）

### 1.3 目标

**把 Supabase 提升为唯一可信状态源，内存仅作性能缓存**。确保：
- 实例重启后，用户通过 `job_id` 仍能查询任务状态
- 渲染成功的视频通过 Supabase Storage URL 访问，不依赖本地文件
- 孤儿任务（实例崩溃后遗留的 running 任务）被自动清理

---

## 2. 技术方案（我们要怎么做）

### 2.1 核心原则

```
写操作：Supabase 先成功，内存后更新（保证持久层优先）
读操作：Supabase 优先，内存兜底（保证看到最新状态）
启动时：从 Supabase 恢复未完成任务到内存缓存
运行时：后台线程定期清理孤儿任务
```

### 2.2 改动范围

#### 文件 1：`render_backend/supabase_client.py`（新增/增强）

新增以下函数：

```python
def list_jobs_by_status(statuses: list[str]) -> list[dict[str, Any]]:
    """查询指定状态的所有任务。用于启动恢复和孤儿清理。"""

def job_exists(job_id: str) -> bool:
    """轻量级存在性检查，避免完整反序列化。"""

def update_job_heartbeat(job_id: str) -> bool:
    """更新任务的 updated_at 时间戳，用于孤儿检测。"""
```

增强现有函数：
- `insert_job`：增加重试机制（网络抖动时最多重试 2 次）
- `update_job`：增加重试机制，返回更新后的完整记录
- `get_job`：增加重试机制

#### 文件 2：`render_backend/app.py`（核心改动）

**A. 启动恢复机制**

在 Flask app 启动时（`app.run` 之前，或用一个 `before_first_request` 钩子），添加：

```python
def _recover_jobs_from_supabase() -> None:
    """
    启动时从 Supabase 恢复所有 pending/running 的任务到内存缓存。
    这些任务可能是上次实例崩溃时遗留的。
    """
    if not _use_supabase():
        return
    jobs = supabase_client.list_jobs_by_status(["pending", "running"])
    with _jobs_lock:
        for row in jobs:
            job = RenderJob(
                job_id=row["job_id"],
                status=JobStatus(row["status"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                code=row["code"],
                scene_name=row["scene_name"],
                video_path=row.get("video_path"),
                error_message=row.get("error_message"),
                stderr=row.get("stderr"),
            )
            _jobs[row["job_id"]] = job
    print(f"[recovery] Restored {len(jobs)} jobs from Supabase", file=sys.stderr)
```

**B. 孤儿任务清理线程**

添加一个后台守护线程，每 30 秒执行一次：

```python
ORPHAN_JOB_THRESHOLD_SECONDS = 600  # 10 分钟无更新视为孤儿

def _reap_orphan_jobs() -> None:
    """
    将长时间处于 running 状态且未更新的任务标记为 failed。
    这通常意味着实例崩溃时该任务正在运行。
    """
    if not _use_supabase():
        return
    now = datetime.now(timezone.utc)
    jobs = supabase_client.list_jobs_by_status(["running"])
    for row in jobs:
        updated_at = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
        if (now - updated_at).total_seconds() > ORPHAN_JOB_THRESHOLD_SECONDS:
            supabase_client.update_job(
                job_id=row["job_id"],
                status="failed",
                error_message="Render instance restarted unexpectedly. Please resubmit.",
            )
            with _jobs_lock:
                if row["job_id"] in _jobs:
                    _jobs[row["job_id"]].status = JobStatus.FAILED
                    _jobs[row["job_id"]].error_message = "Render instance restarted unexpectedly."
            print(f"[reaper] Orphan job {row['job_id'][:8]} marked as failed", file=sys.stderr)

def _start_orphan_reaper() -> None:
    def loop():
        while True:
            time.sleep(30)
            try:
                _reap_orphan_jobs()
            except Exception as exc:
                print(f"[reaper] Error: {exc}", file=sys.stderr)
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
```

**C. 修改 `_register_job`**

```python
def _register_job(code: str, scene_name: str, client_ip: str | None = None) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # 1. 先写入 Supabase（持久层优先）
    if _use_supabase():
        row = supa_insert_job(job_id=job_id, code=code, scene_name=scene_name, client_ip=client_ip)
        if row is None:
            # Supabase 写入失败，不要创建内存任务，直接抛异常让上层返回 500
            raise RuntimeError("Failed to persist job to Supabase")

    # 2. Supabase 成功后再写入内存缓存
    job = RenderJob(
        job_id=job_id,
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
        code=code,
        scene_name=scene_name,
    )
    with _jobs_lock:
        _jobs[job_id] = job
    return job_id
```

**D. 修改 `_update_job`**

```python
def _update_job(
    job_id: str,
    status: JobStatus | None = None,
    video_path: str | None = None,
    error_message: str | None = None,
    stderr: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()

    # 1. 先更新 Supabase
    if _use_supabase():
        result = supa_update_job(
            job_id=job_id,
            status=status.value if status else None,
            video_path=video_path,
            error_message=error_message,
            stderr=stderr,
        )
        if result is None:
            print(f"[update_job] Supabase update failed for {job_id[:8]}", file=sys.stderr)
            # 关键：Supabase 更新失败时，不同步内存，保证一致性
            return

    # 2. Supabase 成功后再更新内存
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            # 内存中没有但 Supabase 有（比如恢复后的任务正在被更新）
            # 从 Supabase 重新加载
            if _use_supabase():
                row = supa_get_job(job_id)
                if row:
                    job = RenderJob(
                        job_id=row["job_id"],
                        status=JobStatus(row["status"]),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        code=row["code"],
                        scene_name=row["scene_name"],
                        video_path=row.get("video_path"),
                        error_message=row.get("error_message"),
                        stderr=row.get("stderr"),
                    )
                    _jobs[job_id] = job
            if job is None:
                return
        if status is not None:
            job.status = status
        if video_path is not None:
            job.video_path = video_path
        if error_message is not None:
            job.error_message = error_message
        if stderr is not None:
            job.stderr = stderr
        job.updated_at = now
```

**E. 修改 `_get_job`**

```python
def _get_job(job_id: str) -> RenderJob | None:
    # 始终优先从 Supabase 读取最新状态
    if _use_supabase():
        row = supa_get_job(job_id)
        if row:
            job = RenderJob(
                job_id=row["job_id"],
                status=JobStatus(row["status"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                code=row["code"],
                scene_name=row["scene_name"],
                video_path=row.get("video_path"),
                error_message=row.get("error_message"),
                stderr=row.get("stderr"),
            )
            # 同步到内存缓存
            with _jobs_lock:
                _jobs[job_id] = job
            return job

    # Supabase 未配置或未查到，回退内存
    with _jobs_lock:
        return _jobs.get(job_id)
```

**F. 修改渲染流程 `_run_manim_render`**

当前逻辑：渲染成功后先 `shutil.move` 到本地 `OUTPUT_DIR`，然后如果 Supabase 配置了再上传。

**改为**：上传 Supabase Storage 是**强制步骤**，上传成功后 `video_path` 必须是 Supabase URL。

```python
def _run_manim_render(
    code: str,
    scene_name: str,
    job_id: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    # ... 创建 workspace，运行 manim ...

    # 渲染成功，找到视频文件
    video_path = _find_rendered_video(workspace, scene_name)
    if video_path is None:
        _cleanup_workspace(workspace)
        return {"success": False, "error": "Video file not found", ...}

    # 强制上传到 Supabase Storage（如果配置了）
    supa_video_url: str | None = None
    if _use_supabase() and job_id:
        supa_video_url = supa_upload_video(job_id, video_path)
        if supa_video_url:
            supa_insert_log(job_id=job_id, level="info", stage="upload",
                           message="Video uploaded to Supabase Storage",
                           detail=f"url={supa_video_url}")
        else:
            # 上传失败，标记任务失败（避免用户得到一个本地路径但实例重启后文件丢失）
            _cleanup_workspace(workspace)
            return {
                "success": False,
                "error": "Video rendered but failed to upload to persistent storage",
                "stderr": result.stderr,
            }

    # 本地保留一份作为备份
    output_filename = f"{job_id or uuid.uuid4().hex}_{scene_name}.mp4"
    local_output_path = OUTPUT_DIR / output_filename
    shutil.copy(str(video_path), str(local_output_path))
    _cleanup_workspace(workspace)

    return {
        "success": True,
        "video_path": supa_video_url or str(local_output_path),  # 优先返回 URL
        "video_url": supa_video_url,
        "error": None,
        "stderr": result.stderr,
    }
```

**G. 修改 `download_video` 端点**

```python
@app.route("/download/<job_id>", methods=["GET"])
@require_api_key
def download_video(job_id: str) -> tuple:
    job = _get_job(job_id)  # 这会从 Supabase 读取最新状态
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job.status != JobStatus.DONE:
        return jsonify({"error": "Video not ready", "status": job.status.value}), 409

    # 优先返回 Supabase Storage URL
    if job.video_path and job.video_path.startswith("http"):
        return jsonify({
            "ok": True,
            "video_url": job.video_path,
            "scene_name": job.scene_name,
        }), 200

    # 兜底：本地文件（仅在 Supabase 未配置时走到这里）
    if not job.video_path or not Path(job.video_path).exists():
        return jsonify({"error": "Video file missing"}), 500

    return send_file(...)
```

**H. 启动时调用恢复和清理**

在 `if __name__ == "__main__":` 之前添加：

```python
def initialize_app() -> None:
    """应用初始化：从 Supabase 恢复任务，启动孤儿清理线程。"""
    if _use_supabase():
        _recover_jobs_from_supabase()
        _start_orphan_reaper()
    else:
        print("[init] Supabase not configured, running in memory-only mode", file=sys.stderr)

# 在 __main__ 中调用
if __name__ == "__main__":
    initialize_app()
    port = int(os.environ.get("PORT", "5000"))
    # ...
```

**对于 Gunicorn 部署**（Render 实际使用 gunicorn）：

Gunicorn 多 worker 模式下，`initialize_app()` 会在每个 worker 启动时执行。需要确保：
- `_recover_jobs_from_supabase()` 是幂等的（多次执行不会重复添加同一 job_id）
- 孤儿清理线程每个 worker 各有一个，这是可以接受的（多个 worker 同时尝试更新同一孤儿任务，由于状态变更幂等，不会出错）

更稳妥的方式是使用 Gunicorn 的 `post_worker_init` hook：

```python
# 在 app.py 末尾添加
def post_worker_init(worker):
    initialize_app()
```

然后在启动命令中使用：

```bash
gunicorn --config gunicorn.conf.py app:app
```

但由于 Render 可能直接使用 `gunicorn app:app`，我们需要一个更简单的方案：

```python
# 使用 Flask 的 before_first_request（每个 worker 第一次请求时触发）
@app.before_request
def _init_once():
    if not getattr(app, "_initialized", False):
        initialize_app()
        app._initialized = True
```

**推荐**：使用 `before_request` 单例模式，兼容直接 `gunicorn app:app` 启动。

#### 文件 3：`render_backend/requirements.txt`（无变更）

当前 `requests>=2.31.0` 已满足 Supabase REST API 调用需求，不需要新增依赖。

#### 文件 4：`api/index.py`（Vercel Gateway，无变更）

Gateway 层只是透传请求，不需要改动。已有的冷启动保护（预热+重试）继续生效。

---

## 3. 时序图

### 3.1 正常渲染流程

```
用户          Vercel Gateway          Render Backend          Supabase
 |                  |                         |                   |
 |---提交代码------>|                         |                   |
 |                  |------POST /render-async->|                   |
 |                  |                         |--insert_job()---->|
 |                  |                         |<--job record------|
 |                  |                         |--_jobs[job_id]=job|
 |                  |<----{job_id, status_url}-|                   |
 |<----job_id------|                         |                   |
 |                  |                         |                   |
 |---轮询 status--->|                         |                   |
 |                  |------GET /status/{id}--->|                   |
 |                  |                         |--get_job()------->|
 |                  |                         |<--latest state----|
 |                  |<----{status: running}---|                   |
 |<----running-----|                         |                   |
 |                  |                         |                   |
 |                  |                         |--渲染完成---------|
 |                  |                         |--upload_video()-->|
 |                  |                         |<--URL------------|
 |                  |                         |--update_job()---->|
 |                  |                         |--_jobs[id].status=done
 |                  |                         |                   |
 |---轮询 status--->|                         |                   |
 |                  |------GET /status/{id}--->|                   |
 |                  |                         |--get_job()------->|
 |                  |                         |<--state: done-----|
 |                  |<----{status: done}------|                   |
 |<----done--------|                         |                   |
 |---download----->|                         |                   |
 |                  |------GET /download/{id}->|                   |
 |                  |                         |--返回 video_url   |
 |                  |<----{video_url}---------|                   |
 |<----video_url---|                         |                   |
 |---直接播放视频---|（浏览器直接访问 Supabase Storage URL）        |
```

### 3.2 实例崩溃恢复流程

```
时间线:
T0: 用户创建任务 #123，状态 running，Supabase 已记录
T1: Render 实例 OOM 崩溃
T2: Render 新实例启动
T3: 新实例 initialize_app() → 从 Supabase 恢复 #123 到 _jobs
T4: 用户轮询 #123 → _get_job() 从 Supabase 读取 → 返回 running
T5: 孤儿清理线程运行 → #123 超过 10min 未更新 → 标记为 failed
T6: 用户轮询 #123 → 返回 failed + error_message
T7: 用户可重新提交
```

---

## 4. 边界情况处理

| 场景 | 处理策略 |
|------|---------|
| Supabase 写入失败 | `_register_job` 抛异常，返回 500，不创建内存任务 |
| Supabase 更新失败 | `_update_job` 提前返回，不同步内存，保证下次读取 Supabase 时状态一致 |
| Supabase 读取失败 | `_get_job` 回退到内存，保证服务可用性（可能读到旧状态） |
| 视频上传失败 | 任务标记为 failed，不返回本地路径（避免实例重启后文件丢失） |
| 孤儿任务被清理时，实际渲染仍在运行 | 极小概率。如果发生，渲染线程完成后尝试更新 Supabase 会发现状态已是 failed，忽略即可 |
| 多 worker 同时恢复同一任务 | `_recover_jobs_from_supabase` 使用 `_jobs_lock`，幂等覆盖 |

---

## 5. 验收标准（做到什么程度算完成）

### 5.1 功能验收（必须全部通过）

- [ ] **AC-1 任务持久化**：创建任务后，手动停止 Render 服务，重新启动，通过 `job_id` 仍能查询到任务状态，且状态与 Supabase 中一致
- [ ] **AC-2 状态一致性**：在任务渲染过程中，通过 Supabase Dashboard 直接查看 `render_jobs` 表，状态字段与 API 返回一致
- [ ] **AC-3 视频持久化**：渲染成功的任务，`download` 端点返回的 `video_url` 是 Supabase Storage URL（以 `https://...supabase.co` 开头），而非本地路径
- [ ] **AC-4 孤儿清理**：创建一个任务后手动 SIGKILL Render 进程，等待 10 分钟后重新启动，该任务状态自动变为 `failed`
- [ ] **AC-5 降级兼容**：未配置 Supabase 时（`SUPABASE_URL` 为空），系统回退到内存模式，行为与当前一致

### 5.2 集成验收（必须全部通过）

- [ ] **AC-6 端到端流程**：从前端提交代码 → 轮询状态 → 获取视频 URL → 浏览器可播放视频，全流程成功
- [ ] **AC-7 冷启动场景**：Render 实例休眠 15 分钟后，前端首次请求触发冷启动，任务创建和状态查询正常工作
- [ ] **AC-8 错误提示友好**：当任务因实例重启失败时，前端显示 `"Render instance restarted unexpectedly. Please resubmit."`

### 5.3 代码验收

- [ ] **AC-9 代码审查**：所有修改通过 `code-reviewer` agent 审查，无 CRITICAL/HIGH 级别问题
- [ ] **AC-10 无回归**：原有 Supabase 相关功能（`insert_job`, `update_job`, `get_job`, `upload_video`）继续正常工作

### 5.4 测试方法

**本地测试**：
```bash
cd render_backend
# 1. 确保 SUPABASE_URL 和 SUPABASE_SERVICE_KEY 已配置
python app.py

# 2. 创建任务
curl -X POST http://localhost:5000/render-async \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-change-in-production" \
  -d '{"code": "from manim import *\nclass Test(Scene):\n    def construct(self):\n        self.add(Circle())", "scene_name": "Test"}'

# 3. 记录返回的 job_id

# 4. 停止服务 (Ctrl+C)，重新启动

# 5. 查询任务状态（应该能查到，不是 "Job not found"）
curl http://localhost:5000/status/{job_id} \
  -H "X-API-Key: dev-key-change-in-production"
```

**Render 生产环境测试**：
1. 部署到 Render
2. 从前端提交一个复杂渲染任务
3. 在 Render Dashboard 中手动 Restart 服务
4. 前端继续轮询，应能查到任务状态（可能是 failed 或继续 running）

---

## 6. 参考信息

### 6.1 当前代码位置

| 文件 | 说明 |
|------|------|
| `render_backend/app.py` | Flask 后端主文件，包含 `_jobs` 内存存储和渲染逻辑 |
| `render_backend/supabase_client.py` | Supabase REST API 封装 |
| `render_backend/requirements.txt` | Python 依赖 |
| `api/index.py` | Vercel Gateway，透传请求到 Render Backend |
| `core/web_app.py` | 前端页面，包含状态轮询逻辑 |

### 6.2 当前状态枚举

```python
class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
```

### 6.3 前端期望状态值

```javascript
// core/web_app.js 轮询逻辑
if (statusData.status === "done" || statusData.status === "completed") { ... }
if (statusData.status === "failed" || statusData.status === "error") { ... }
```

后端返回 `"done"` 和 `"failed"` 已匹配，无需修改前端。

### 6.4 Supabase 表结构（已知字段）

表名：`render_jobs`
- `job_id` (text, PK)
- `status` (text)
- `code` (text)
- `scene_name` (text)
- `client_ip` (text, nullable)
- `video_path` (text, nullable)
- `video_bucket` (text, nullable)
- `video_name` (text, nullable)
- `error_message` (text, nullable)
- `stderr` (text, nullable)
- `metadata` (jsonb, nullable)
- `created_at` (timestamptz)
- `updated_at` (timestamptz)

表名：`job_logs`
- `job_id` (text, FK)
- `level` (text)
- `stage` (text, nullable)
- `message` (text)
- `detail` (text, nullable)
- `metadata` (jsonb, nullable)
- `created_at` (timestamptz)

---

## 7. 风险与注意事项

1. **Supabase 免费 tier 限制**：当前 Supabase 也是免费 tier，有连接数和存储限制。如果超出，需考虑升级或切换到其他持久化方案（如 Redis）。
2. **视频存储成本**：Supabase Storage 免费 tier 有 1GB 限制。需要定期清理旧视频或设置生命周期策略。
3. **Gunicorn worker 数量**：每个 worker 都会启动一个孤儿清理线程。如果 worker 数量很多（>4），需考虑把清理逻辑改为基于数据库的分布式锁（当前 1-2 个 worker 无需处理）。

---

## 8. 任务拆分（供 Codex 参考）

建议按以下顺序实现：

1. **Phase 1**：修改 `supabase_client.py` —— 新增 `list_jobs_by_status` 和重试机制
2. **Phase 2**：修改 `app.py` —— 实现 `_recover_jobs_from_supabase` 和 `_start_orphan_reaper`
3. **Phase 3**：修改 `app.py` —— 重写 `_register_job`, `_update_job`, `_get_job` 的持久化逻辑
4. **Phase 4**：修改 `app.py` —— 强制 Supabase Storage 上传，修改 `_run_manim_render`
5. **Phase 5**：修改 `app.py` —— 启动初始化（`initialize_app` + `before_request` 单例）
6. **Phase 6**：本地测试验收 AC-1 ~ AC-5
7. **Phase 7**：部署到 Render，验收 AC-6 ~ AC-8
