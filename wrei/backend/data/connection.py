import logging
import os
from psycopg2 import pool
from psycopg2.extras import register_default_jsonb

logger = logging.getLogger(__name__)

_pool = None

def init_pool():
    global _pool
    if _pool is None:
        logger.info("[DB] Initializing connection pool...")
        _pool = pool.ThreadedConnectionPool(
            minconn=int(os.getenv("DB_MIN_CONN", 2)),
            maxconn=int(os.getenv("DB_MAX_CONN", 10)),
            dbname=os.getenv("POSTGRES_DB", "wrei"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            host=os.getenv("POSTGRES_HOST", "db"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
        )

class PooledConnectionWrapper:
    """
    Context manager and wrapper for pooled database connections.
    Ensures connection is returned to pool after use.
    """
    def __init__(self):
        if _pool is None:
            init_pool()
        self.conn = _pool.getconn()
        register_default_jsonb(self.conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            try:
                self.conn.rollback()
            except Exception as e:
                logger.error("[DB] Rollback error: %s", e)
        self.close()

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def close(self):
        if _pool is not None and self.conn is not None:
            _pool.putconn(self.conn)
            self.conn = None

    def commit(self):
        if self.conn:
            self.conn.commit()

    def rollback(self):
        if self.conn:
            self.conn.rollback()

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)

def get_conn():
    """Returns a PooledConnectionWrapper instance."""
    return PooledConnectionWrapper()
