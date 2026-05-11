-- Migracja 005: Dodanie kolumn RCN/ML do tabeli listings
-- Wymagane przez: analysis.py, model.py, dashboard, alerty

ALTER TABLE listings
    ADD COLUMN IF NOT EXISTS rcn_benchmark    FLOAT,
    ADD COLUMN IF NOT EXISTS cagr_5y          FLOAT,
    ADD COLUMN IF NOT EXISTS transaction_gap  FLOAT,
    ADD COLUMN IF NOT EXISTS text_score       FLOAT,
    ADD COLUMN IF NOT EXISTS photo_score      FLOAT,
    ADD COLUMN IF NOT EXISTS days_on_market   INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS city_slug        TEXT DEFAULT 'warszawa',
    ADD COLUMN IF NOT EXISTS lat              FLOAT,
    ADD COLUMN IF NOT EXISTS lng              FLOAT;

-- Indeksy analityczne
CREATE INDEX IF NOT EXISTS idx_listings_transaction_gap ON listings(transaction_gap DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_listings_district_score  ON listings(district, score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_listings_city_slug       ON listings(city_slug);
CREATE INDEX IF NOT EXISTS idx_listings_created_at      ON listings(created_at DESC);

-- Uzupełnij days_on_market dla istniejących rekordów
UPDATE listings
SET days_on_market = GREATEST(0, EXTRACT(DAY FROM (NOW() - first_seen))::INT)
WHERE days_on_market = 0 AND first_seen IS NOT NULL;
