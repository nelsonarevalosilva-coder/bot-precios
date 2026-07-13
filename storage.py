import sqlite3
import threading
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "prices.db"
_db_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT NOT NULL,
                url TEXT NOT NULL,
                price INTEGER NOT NULL,
                checked_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notified_discounts (
                url TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                discount_pct REAL NOT NULL,
                sale_price INTEGER NOT NULL,
                notified_at TEXT NOT NULL,
                channel_key TEXT
            )
        """)
        # Migración: agregar channel_key si no existe
        try:
            conn.execute("ALTER TABLE notified_discounts ADD COLUMN channel_key TEXT")
        except Exception:
            pass
        conn.commit()


def has_been_notified(url: str, sale_price: int) -> bool:
    """Retorna True si ya notificamos este producto a este precio o menor (no hay mejora)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT sale_price FROM notified_discounts WHERE url = ?",
            (url,),
        ).fetchone()
        if row is None:
            return False
        last_price = row[0]
        return sale_price >= last_price


def get_last_notified_price(url: str) -> int | None:
    """Retorna el precio de la última notificación enviada, o None si nunca se notificó."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT sale_price FROM notified_discounts WHERE url = ?",
            (url,),
        ).fetchone()
    return row[0] if row else None


def mark_notified(url: str, product_name: str, discount_pct: float, sale_price: int, channel_key: str = ""):
    with _db_lock:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO notified_discounts (url, product_name, discount_pct, sale_price, notified_at, channel_key)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET
                       sale_price=excluded.sale_price,
                       discount_pct=excluded.discount_pct,
                       notified_at=excluded.notified_at,
                       channel_key=excluded.channel_key""",
                (url, product_name, discount_pct, sale_price, datetime.now().isoformat(), channel_key),
            )
            conn.commit()


def clear_old_notifications(days: int = 7, url_pattern: str | None = None):
    """Limpia alertas antiguas para que productos puedan volver a notificarse."""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with _db_lock:
        with _connect() as conn:
            if url_pattern:
                conn.execute(
                    "DELETE FROM notified_discounts WHERE notified_at < ? AND url LIKE ?",
                    (cutoff, url_pattern),
                )
            else:
                conn.execute("DELETE FROM notified_discounts WHERE notified_at < ?", (cutoff,))
            conn.commit()


def get_last_price(url: str) -> int | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT price FROM price_history WHERE url = ? ORDER BY checked_at DESC LIMIT 1",
            (url,),
        ).fetchone()
    return row[0] if row else None


def save_price(product_name: str, url: str, price: int):
    with _db_lock:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO price_history (product_name, url, price, checked_at) VALUES (?, ?, ?, ?)",
                (product_name, url, price, datetime.now().isoformat()),
            )
            conn.commit()


def get_min_price(url: str) -> int | None:
    """Retorna el precio mínimo histórico registrado para este producto, o None si es la primera vez."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT MIN(price) FROM price_history WHERE url = ?",
            (url,),
        ).fetchone()
    return row[0] if row and row[0] is not None else None


def get_min_price_with_date(url: str) -> tuple[int, str] | None:
    """Retorna (precio_minimo, fecha) o None si no hay historial."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT price, checked_at FROM price_history WHERE url = ? ORDER BY price ASC, checked_at ASC LIMIT 1",
            (url,),
        ).fetchone()
    return (row[0], row[1]) if row else None


def get_last_prices(url: str, limit: int = 2) -> list[tuple[int, str]]:
    """Retorna los últimos N precios registrados (precio, fecha), del más reciente al más antiguo."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT price, checked_at FROM price_history WHERE url = ? ORDER BY checked_at DESC LIMIT ?",
            (url, limit),
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def get_price_history(url: str, limit: int = 10) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT price, checked_at FROM price_history WHERE url = ? ORDER BY checked_at DESC LIMIT ?",
            (url, limit),
        ).fetchall()
    return [{"price": r[0], "checked_at": r[1]} for r in rows]
