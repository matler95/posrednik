-- 009_alert_json.sql
ALTER TABLE watchlist
    ADD COLUMN IF NOT EXISTS condition_json JSONB DEFAULT '{}';

-- Migration of existing strings to simple JSON if possible
-- 'score > 0.25' -> {"score": {"gt": 0.25}}
UPDATE watchlist
SET condition_json = jsonb_build_object('score', jsonb_build_object('gt', 0.25))
WHERE condition_expr = 'score > 0.25' AND (condition_json = '{}' OR condition_json IS NULL);

UPDATE watchlist
SET condition_json = jsonb_build_object('transaction_gap', jsonb_build_object('gt', 0.10), 'score', jsonb_build_object('gt', 0.20))
WHERE condition_expr = 'transaction_gap > 0.10 and score > 0.20' AND (condition_json = '{}' OR condition_json IS NULL);
