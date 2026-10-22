-- PCM initial schema. Apply to the InsForge PostgreSQL database.
-- Store media in object/file storage, not in these relational tables.

CREATE TABLE IF NOT EXISTS pcm_jobs (
    id UUID PRIMARY KEY,
    batch_id UUID,
    owner_telegram_id BIGINT NOT NULL,
    source_url TEXT NOT NULL,
    source_identity TEXT NOT NULL,
    state TEXT NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 0,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    worker_id TEXT,
    lease_expires_at TIMESTAMPTZ,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pcm_jobs_queue
    ON pcm_jobs (priority DESC, created_at ASC)
    WHERE state IN ('queued', 'waiting_for_worker', 'retry_wait');

CREATE INDEX IF NOT EXISTS idx_pcm_jobs_owner_created
    ON pcm_jobs (owner_telegram_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pcm_jobs_lease
    ON pcm_jobs (lease_expires_at)
    WHERE worker_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS pcm_batches (
    id UUID PRIMARY KEY,
    owner_telegram_id BIGINT NOT NULL,
    requested_count INTEGER NOT NULL CHECK (requested_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pcm_job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES pcm_jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pcm_job_events_job_time
    ON pcm_job_events (job_id, created_at);

CREATE TABLE IF NOT EXISTS pcm_job_destinations (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES pcm_jobs(id) ON DELETE CASCADE,
    destination TEXT NOT NULL,
    state TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    result_url TEXT,
    error_code TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, destination)
);

CREATE TABLE IF NOT EXISTS pcm_destination_profiles (
    id BIGSERIAL PRIMARY KEY,
    owner_telegram_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_telegram_id, name)
);

CREATE TABLE IF NOT EXISTS pcm_provider_health (
    provider_id TEXT PRIMARY KEY,
    sample_count INTEGER NOT NULL DEFAULT 0 CHECK (sample_count >= 0),
    success_count INTEGER NOT NULL DEFAULT 0 CHECK (success_count >= 0),
    failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    rolling_latency_ms DOUBLE PRECISION,
    circuit_state TEXT NOT NULL DEFAULT 'closed',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
