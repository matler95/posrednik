-- migrations/002_migrate_existing.sql
-- Bezpieczne — używa IF NOT EXISTS / DO $$ EXCEPTION

DO $$
BEGIN
    -- listings — nowe kolumny
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='images') THEN
        ALTER TABLE listings ADD COLUMN images JSONB DEFAULT '[]';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='features') THEN
        ALTER TABLE listings ADD COLUMN features JSONB DEFAULT '{}';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='floor') THEN
        ALTER TABLE listings ADD COLUMN floor INT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='total_floors') THEN
        ALTER TABLE listings ADD COLUMN total_floors INT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='year_built') THEN
        ALTER TABLE listings ADD COLUMN year_built INT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='heating') THEN
        ALTER TABLE listings ADD COLUMN heating TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='condition') THEN
        ALTER TABLE listings ADD COLUMN condition TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='building_type') THEN
        ALTER TABLE listings ADD COLUMN building_type TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='ownership') THEN
        ALTER TABLE listings ADD COLUMN ownership TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='llm_analysis') THEN
        ALTER TABLE listings ADD COLUMN llm_analysis JSONB;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='photo_analysis') THEN
        ALTER TABLE listings ADD COLUMN photo_analysis JSONB;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='first_seen') THEN
        ALTER TABLE listings ADD COLUMN first_seen TIMESTAMP DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listings' AND column_name='days_on_market') THEN
        ALTER TABLE listings ADD COLUMN days_on_market INT DEFAULT 0;
    END IF;

    -- listing_history — nowe kolumny
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listing_history' AND column_name='portal') THEN
        ALTER TABLE listing_history ADD COLUMN portal TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listing_history' AND column_name='price_per_m2') THEN
        ALTER TABLE listing_history ADD COLUMN price_per_m2 FLOAT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listing_history' AND column_name='district') THEN
        ALTER TABLE listing_history ADD COLUMN district TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listing_history' AND column_name='rooms') THEN
        ALTER TABLE listing_history ADD COLUMN rooms INT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listing_history' AND column_name='condition') THEN
        ALTER TABLE listing_history ADD COLUMN condition TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listing_history' AND column_name='building_type') THEN
        ALTER TABLE listing_history ADD COLUMN building_type TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listing_history' AND column_name='floor') THEN
        ALTER TABLE listing_history ADD COLUMN floor INT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listing_history' AND column_name='year_built') THEN
        ALTER TABLE listing_history ADD COLUMN year_built INT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='listing_history' AND column_name='recorded_at') THEN
        ALTER TABLE listing_history ADD COLUMN recorded_at TIMESTAMP DEFAULT NOW();
    END IF;

    RAISE NOTICE 'Migracja 002 zakończona';
END $$;

-- Nowe tabele (idempotentne)
CREATE TABLE IF NOT EXISTS market_stats (
    id                  SERIAL PRIMARY KEY,
    district            TEXT NOT NULL,
    rooms               INT,
    condition           TEXT,
    avg_price_per_m2    FLOAT,
    median_price_per_m2 FLOAT,
    p25_price_per_m2    FLOAT,
    p75_price_per_m2    FLOAT,
    sample_count        INT DEFAULT 0,
    updated_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (district, rooms, condition)
);

CREATE TABLE IF NOT EXISTS portals (
    name                TEXT PRIMARY KEY,
    enabled             BOOLEAN DEFAULT TRUE,
    last_scraped        TIMESTAMP,
    listings_last_run   INT DEFAULT 0,
    error_rate          FLOAT DEFAULT 0.0,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS watchlist (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    filters         JSONB NOT NULL,
    alert_threshold FLOAT DEFAULT 0.15,
    channels        JSONB DEFAULT '{"telegram": true}',
    active          BOOLEAN DEFAULT TRUE,
    last_checked    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Nowe kolumny w alerts
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='alerts' AND column_name='channels') THEN
        ALTER TABLE alerts ADD COLUMN channels JSONB DEFAULT '{"telegram": true}';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='alerts' AND column_name='last_triggered') THEN
        ALTER TABLE alerts ADD COLUMN last_triggered TIMESTAMP;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='alerts' AND column_name='trigger_count') THEN
        ALTER TABLE alerts ADD COLUMN trigger_count INT DEFAULT 0;
    END IF;
END $$;

-- Indeksy (idempotentne)
CREATE INDEX IF NOT EXISTS idx_listings_portal     ON listings(portal);
CREATE INDEX IF NOT EXISTS idx_listings_district   ON listings(district);
CREATE INDEX IF NOT EXISTS idx_listings_score      ON listings(score DESC);
CREATE INDEX IF NOT EXISTS idx_listings_price      ON listings(price);
CREATE INDEX IF NOT EXISTS idx_listings_created_at ON listings(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_listing_history_url ON listing_history(listing_url);
CREATE INDEX IF NOT EXISTS idx_listing_history_rec ON listing_history(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_stats_lookup ON market_stats(district, rooms, condition);