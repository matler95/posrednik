-- Stage 1: Backend Core Updates

-- 1. Rozszerzenie tabeli listings
ALTER TABLE listings ADD COLUMN IF NOT EXISTS preliminary_score FLOAT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS score_version INT DEFAULT 1;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS anomaly_score FLOAT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS llm_error_count INT DEFAULT 0;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS price_drop_days INT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS last_enriched_at TIMESTAMP;

-- 2. Tabela hunt_jobs dla persystencji i statusu
CREATE TABLE IF NOT EXISTS hunt_jobs (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL,
    config JSONB NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP,
    total_scraped INT DEFAULT 0,
    total_saved INT DEFAULT 0,
    total_ai_analyzed INT DEFAULT 0,
    error TEXT,
    portals_counts JSONB DEFAULT '{}'
);

-- 3. Tabela price_alerts dla śledzenia zmian i anomalii
CREATE TABLE IF NOT EXISTS price_alerts (
    id SERIAL PRIMARY KEY,
    listing_id INT REFERENCES listings(id),
    alert_type TEXT, -- 'price_drop', 'new_high_score', 'anomaly'
    old_value FLOAT,
    new_value FLOAT,
    triggered_at TIMESTAMP DEFAULT NOW(),
    sent_at TIMESTAMP
);

-- 4. Indeksy dla wydajności
CREATE INDEX IF NOT EXISTS idx_listings_url_updated ON listings(url, updated_at);
CREATE INDEX IF NOT EXISTS idx_listings_preliminary_score ON listings(preliminary_score DESC) WHERE preliminary_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_txn_prices_invest_district ON transaction_prices(invest_slug, district);
CREATE INDEX IF NOT EXISTS idx_hunt_jobs_started_at ON hunt_jobs(started_at DESC);
