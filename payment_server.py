"""
Servidor Flask — recibe webhooks de MercadoPago y activa suscripciones.

Requisitos:
  - Debe ser accesible públicamente (IP pública o ngrok)
  - Puerto: 8080 (ajustable con variable PORT en .env)
  - Configurar WEBHOOK_BASE_URL en .env con la URL pública

Correr:
  python payment_server.py
"""
import logging
import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from sub_config import CHANNELS, PLANS
from sub_db import add_subscription, init_sub_db

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
PORT = int(os.getenv("PORT", "8080"))

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def send_telegram(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(f"{API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        log.error(f"Telegram send error: {e}")


def create_invite_link(channel_id):
    """Genera un link de invitación de un solo uso, válido 24 horas."""
    expire_date = int((datetime.now() + timedelta(hours=24)).timestamp())
    resp = requests.post(f"{API}/createChatInviteLink", json={
        "chat_id": channel_id,
        "member_limit": 1,
        "expire_date": expire_date,
    }, timeout=10)
    data = resp.json()
    if data.get("ok"):
        return data["result"]["invite_link"]
    log.error(f"Error creando invite link para {channel_id}: {data}")
    return None


@app.route("/webhook/mercadopago", methods=["POST"])
def mp_webhook():
    data = request.json or {}
    topic = data.get("type") or request.args.get("topic", "")

    # Solo procesar pagos
    if topic != "payment":
        return jsonify({"ok": True})

    payment_id = (data.get("data", {}).get("id") or request.args.get("id"))
    if not payment_id:
        return jsonify({"ok": True})

    log.info(f"Webhook recibido: payment_id={payment_id}")

    # Consultar detalles del pago en MercadoPago
    resp = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
        timeout=15,
    )
    if resp.status_code != 200:
        log.error(f"Error consultando pago {payment_id}: {resp.text}")
        return jsonify({"ok": True})

    payment = resp.json()
    status = payment.get("status")
    log.info(f"Payment {payment_id} status: {status}")

    if status != "approved":
        return jsonify({"ok": True})

    # Parsear external_reference: "telegram_id|username|channel_key|plan_key"
    external_ref = payment.get("external_reference", "")
    parts = external_ref.split("|")
    if len(parts) != 4:
        log.error(f"external_reference inválido: {external_ref}")
        return jsonify({"ok": True})

    telegram_id = int(parts[0])
    telegram_user = parts[1]
    channel_key = parts[2]
    plan_key = parts[3]
    amount = int(payment.get("transaction_amount", 0))

    plan = PLANS.get(plan_key)
    if not plan:
        log.error(f"Plan desconocido: {plan_key}")
        return jsonify({"ok": True})

    # Determinar qué canales activar
    channels_to_activate = list(CHANNELS.items()) if channel_key == "all" else [
        (channel_key, CHANNELS[channel_key])
    ] if channel_key in CHANNELS else []

    if not channels_to_activate:
        log.error(f"Canal desconocido: {channel_key}")
        return jsonify({"ok": True})

    # Generar links de invitación y registrar en BD
    invite_links = []
    for key, ch in channels_to_activate:
        link = create_invite_link(ch["id"])
        if link:
            add_subscription(
                telegram_id=telegram_id,
                telegram_user=telegram_user,
                channel_key=key,
                channel_id=ch["id"],
                plan=plan_key,
                amount=amount,
                mp_payment_id=str(payment_id),
                invite_link=link,
                days=plan["days"],
            )
            invite_links.append((ch["name"], link))

    if not invite_links:
        send_telegram(telegram_id,
            "❌ Hubo un problema al generar tu acceso.\n"
            "Por favor escríbenos para resolverlo."
        )
        return jsonify({"ok": True})

    SEARCH_BOT = "https://t.me/Ofertas_search_bot"

    # Enviar mensaje de bienvenida con los links
    if channel_key == "all":
        msg = (
            f"🎉 <b>¡Pago confirmado!</b>\n\n"
            f"Acceso a <b>todos los canales</b> por <b>{plan['label']}</b>.\n\n"
            f"<b>Úsalos una sola vez:</b>\n\n"
        )
        for name, link in invite_links:
            msg += f"• {name}: {link}\n"
        msg += (
            f"\n⏰ Los links expiran en 24 horas si no los usas.\n\n"
            f"🔍 <b>Buscador exclusivo:</b> {SEARCH_BOT}\n"
            f"Escribe cualquier producto y te mostramos las mejores ofertas."
        )
    else:
        ch_name, link = invite_links[0]
        msg = (
            f"🎉 <b>¡Pago confirmado!</b>\n\n"
            f"Canal: <b>{ch_name}</b>\n"
            f"Plan: <b>{plan['label']}</b>\n\n"
            f"👇 Link de acceso (uso único):\n{link}\n\n"
            f"⏰ El link expira en 24 horas si no lo usas.\n\n"
            f"🔍 <b>Buscador exclusivo:</b> {SEARCH_BOT}\n"
            f"Escribe cualquier producto y te mostramos las mejores ofertas."
        )

    send_telegram(telegram_id, msg)
    log.info(f"Suscripcion activada: user {telegram_id} → {channel_key}/{plan_key}")
    return jsonify({"ok": True})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "cazador-precios-webhooks"})


if __name__ == "__main__":
    init_sub_db()
    log.info(f"Payment server iniciado en puerto {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
