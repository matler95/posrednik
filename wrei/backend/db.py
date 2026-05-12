"""
db.py — Database access layer (FACADE).
This file now acts as a bridge to the modularized data layer in backend/data/*.
"""
import logging
from pathlib import Path
from backend.data.connection import get_conn, PooledConnectionWrapper
from backend.data.listings import *
from backend.data.alerts import *
from backend.data.transactions import *
from backend.data.hunt import *
from backend.data.scrapes import *
from backend.data.stats import *
from backend.data.cache import *

logger = logging.getLogger(__name__)

def init_db():
    """Uruchamia migracje przy starcie aplikacji."""
    migrations_dir = Path(__file__).parent / "migrations"
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    if migrations_dir.exists():
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            cur.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (sql_file.name,))
            if cur.fetchone():
                continue
            logger.info("[DB] Aplykuję migrację: %s", sql_file.name)
            sql = sql_file.read_text(encoding="utf-8")
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)", (sql_file.name,)
            )
            conn.commit()
            logger.info("[DB] Migracja %s zakończona", sql_file.name)

    _register_portals(cur, conn)
    cur.close()
    conn.close()
    logger.info("[DB] init_db zakończony")

def _register_portals(cur, conn):
    try:
        from backend.scrapers import AVAILABLE_PORTALS
        for portal in AVAILABLE_PORTALS:
            cur.execute("""
                INSERT INTO portals (name) VALUES (%s)
                ON CONFLICT (name) DO NOTHING
            """, (portal,))
        conn.commit()
    except Exception as e:
        logger.warning("[DB] _register_portals error: %s", e)
