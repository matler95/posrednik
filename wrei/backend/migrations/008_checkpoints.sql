-- 008_checkpoints.sql
CREATE TABLE IF NOT EXISTS job_checkpoints (
    job_key TEXT PRIMARY KEY,
    data JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);
