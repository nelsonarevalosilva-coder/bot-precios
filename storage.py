import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "prices.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
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
                notified_at TEXT NOT NULL
            )
        """)
        conn.commit()


def has_been_notified(url: str, sale_price: int) -> bool:
    """Retorna True si ya enviamos alerta para este producto a este precio."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT sale_price FROM notified_discounts WHERE url = ?",
            (url,),
        ).fetchone()
    # Notificar de nuevo si el precio bajó más desde la última alerta
    if row is None:
        return False
    return row[0] <= sale_price


def mark_notified(url: str, product_name: str, discount_pct: float, sale_price: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT INTO notified_discounts (url, product_name, discount_pct, sale_price, notified_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET
                   sale_price=excluded.sale_price,
                   discount_pct=excluded.discount_pct,
                   notified_at=excluded.notified_at""",
            (url, product_name, discount_pct, sale_price, datetime.now().isoformat()),
        )
        conn.commit()


def clear_old_notifications(days: int = 7):
    """Limpia alertas antiguas para que productos puedan volver a notificarse."""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM notified_discounts WHERE notified_at < ?", (cutoff,))
        conn.commit()


def get_last_price(url: str) -> int | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT price FROM price_history WHERE url = ? ORDER BY checked_at DESC LIMIT 1",
            (url,),
        ).fetchone()
    return row[0] if row else None


def save_price(product_name: str, url: str, price: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO price_history (product_name, url, price, checked_at) VALUES (?, ?, ?, ?)",
            (product_name, url, price, datetime.now().isoformat()),
        )
        conn.commit()


def get_price_history(url: str, limit: int = 10) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT price, checked_at FROM price_history WHERE url = ? ORDER BY checked_at DESC LIMIT ?",
            (url, limit),
        ).fetchall()
    return [{"price": r[0], "checked_at": r[1]} for r in rows]
