-- Aegis-Manim 渲染系统数据库结构
-- 在 Supabase SQL 编辑器中执行

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 渲染任务主表
CREATE TABLE IF NOT EXISTS render_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    code text NOT NULL,
    scene_name text NOT NULL DEFAULT 'GeneratedScene',
    video_path text,
    video_bucket text,
    video_name text,
    error_message text,
    stderr text,
    client_ip text,
    metadata jsonb DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- 任务日志表
CREATE TABLE IF NOT EXISTS job_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id text NOT NULL REFERENCES render_jobs(job_id) ON DELETE CASCADE,
    level text NOT NULL DEFAULT 'info' CHECK (level IN ('debug', 'info', 'warn', 'error')),
    stage text,
    message text NOT NULL,
    detail text,
    metadata jsonb DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_render_jobs_status ON render_jobs(status);
CREATE INDEX IF NOT EXISTS idx_render_jobs_created_at ON render_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id);
CREATE INDEX IF NOT EXISTS idx_job_logs_created_at ON job_logs(created_at DESC);

-- 社区作品复用库：保存已渲染成功、可复用的视频作品
CREATE TABLE IF NOT EXISTS community_works (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    prompt text NOT NULL,
    prompt_normalized text NOT NULL,
    scene_name text NOT NULL DEFAULT 'GeneratedScene',
    code text NOT NULL,
    video_url text NOT NULL,
    render_job_id text REFERENCES render_jobs(job_id) ON DELETE SET NULL,
    author_label text,
    tags text[] DEFAULT '{}',
    status text NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'hidden', 'rejected')),
    rating_avg numeric(3,2) NOT NULL DEFAULT 0,
    rating_count int NOT NULL DEFAULT 0,
    reuse_count int NOT NULL DEFAULT 0,
    quality_score numeric(6,4) NOT NULL DEFAULT 0,
    metadata jsonb DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS community_work_ratings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_id uuid NOT NULL REFERENCES community_works(id) ON DELETE CASCADE,
    rater_key text NOT NULL,
    rating int NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (work_id, rater_key)
);

CREATE TABLE IF NOT EXISTS community_work_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_id uuid NOT NULL REFERENCES community_works(id) ON DELETE CASCADE,
    event_type text NOT NULL CHECK (event_type IN ('reuse')),
    query text,
    metadata jsonb DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_community_works_quality
    ON community_works (quality_score DESC, rating_avg DESC, reuse_count DESC, created_at DESC)
    WHERE status = 'published';
CREATE INDEX IF NOT EXISTS idx_community_works_prompt_normalized ON community_works USING gin (prompt_normalized gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_community_work_ratings_work_id ON community_work_ratings(work_id);
CREATE INDEX IF NOT EXISTS idx_community_work_events_work_id ON community_work_events(work_id);

-- 自动更新 updated_at 触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_render_jobs_updated_at ON render_jobs;
CREATE TRIGGER update_render_jobs_updated_at
    BEFORE UPDATE ON render_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_community_works_updated_at ON community_works;
CREATE TRIGGER update_community_works_updated_at
    BEFORE UPDATE ON community_works
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_community_work_ratings_updated_at ON community_work_ratings;
CREATE TRIGGER update_community_work_ratings_updated_at
    BEFORE UPDATE ON community_work_ratings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- RLS 策略：允许匿名插入和按 job_id 查询
ALTER TABLE render_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_works ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_work_ratings ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_work_events ENABLE ROW LEVEL SECURITY;

-- 允许任何人创建任务（通过 API Key 在应用层控制）
CREATE POLICY allow_insert_jobs ON render_jobs
    FOR INSERT TO anon, authenticated
    WITH CHECK (true);

-- 允许任何人通过 job_id 查询任务
CREATE POLICY allow_select_jobs ON render_jobs
    FOR SELECT TO anon, authenticated
    USING (true);

-- 允许任何人更新任务状态（渲染后端更新）
CREATE POLICY allow_update_jobs ON render_jobs
    FOR UPDATE TO anon, authenticated
    USING (true)
    WITH CHECK (true);

-- 允许任何人插入日志
CREATE POLICY allow_insert_logs ON job_logs
    FOR INSERT TO anon, authenticated
    WITH CHECK (true);

-- 允许任何人查询日志
CREATE POLICY allow_select_logs ON job_logs
    FOR SELECT TO anon, authenticated
    USING (true);

-- 社区表：浏览器不直接写入；公开读仅限已发布作品，写入由 Render service-role API 执行
CREATE POLICY allow_select_published_community_works ON community_works
    FOR SELECT TO anon, authenticated
    USING (status = 'published');

-- 创建一个函数用于清理旧任务（可选，通过 pg_cron 调用）
CREATE OR REPLACE FUNCTION cleanup_old_render_jobs(older_than_days int DEFAULT 7)
RETURNS int AS $$
DECLARE
    deleted_count int;
BEGIN
    DELETE FROM render_jobs
    WHERE status IN ('done', 'failed')
      AND updated_at < now() - interval '1 day' * older_than_days;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
