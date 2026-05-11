-- Faza 5: Rozszerzenie tabeli watchlist o nowe kolumny (kompatybilność wsteczna)
-- Stara tabela ma: filters (jsonb), alert_threshold, channels
-- Dodajemy: condition_expr, min_score, city_slug

ALTER TABLE watchlist
    ADD COLUMN IF NOT EXISTS condition_expr TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS min_score FLOAT DEFAULT 0.15,
    ADD COLUMN IF NOT EXISTS city_slug TEXT DEFAULT 'warszawa';

-- Migruj stare dane: przenieś alert_threshold -> min_score
UPDATE watchlist
SET min_score = COALESCE(alert_threshold, 0.15)
WHERE min_score = 0.15 AND alert_threshold IS NOT NULL;

-- Tabela logów wysłanych alertów (deduplicacja)
CREATE TABLE IF NOT EXISTS alert_sent_log (
    listing_id INT NOT NULL,
    watchlist_id INT NOT NULL,
    sent_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (listing_id, watchlist_id)
);

CREATE INDEX IF NOT EXISTS idx_asl_sent_at ON alert_sent_log(sent_at DESC);

-- Przykładowe alerty startowe
INSERT INTO watchlist (name, condition_expr, min_score, city_slug, filters, channels)
VALUES
    ('Okazje Warszawa', 'score > 0.25', 0.25, 'warszawa', '{}', '{"telegram": true}'),
    ('Mokotów bezpośrednie', 'district == ''Mokotów'' and direct_offer == True', 0.15, 'warszawa', '{}', '{"telegram": true}'),
    ('Tanie Wola', 'district == ''Wola'' and price_per_m2 < 14000', 0.10, 'warszawa', '{}', '{"telegram": true}'),
    ('RCN okazja', 'transaction_gap > 0.10 and score > 0.20', 0.20, 'warszawa', '{}', '{"telegram": true}')
ON CONFLICT DO NOTHING;
