-- Faza 2B: Dane transakcyjne z Deweloperuch/RCN
CREATE TABLE IF NOT EXISTS transaction_prices (
    id SERIAL PRIMARY KEY,
    sale_rcn_id INT UNIQUE NOT NULL,
    city TEXT NOT NULL,
    city_slug TEXT NOT NULL,
    street_address TEXT,
    invest_slug TEXT,               -- cache key do geocodingu
    district TEXT,                  -- wypełniane przez geocoder
    amount INT NOT NULL,
    amount_sqm FLOAT NOT NULL,
    size FLOAT NOT NULL,
    rooms_number INT,
    floor_number INT,
    creation_date DATE NOT NULL,
    year INT,                       -- wypełniany przy insercie
    quarter INT,                    -- 1-4, wypełniany przy insercie
    month INT,                      -- 1-12
    is_flipped BOOLEAN DEFAULT FALSE,
    scraped_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tp_city_date    ON transaction_prices(city_slug, creation_date DESC);
CREATE INDEX IF NOT EXISTS idx_tp_city_dist    ON transaction_prices(city_slug, district, creation_date DESC);
CREATE INDEX IF NOT EXISTS idx_tp_invest_slug  ON transaction_prices(invest_slug);
CREATE INDEX IF NOT EXISTS idx_tp_year_qtr     ON transaction_prices(city_slug, year, quarter);

-- Cache wyników geocodowania (street → dzielnica)
CREATE TABLE IF NOT EXISTS geocode_cache (
    invest_slug TEXT PRIMARY KEY,
    street_address TEXT,
    district TEXT,
    lat FLOAT,
    lng FLOAT,
    cached_at TIMESTAMP DEFAULT NOW()
);
