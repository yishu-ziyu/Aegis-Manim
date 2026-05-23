# Aegis-Manim Community Works MVP

## Goal

Reduce model and render risk by reusing high-quality completed works before generating new Manim code.

When a user submits a prompt, Aegis should first search published community works. If a strong match exists, the page should show the existing code and MP4 immediately. If no match exists, the current `/api/generate -> /api/render -> status -> video_url` flow remains unchanged.

## Current Base

- Vercel is the public gateway and browser UI host.
- Render owns long-running Manim rendering and Supabase service access.
- Supabase stores render job state in `render_jobs`, logs in `job_logs`, and MP4 files in the `manim-videos` bucket.
- Existing render jobs are task records, not reusable works. They do not store search rank, ratings, publish state, or reuse counts.

## MVP Architecture

```text
User prompt
  -> Vercel /api/community/search?q=...
  -> Render community search API
  -> Supabase community_works
  -> hit: return code + video_url, skip model and render
  -> miss: continue current /api/generate and /api/render flow
  -> after successful render: user can publish the result to community_works
```

Keep Supabase service credentials in Render. Vercel should only proxy community API calls.

## Tables

```sql
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
    status text NOT NULL DEFAULT 'published'
        CHECK (status IN ('published', 'hidden', 'rejected')),
    quality_score numeric NOT NULL DEFAULT 0,
    rating_avg numeric NOT NULL DEFAULT 0,
    rating_count int NOT NULL DEFAULT 0,
    reuse_count int NOT NULL DEFAULT 0,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_community_works_quality
    ON community_works (quality_score DESC, rating_avg DESC, reuse_count DESC, created_at DESC)
    WHERE status = 'published';

CREATE INDEX IF NOT EXISTS idx_community_works_prompt_normalized
    ON community_works USING gin (prompt_normalized gin_trgm_ops);

CREATE TABLE IF NOT EXISTS community_work_ratings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_id uuid NOT NULL REFERENCES community_works(id) ON DELETE CASCADE,
    rater_key text NOT NULL,
    rating int NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (work_id, rater_key)
);

CREATE TABLE IF NOT EXISTS community_work_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_id uuid NOT NULL REFERENCES community_works(id) ON DELETE CASCADE,
    event_type text NOT NULL CHECK (event_type IN ('reuse')),
    query text,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
```

MVP search can use Postgres full-text search plus score ordering. Embeddings are a later enhancement, not a prerequisite.

## API

### Search

`GET /api/community/search?q=帕累托最优&limit=5`

Returns published works only. Automatic reuse should only use the top result when it has a valid `video_url`, acceptable score, and status `published`.

### Publish

`POST /api/community/works`

Body:

```json
{
  "title": "帕累托最优可视化",
  "prompt": "可视化帕累托最优过程。",
  "sceneName": "GeneratedScene",
  "code": "from manim import * ...",
  "videoUrl": "https://...supabase.co/storage/v1/object/public/manim-videos/...",
  "renderJobId": "fd693826-...",
  "tags": ["经济学", "帕累托"]
}
```

Validation:

- `videoUrl` must be an existing public URL from the current Supabase `manim-videos` bucket.
- `renderJobId` is required in the implemented MVP. Render loads the completed job's persisted `code`, `scene_name`, and `video_path` server-side instead of trusting browser-submitted code/video fields.
- `code` must pass existing compatibility and render-budget checks before the original render job can complete.
- MVP may publish immediately, but the schema keeps `hidden` and `rejected` states for moderation.

### Rate

`POST /api/community/works/{work_id}/rating`

Body:

```json
{"rating": 5, "comment": "讲得清楚，中文显示正常"}
```

Ratings should be unique by anonymous `rater_key` for MVP.

### Reuse Event

`POST /api/community/works/{work_id}/reuse`

Records a cache hit and increments `reuse_count`.

## Frontend Flow

1. User clicks generate.
2. UI shows "正在搜索已有高质量作品...".
3. Call `/api/community/search`.
4. On strong hit:
   - set generated code panel from `item.code`;
   - set video player `src` to `item.videoUrl`;
   - show "已复用社区高分作品";
   - call reuse event;
   - do not call `/api/generate` or `/api/render`.
5. On miss:
   - keep current generate and render flow.
6. After successful render:
   - show a "发布到作品库" action with title and tags.
7. On a displayed community work:
   - show rating control and write rating events.

## Quality Score

Start simple:

```text
quality_score =
  0.45 * normalized_rating_avg
+ 0.25 * log(1 + reuse_count)
+ 0.15 * render_success_bonus
+ 0.15 * freshness
- moderation_penalty
```

The exact formula can live in backend code first. Move it to SQL later only if needed.

## Acceptance Criteria

- A prompt matching a published work returns a playable `videoUrl` without calling `/api/generate` or `/api/render`.
- A prompt without a match still follows the current production flow.
- Successful renders can be published into `community_works`.
- Ratings update `rating_avg`, `rating_count`, and `quality_score`.
- Reuse increments `reuse_count` and records an event.
- Vercel does not receive Supabase service credentials.
- Existing health and render endpoints keep their current behavior.

## Risks

- False positive matches: keep thresholds conservative and expose a "重新生成" action.
- Low-quality uploads: only allow publishing completed renders, add hide/reject status from day one.
- Storage growth: later clean low-score, low-reuse, old works.
- Render capacity: cache hits reduce load, but misses still need the current worker or a future Cloud Run Jobs/Modal-style worker.
