"""
Verifica suscripciones vencidas y expulsa usuarios de los canales.
Corre como proceso separado, revisa cada hora.

Correr:
  python expiry_checker.py
"""
import logging
import os
import time

import requests
import schedule
from dotenv import load_dotenv

from sub_config import CHANNELS
from sub_db import get_expired_subscriptions, init_sub_db, mark_expired

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def send_telegram(chat_id, text):
    try:
        requests.post(f"{API}/sendMessage", json={
            "chat_id": chat_id, "text": text, "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        log.error(f"Telegram send error: {e}")


def remove_from_channel(channel_id, user_id):
    """Expulsa al usuario del canal y lo desbloquea para que pueda volver a suscribirse."""
    resp = requests.post(f"{API}/banChatMember", json={
        "chat_id": channel_id,
        "user_id": user_id,
    }, timeout=10)
    if not resp.json().get("ok"):
        log.error(f"Error expulsando user {user_id} de {channel_id}: {resp.text}")
        return False
    # Desbloquear inmediatamente para que pueda re-suscribirse después
    requests.post(f"{API}/unbanChatMember", json={
        "chat_id": channel_id,
        "user_id": user_id,
        "only_if_banned": True,
    }, timeout=10)
    return True


def check_expiries():
    expired = get_expired_subscriptions()
    if not expired:
        log.info("Sin suscripciones vencidas")
        return

    log.info(f"{len(expired)} suscripcion(es) vencida(s)")
    for sub in expired:
        try:
            if sub["telegram_id"] == OWNER_TELEGRAM_ID:
                mark_expired(sub["id"])
                log.info(f"Owner ({OWNER_TELEGRAM_ID}) — suscripción expirada ignorada, no se expulsa")
                continue

            removed = remove_from_channel(sub["channel_id"], sub["telegram_id"])
            mark_expired(sub["id"])

            if removed:
                ch_name = (
                    "⭐ Todos los canales" if sub["channel_key"] == "all"
                    else CHANNELS.get(sub["channel_key"], {}).get("name", sub["channel_key"])
                )
                send_telegram(sub["telegram_id"],
                    f"⏰ <b>Tu suscripción venció</b>\n\n"
                    f"Canal: <b>{ch_name}</b>\n\n"
                    f"Para renovar usa /suscribir"
                )
                log.info(f"Expirado: user {sub['telegram_id']} → {sub['channel_key']}")
        except Exception as e:
            log.error(f"Error procesando vencimiento {sub['id']}: {e}")


if __name__ == "__main__":
    init_sub_db()
    check_expiries()
    schedule.every(1).hours.do(check_expiries)
    log.info("Expiry checker activo — revisando cada hora")
    while True:
        schedule.run_pending()
        time.sleep(60)
