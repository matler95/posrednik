-- Migracja 010: Zmiana typu sale_rcn_id na TEXT
ALTER TABLE transaction_prices ALTER COLUMN sale_rcn_id TYPE TEXT;
