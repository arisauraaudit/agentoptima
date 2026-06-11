-- AgentOptima Proxy Gateway — DB Migration 001
-- Phase 1: API keys, cache, savings log
-- Run once against Railway PostgreSQL

-- ── API Keys ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash            TEXT UNIQUE NOT NULL,   -- SHA256 of raw key, never store raw
    user_label          TEXT,
    user_email          TEXT,
    budget_limit_cents  INTEGER DEFAULT 500,    -- $5.00 default hard limit
    spent_cents         REAL DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    last_used_at        TIMESTAMPTZ,
    enabled             BOOLEAN DEFAULT TRUE,
    plan                TEXT DEFAULT 'free'     -- 'free' | 'pro' | 'builder'
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);

-- ── Response Cache ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS response_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cache_key       TEXT UNIQUE NOT NULL,   -- SHA256 of normalized prompt
    request_hash    TEXT NOT NULL,
    response_json   JSONB NOT NULL,
    model_used      TEXT NOT NULL,
    cost_cents      REAL NOT NULL,
    hit_count       INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,            -- NULL = never expires
    cache_type      TEXT DEFAULT 'exact'    -- 'exact' | 'semantic'
);

CREATE INDEX IF NOT EXISTS idx_cache_key ON response_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON response_cache(expires_at) WHERE expires_at IS NOT NULL;

-- ── Savings Log ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS savings_log (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id              UUID REFERENCES api_keys(id),
    date                    DATE NOT NULL,
    cache_hits              INTEGER DEFAULT 0,
    tokens_saved            INTEGER DEFAULT 0,
    cost_saved_cents        REAL DEFAULT 0,     -- from cache hits
    routing_saved_cents     REAL DEFAULT 0,     -- from smart routing vs GPT-4o baseline
    actual_cost_cents       REAL DEFAULT 0,
    UNIQUE (api_key_id, date)
);

CREATE INDEX IF NOT EXISTS idx_savings_key_date ON savings_log(api_key_id, date);

-- ── Cleanup: expire old cache entries (run via cron later) ───────────────────
-- DELETE FROM response_cache WHERE expires_at < NOW();
