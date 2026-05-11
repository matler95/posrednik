-- migrations/006_hunt_config.sql
-- Formalizacja tabeli hunt_config dla trybu "Snajper"

CREATE TABLE IF NOT EXISTS hunt_config (
    id          INT PRIMARY KEY,
    config      JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- Inicjalizacja domyślnego rekordu jeśli nie istnieje
INSERT INTO hunt_config (id, config, updated_at)
VALUES (1, '{
  "city_slug": "warszawa",
  "max_price": 430000,
  "min_price": 0,
  "max_area": 40,
  "min_area": 0,
  "rooms": [],
  "districts": [],
  "portals": ["otodom", "olx"],
  "direct_only": false,
  "min_score_alert": 0.25
}', NOW())
ON CONFLICT (id) DO NOTHING;
