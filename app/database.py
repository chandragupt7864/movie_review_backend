import logging
from contextlib import contextmanager
import time

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from app.config import settings


logger = logging.getLogger(__name__)

_connection_pool: ThreadedConnectionPool | None = None


def get_connection_pool() -> ThreadedConnectionPool:
    global _connection_pool
    if _connection_pool is None:
        if not settings.database_url:
            raise ValueError("DATABASE_URL is not configured.")
        last_error = None
        for attempt in range(8):
            try:
                _connection_pool = ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    dsn=settings.database_url,
                )
                break
            except psycopg2.OperationalError as exc:
                last_error = exc
                if attempt < 7:
                    time.sleep(min(5.0, 1.5 * (attempt + 1)))
        if _connection_pool is None:
            raise last_error or psycopg2.OperationalError("Could not create the database connection pool.")
    return _connection_pool


def _get_pool_connection_with_retry(pool):
    last_error = None
    for attempt in range(8):
        try:
            return pool.getconn()
        except psycopg2.OperationalError as exc:
            last_error = exc
            if attempt < 7:
                time.sleep(min(5.0, 1.5 * (attempt + 1)))
    raise last_error or psycopg2.OperationalError("Could not acquire a database connection.")


def _is_connection_alive(conn) -> bool:
    """
    Check karo ki connection abhi bhi DB se connected hai ya nahi.
    Ek lightweight query se test hota hai.
    """
    try:
        conn.cursor().execute("SELECT 1")
        return True
    except Exception:
        return False


def _get_fresh_connection():
    """
    Pool se connection lo — agar connection dead/stale hai toh close karke
    naya fresh connection lo. Isse 'server closed the connection unexpectedly'
    error nahi aata.
    """
    pool = get_connection_pool()
    conn = _get_pool_connection_with_retry(pool)

    # Connection alive hai?
    if conn.closed or not _is_connection_alive(conn):
        logger.warning("Stale DB connection detected — closing and reopening.")
        try:
            pool.putconn(conn, close=True)  # Pool se permanently hata do
        except Exception:
            pass
        # Naya connection lo
        conn = _get_pool_connection_with_retry(pool)

    # Connection rollback karo taaki koi purana failed transaction na ho
    try:
        if conn.status != psycopg2.extensions.STATUS_READY:
            conn.rollback()
    except Exception:
        pass

    return conn


def _return_connection(pool, conn) -> None:
    """
    Connection pool ko wapas do. Agar connection broken hai toh permanently
    close karo (pool se hata do) taaki doosra thread use na kare.
    """
    try:
        if conn.closed:
            pool.putconn(conn, close=True)
        else:
            pool.putconn(conn)
    except Exception as exc:
        logger.warning("Error returning connection to pool: %s", exc)
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass


@contextmanager
def get_db_cursor(commit: bool = False):
    pool = get_connection_pool()
    conn = _get_fresh_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        _return_connection(pool, conn)
