import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "subscriptions.db"


def init_sub_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id    INTEGER NOT NULL,
                telegram_user  TEXT,
                channel_key    TEXT NOT NULL,
                channel_id     INTEGER NOT NULL,
                plan           TEXT NOT NULL,
                amount         INTEGER NOT NULL,
                expires_at     TEXT NOT NULL,
                mp_payment_id  TEXT,
                invite_link    TEXT,
                status         TEXT DEFAULT 'active',
                created_at     TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def add_subscription(telegram_id, telegram_user, channel_key, channel_id,
                     plan, amount, mp_payment_id, invite_link, days):
    expires_at = (datetime.now() + timedelta(days=days)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO subscriptions
              (telegram_id, telegram_user, channel_key, channel_id,
               plan, amount, expires_at, mp_payment_id, invite_link, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (telegram_id, telegram_user, channel_key, channel_id,
              plan, amount, expires_at, mp_payment_id, invite_link))
        conn.commit()


def get_active_subscriptions(telegram_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("""
            SELECT * FROM subscriptions
            WHERE telegram_id = ? AND status = 'active' AND expires_at > datetime('now')
            ORDER BY expires_at DESC
        """, (telegram_id,)).fetchall()


def get_expired_subscriptions():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("""
            SELECT * FROM subscriptions
            WHERE status = 'active' AND expires_at <= datetime('now')
        """).fetchall()


def mark_expired(sub_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE subscriptions SET status = 'expired' WHERE id = ?", (sub_id,))
        conn.commit()


def has_active_subscription(telegram_id, channel_key):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("""
            SELECT id FROM subscriptions
            WHERE telegram_id = ? AND channel_key = ?
              AND status = 'active' AND expires_at > datetime('now')
        """, (telegram_id, channel_key)).fetchone()
        return row is not None
