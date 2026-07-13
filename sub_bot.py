"""
Bot de suscripciones — Cazador de Precios Chile.
Corre en paralelo con catalog_monitor.py (proceso separado).

Comandos:
  /start      — bienvenida
  /suscribir  — elegir canal y pagar
  /estado     — ver suscripciones activas
  /ayuda      — ayuda
"""
import logging
import os
import time

import requests
from dotenv import load_dotenv

from sub_config import CHANNELS, PLANS
from sub_db import get_active_subscriptions, has_active_subscription, init_sub_db, add_subscription

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")
OWNER_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def tg(method, **kwargs):
    resp = requests.post(f"{API}/{method}", json=kwargs, timeout=10)
    return resp.json()


def send(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("sendMessage", **payload)


def edit(chat_id, msg_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("editMessageText", **payload)


def answer_cb(cb_id, text=""):
    tg("answerCallbackQuery", callback_query_id=cb_id, text=text)


def channel_list_keyboard():
    buttons = []
    row = []
    for key, ch in CHANNELS.items():
        row.append({"text": ch["name"], "callback_data": f"ch_{key}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([{"text": "⭐ TODOS LOS CANALES", "callback_data": "ch_all"}])
    return {"inline_keyboard": buttons}


def plan_keyboard(channel_key):
    buttons = []
    for plan_key, plan in PLANS.items():
        price = plan["price_all"] if channel_key == "all" else plan["price_single"]
        label = f"📅 {plan['label']} — ${price:,} CLP"
        buttons.append([{"text": label, "callback_data": f"pl_{channel_key}_{plan_key}"}])
    buttons.append([{"text": "◀️ Volver", "callback_data": "back_channels"}])
    return {"inline_keyboard": buttons}


def channels_text():
    plan = PLANS["mensual"]
    return (
        f"🛒 <b>Elige el canal al que quieres acceder</b>\n\n"
        f"💰 Desde <b>${plan['price_single']:,} CLP/mes</b> por canal\n"
        f"⭐ Todos los canales: <b>${plan['price_all']:,} CLP/mes</b>"
    )


def create_mp_link(user_id, username, channel_key, plan_key):
    if not MP_ACCESS_TOKEN:
        return None, "Pagos no configurados aún. Contacta al administrador."
    if not WEBHOOK_BASE_URL:
        return None, "Servidor de pagos no configurado."

    plan = PLANS[plan_key]
    if channel_key == "all":
        title = f"Cazador de Precios — Todos los canales — {plan['label']}"
        price = plan["price_all"]
    else:
        ch = CHANNELS[channel_key]
        title = f"Cazador de Precios — {ch['name']} — {plan['label']}"
        price = plan["price_single"]

    external_ref = f"{user_id}|{username or 'unknown'}|{channel_key}|{plan_key}"

    body = {
        "items": [{"title": title, "quantity": 1, "unit_price": price, "currency_id": "CLP"}],
        "payer": {"name": username or str(user_id)},
        "external_reference": external_ref,
        "notification_url": f"{WEBHOOK_BASE_URL}/webhook/mercadopago",
        "back_urls": {
            "success": "https://t.me/Cazador_precios_cl_chile_bot",
            "failure": "https://t.me/Cazador_precios_cl_chile_bot",
            "pending": "https://t.me/Cazador_precios_cl_chile_bot",
        },
        "auto_return": "approved",
        "statement_descriptor": "CAZADOR PRECIOS CL",
    }

    resp = requests.post(
        "https://api.mercadopago.com/checkout/preferences",
        headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}", "Content-Type": "application/json"},
        json=body,
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        log.error(f"MP error: {resp.text[:300]}")
        return None, "Error al conectar con MercadoPago. Intenta más tarde."

    url = resp.json().get("init_point")
    return url, None


def create_invite_link(channel_id):
    from datetime import datetime, timedelta
    expire_date = int((datetime.now() + timedelta(hours=24)).timestamp())
    resp = tg("createChatInviteLink", chat_id=channel_id, member_limit=1, expire_date=expire_date)
    if resp.get("ok"):
        return resp["result"]["invite_link"]
    return None


def handle_regalar(chat_id, owner_id, args_text):
    """Comando /regalar <telegram_id> <canal_o_all> <dias>"""
    if owner_id != OWNER_ID:
        send(chat_id, "⛔ No tienes permiso para usar este comando.")
        return

    parts = args_text.strip().split()
    if len(parts) != 3:
        send(chat_id,
            "⚠️ <b>Faltan argumentos.</b>\n\n"
            "📋 <b>Uso correcto:</b>\n"
            "<code>/regalar &lt;telegram_id&gt; &lt;canal&gt; &lt;días&gt;</code>\n\n"
            "<b>Ejemplo:</b>\n"
            "<code>/regalar 5700067936 all 30</code>\n\n"
            "<b>Canales disponibles:</b>\n" +
            "\n".join(f"• <code>{k}</code>" for k in list(CHANNELS.keys()) + ["all"])
        )
        return

    try:
        target_id = int(parts[0])
    except ValueError:
        send(chat_id, "❌ El telegram_id debe ser un número.")
        return

    channel_key = parts[1].lower()
    try:
        days = int(parts[2])
    except ValueError:
        send(chat_id, "❌ Los días deben ser un número.")
        return

    if channel_key != "all" and channel_key not in CHANNELS:
        send(chat_id, f"❌ Canal '{channel_key}' no existe.\nUsa: {', '.join(CHANNELS.keys())} o all")
        return

    channels_to_activate = list(CHANNELS.items()) if channel_key == "all" else [(channel_key, CHANNELS[channel_key])]

    invite_links = []
    for key, ch in channels_to_activate:
        link = create_invite_link(ch["id"])
        if link:
            add_subscription(
                telegram_id=target_id,
                telegram_user="regalo",
                channel_key=key,
                channel_id=ch["id"],
                plan="regalo",
                amount=0,
                mp_payment_id="regalo",
                invite_link=link,
                days=days,
            )
            invite_links.append((ch["name"], link))

    if not invite_links:
        send(chat_id, "❌ No se pudieron generar los links de invitación. ¿El bot es admin en los canales?")
        return

    SEARCH_BOT = "https://t.me/Ofertas_search_bot"
    if channel_key == "all":
        msg = f"🎁 <b>¡Tienes acceso gratuito!</b>\n\n<b>Todos los canales — {days} días</b>\n\n"
        for name, link in invite_links:
            msg += f"• {name}: {link}\n"
        msg += f"\n🔍 Buscador: {SEARCH_BOT}\n⏰ Links válidos por 24h."
    else:
        ch_name, link = invite_links[0]
        msg = (
            f"🎁 <b>¡Tienes acceso gratuito!</b>\n\n"
            f"Canal: <b>{ch_name}</b> — {days} días\n\n"
            f"👇 Link de acceso:\n{link}\n\n"
            f"🔍 Buscador: {SEARCH_BOT}\n⏰ Link válido por 24h."
        )

    send(target_id, msg)
    send(chat_id, f"✅ Membresía de {days} días enviada al usuario {target_id}.")
    log.info(f"Regalo: owner → user {target_id} | {channel_key} | {days} días")


def handle_message(msg):
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")
    user = msg.get("from", {})
    user_id = user.get("id")

    if text.startswith("/regalar"):
        args = text[len("/regalar"):].strip()
        handle_regalar(chat_id, user_id, args)

    if text.startswith("/start") or text.startswith("/ayuda"):
        send(chat_id,
            "👋 <b>Cazador de Precios Chile</b>\n\n"
            "Recibe alertas de ofertas en tiempo real, organizadas por categoría.\n\n"
            "<b>Comandos:</b>\n"
            "/suscribir — ver canales y precios\n"
            "/estado — ver mis suscripciones activas\n"
            "/ayuda — esta ayuda"
        )

    elif text.startswith("/suscribir"):
        send(chat_id, channels_text(), reply_markup=channel_list_keyboard())

    elif text.startswith("/estado"):
        subs = get_active_subscriptions(user_id)
        if not subs:
            send(chat_id,
                "❌ No tienes suscripciones activas.\n\n"
                "Usa /suscribir para activar tu acceso."
            )
        else:
            lines = ["📋 <b>Tus suscripciones activas:</b>\n"]
            for s in subs:
                exp = s["expires_at"][:10]
                ch_name = (
                    "⭐ Todos los canales" if s["channel_key"] == "all"
                    else CHANNELS.get(s["channel_key"], {}).get("name", s["channel_key"])
                )
                lines.append(f"• {ch_name} — vence el <b>{exp}</b>")
            send(chat_id, "\n".join(lines))


def handle_callback(cb):
    cb_id = cb["id"]
    data = cb.get("data", "")
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    user = cb.get("from", {})
    user_id = user.get("id")
    username = user.get("username", "")

    answer_cb(cb_id)

    if data in ("back_channels", "cancel"):
        edit(chat_id, msg_id, channels_text(), reply_markup=channel_list_keyboard())

    elif data.startswith("ch_"):
        channel_key = data[3:]
        ch_name = "⭐ Todos los canales" if channel_key == "all" else CHANNELS.get(channel_key, {}).get("name", channel_key)
        edit(chat_id, msg_id,
            f"📅 <b>Elige el plan para {ch_name}:</b>",
            reply_markup=plan_keyboard(channel_key)
        )

    elif data.startswith("pl_"):
        # Extraer channel_key y plan_key del callback_data
        # Formato: pl_{channel_key}_{plan_key}
        # plan_key solo puede ser "mensual" (7 chars) o "trimestral" (10 chars)
        if data.endswith("_mensual"):
            plan_key = "mensual"
            channel_key = data[3:-8]      # quita "pl_" y "_mensual"
        elif data.endswith("_trimestral"):
            plan_key = "trimestral"
            channel_key = data[3:-11]     # quita "pl_" y "_trimestral"
        else:
            return

        ch_name = "⭐ Todos los canales" if channel_key == "all" else CHANNELS.get(channel_key, {}).get("name", channel_key)
        plan = PLANS[plan_key]
        price = plan["price_all"] if channel_key == "all" else plan["price_single"]

        # Ya tiene suscripción activa?
        if channel_key != "all" and has_active_subscription(user_id, channel_key):
            edit(chat_id, msg_id,
                f"✅ Ya tienes suscripción activa en {ch_name}.\n"
                f"Usa /estado para ver los detalles."
            )
            return

        edit(chat_id, msg_id,
            f"💳 <b>Generando link de pago...</b>\n\n"
            f"• Canal: <b>{ch_name}</b>\n"
            f"• Plan: <b>{plan['label']}</b>\n"
            f"• Precio: <b>${price:,} CLP</b>"
        )

        payment_url, error = create_mp_link(user_id, username, channel_key, plan_key)

        if error or not payment_url:
            edit(chat_id, msg_id,
                f"❌ {error or 'Error al generar el pago. Intenta más tarde.'}"
            )
            return

        edit(chat_id, msg_id,
            f"✅ <b>Link de pago listo</b>\n\n"
            f"• Canal: <b>{ch_name}</b>\n"
            f"• Plan: <b>{plan['label']}</b>\n"
            f"• Precio: <b>${price:,} CLP</b>\n\n"
            f"👇 Haz clic para pagar con MercadoPago:",
            reply_markup={"inline_keyboard": [[
                {"text": f"💳 Pagar ${price:,} CLP", "url": payment_url}
            ]]}
        )
        log.info(f"Payment link → user {user_id} ({username}) | {channel_key}/{plan_key}")


def poll():
    last_id = 0
    log.info("Sub bot iniciado, esperando mensajes...")
    while True:
        try:
            resp = requests.get(f"{API}/getUpdates", params={
                "timeout": 30,
                "offset": last_id + 1,
                "allowed_updates": ["message", "callback_query"],
            }, timeout=35)
            for update in resp.json().get("result", []):
                last_id = update["update_id"]
                try:
                    if "message" in update:
                        handle_message(update["message"])
                    elif "callback_query" in update:
                        handle_callback(update["callback_query"])
                except Exception as e:
                    log.error(f"Error procesando update: {e}")
        except Exception as e:
            log.error(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    init_sub_db()
    poll()
