import json
import os

import psycopg2
from psycopg2.extras import Json, execute_values


def get_conn():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "wrei"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", 5432),
    )


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id SERIAL PRIMARY KEY,
            portal TEXT,
            pages INT,
            direct_only BOOLEAN,
            query_url TEXT,
            status TEXT,
            listings_count INT,
            started_at TIMESTAMP DEFAULT NOW(),
            finished_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS listings (
            id SERIAL PRIMARY KEY,
            portal TEXT,
            title TEXT,
            price INT,
            area FLOAT,
            district TEXT,
            rooms TEXT,
            url TEXT UNIQUE,
            price_per_m2 FLOAT,
            estimated_value FLOAT,
            score FLOAT,
            direct_offer BOOLEAN,
            source TEXT,
            description TEXT,
            raw_location JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS listing_history (
            id SERIAL PRIMARY KEY,
            listing_url TEXT,
            price INT,
            area FLOAT,
            score FLOAT,
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY,
            name TEXT,
            expression TEXT,
            enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def record_scrape_run(portal, pages, direct_only, status, listings_count, query_url=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scrape_runs (portal, pages, direct_only, query_url, status, listings_count, finished_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """,
        (portal, pages, direct_only, query_url, status, listings_count),
    )
    run_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return run_id


def save_listings(listings):
    if not listings:
        return

    conn = get_conn()
    cur = conn.cursor()
    records = []
    for listing in listings:
        records.append(
            (
                listing.get("portal"),
                listing.get("title"),
                listing.get("price"),
                listing.get("area"),
                listing.get("district"),
                listing.get("rooms"),
                listing.get("url"),
                listing.get("price_per_m2"),
                listing.get("estimated_value"),
                listing.get("score"),
                listing.get("direct_offer"),
                listing.get("source"),
                listing.get("description"),
                Json(listing.get("raw_location") or {}),
            )
        )
    execute_values(
        cur,
        """
        INSERT INTO listings (
            portal, title, price, area, district, rooms, url,
            price_per_m2, estimated_value, score, direct_offer, source,
            description, raw_location
        )
        VALUES %s
        ON CONFLICT (url) DO UPDATE SET
            portal = EXCLUDED.portal,
            title = EXCLUDED.title,
            price = EXCLUDED.price,
            area = EXCLUDED.area,
            district = EXCLUDED.district,
            rooms = EXCLUDED.rooms,
            price_per_m2 = EXCLUDED.price_per_m2,
            estimated_value = EXCLUDED.estimated_value,
            score = EXCLUDED.score,
            direct_offer = EXCLUDED.direct_offer,
            source = EXCLUDED.source,
            description = EXCLUDED.description,
            raw_location = EXCLUDED.raw_location,
            updated_at = NOW()
        """,
        records,
    )
    conn.commit()
    cur.close()
    conn.close()


def save_listing_history(listings):
    if not listings:
        return

    conn = get_conn()
    cur = conn.cursor()
    records = []
    for listing in listings:
        records.append(
            (
                listing.get("url"),
                listing.get("price"),
                listing.get("area"),
                listing.get("score"),
            )
        )
    execute_values(
        cur,
        """
        INSERT INTO listing_history (listing_url, price, area, score)
        VALUES %s
        """,
        records,
    )
    conn.commit()
    cur.close()
    conn.close()
