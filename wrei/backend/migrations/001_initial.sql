-- migrations/001_initial.sql
-- Uruchom raz przy pierwszym starcie lub przez init_db()

CREATE TABLE IF NOT EXISTS portals (
    name            TEXT PRIMARY KEY,
    enabled         BOOLEAN DEFAULT TRUE,
    last_scraped    TIMESTAMP,
    listings_last_run INT DEFAULT 0,
    error_rate      FLOAT DEFAULT 0.0,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id              SERIAL PRIMARY KEY,
    portal          TEXT REFERENCES portals(name) ON DELETE SET NULL,
    pages           INT,
    direct_only     BOOLEAN,
    query_url       TEXT,
    status          TEXT,       -- 'completed' | 'failed' | 'partial'
    listings_count  INT DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMP DEFAULT NOW(),
    finished_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS listings (
    id              SERIAL PRIMARY KEY,
    portal          TEXT,
    title           TEXT,
    price           INT,
    area            FLOAT,
    district        TEXT,
    rooms           TEXT,
    url             TEXT UNIQUE,
    price_per_m2    FLOAT,
    estimated_value FLOAT,
    score           FLOAT,
    direct_offer    BOOLEAN DEFAULT FALSE,
    source          TEXT,
    description     TEXT,

    -- Nowe pola Faza 1
    images          JSONB DEFAULT '[]',
    features        JSONB DEFAULT '{}',
    floor           INT,
    total_floors    INT,
    year_built      INT,
    heating         TEXT,
    condition       TEXT,       -- 'nowy' | 'dobry' | 'sredni' | 'remont'
    building_type   TEXT,       -- 'blok' | 'kamienica' | 'apartament' | 'szeregowiec'
    ownership       TEXT,       -- 'pelna' | 'spoldzielcze' | 'udzial'
    raw_location    JSONB DEFAULT '{}',

    -- Analiza (Fazy 3/4 — NULL dopóki nie przetworzone)
    llm_analysis    JSONB,
    photo_analysis  JSONB,

    -- Tracking
    first_seen      TIMESTAMP DEFAULT NOW(),
    days_on_market  INT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS listing_history (
    id              SERIAL PRIMARY KEY,
    listing_url     TEXT,
    portal          TEXT,
    price           INT,
    area            FLOAT,
    price_per_m2    FLOAT,
    score           FLOAT,
    district        TEXT,
    rooms           INT,
    condition       TEXT,
    building_type   TEXT,
    floor           INT,
    year_built      INT,
    recorded_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_stats (
    id              SERIAL PRIMARY KEY,
    district        TEXT NOT NULL,
    rooms           INT,            -- NULL = wszystkie pokoje
    condition       TEXT,           -- NULL = wszystkie stany
    avg_price_per_m2    FLOAT,
    median_price_per_m2 FLOAT,
    p25_price_per_m2    FLOAT,
    p75_price_per_m2    FLOAT,
    sample_count    INT DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (district, rooms, condition)
);

CREATE TABLE IF NOT EXISTS alerts (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    expression      TEXT NOT NULL,  -- Python expression ewaluowany na listingu
    enabled         BOOLEAN DEFAULT TRUE,
    channels        JSONB DEFAULT '{"telegram": true}',
    last_triggered  TIMESTAMP,
    trigger_count   INT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS watchlist (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    filters         JSONB NOT NULL,     -- {district, min_area, max_price, rooms, ...}
    alert_threshold FLOAT DEFAULT 0.15,
    channels        JSONB DEFAULT '{"telegram": true}',
    active          BOOLEAN DEFAULT TRUE,
    last_checked    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Indeksy
CREATE INDEX IF NOT EXISTS idx_listings_portal     ON listings(portal);
CREATE INDEX IF NOT EXISTS idx_listings_district   ON listings(district);
CREATE INDEX IF NOT EXISTS idx_listings_score      ON listings(score DESC);
CREATE INDEX IF NOT EXISTS idx_listings_price      ON listings(price);
CREATE INDEX IF NOT EXISTS idx_listings_created_at ON listings(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_listing_history_url ON listing_history(listing_url);
CREATE INDEX IF NOT EXISTS idx_listing_history_rec ON listing_history(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_stats_lookup ON market_stats(district, rooms, condition);