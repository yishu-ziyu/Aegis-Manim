# Aegis-Manim Community Works MVP

## Goal

Reduce model and render risk by reusing high-quality completed works before generating new Manim code.

When a user submits a prompt, Aegis should first search published community works. If a strong match exists, the page should show the existing code and MP4 immediately. If no match exists, the current `/api/generate -> /api/render -> status -> video_url` flow remains unchanged.

## Current Base

- Vercel is the public gateway and browser UI host.
- Render owns long-running Manim rendering and Supabase service access.
- Supabase stores render job state in `render_jobs`, logs in `job_logs`, and MP4 files in the `manim-videos` bucket.
- Existing render jobs are task records. The preferred community schema stores reusable works in dedicated `community_*` tables, but the implemented MVP also has a compatibility fallback that stores publish state, ratings, score, and reuse counts in `render_jobs.metadata` when those tables have not been migrated yet.

## MVP Architecture

```text
User prompt
  -> Vercel /api/community/search?q=...
  -> Render community search API
  -> Supabase community_works
  -> hit: return code + video_url, skip model and render
  -> miss: continue current /api/generate and /api/render flow
  -> after successful render: user can submit the result as a candidate work
  -> reviewer approves/features/quarantines/hides/rejects it
```

Keep Supabase service credentials in Render. Vercel should only proxy community API calls.

## Migration Compatibility

The Render backend first tries the dedicated `community_works`, `community_work_ratings`, and `community_work_events` tables. If Supabase returns a missing-table response, it automatically falls back to the already-deployed `render_jobs` table:

- Repository state is stored as `metadata.community_status`.
- Search reads completed jobs with `metadata->>community_status = published` and ranks them by metadata quality signals.
- Candidate submission writes the completed render job's community fields back into `render_jobs.metadata`; browser-supplied code and video URLs are still ignored.
- Review writes `community_review_stage`, `community_review_status`, `community_repository_decision`, and reviewer metadata back into `render_jobs.metadata`.
- Rating and reuse update metadata on the same render job.

This lets the cloud MVP work before the new tables are applied. The dedicated tables remain the target structure for moderation, richer search, and cleaner analytics.

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
    status text NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'published', 'featured', 'quarantine', 'hidden', 'rejected')),
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
    WHERE status IN ('published', 'featured');

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
    event_type text NOT NULL CHECK (event_type IN ('reuse', 'rating', 'review', 'promote', 'demote')),
    query text,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
```

MVP search can use Postgres full-text search plus score ordering. Embeddings are a later enhancement, not a prerequisite.

## API

### Search

`GET /api/community/search?q=帕累托最优&limit=5`

Returns public works only: `published` and `featured`. Automatic reuse should only use the top result when it has a valid `video_url`, acceptable score, and public status.

### Submit Candidate

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
- New submissions enter `candidate`, not public search.
- Review metadata is attached immediately: `review_stage=candidate`, `review_status=pending`, and `repository_decision=pending_review`.

### Review Queue

`GET /api/community/review/queue?status=candidate&limit=20&reviewToken=...`

Returns candidate or other non-public works for administrator review.

`POST /api/community/works/{work_id}/review`

Body:

```json
{
  "decision": "approve",
  "reviewToken": "server-configured-token",
  "reviewerLabel": "Aegis 管理员",
  "note": "经济学解释清楚，适合公开复用"
}
```

Supported decisions:

- `approve` or `publish` -> `published`
- `feature` -> `featured`
- `quarantine` -> `quarantine`
- `hide` -> `hidden`
- `reject` -> `rejected`

Review requires the Render backend env var `AEGIS_COMMUNITY_REVIEW_TOKEN` or `COMMUNITY_REVIEW_TOKEN`. The browser panel stores the typed token in local browser storage; the token is not hardcoded into the public bundle.

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
   - show a "提交入库审阅" action.
7. On a displayed community work:
   - show rating control and write rating events.
8. In the folded review panel:
   - reviewer enters the review token;
   - loads `candidate`, `quarantine`, `hidden`, or `rejected` queues;
   - promotes, features, quarantines, hides, or rejects each work.

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
- Successful renders can be submitted as `candidate` community works.
- Candidate works do not appear in public search before review.
- Review can promote a candidate to `published` or `featured`.
- Quarantined, hidden, and rejected works stay out of public search.
- Ratings update `rating_avg`, `rating_count`, and `quality_score`.
- Reuse increments `reuse_count` and records an event.
- Vercel does not receive Supabase service credentials.
- Existing health and render endpoints keep their current behavior.

## Risks

- False positive matches: keep thresholds conservative and expose a "重新生成" action.
- Low-quality uploads: only allow publishing completed renders, add hide/reject status from day one.
- Storage growth: later clean low-score, low-reuse, old works.
- Render capacity: cache hits reduce load, but misses still need the current worker or a future Cloud Run Jobs/Modal-style worker.
