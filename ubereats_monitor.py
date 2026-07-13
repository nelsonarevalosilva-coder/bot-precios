"""
Monitor de promociones en Uber Eats Chile.
Usa Playwright (headless=False) para sesión + curl_cffi para llamadas periódicas.

Uso:
    python ubereats_monitor.py           # Monitoreo continuo (cada 2h)
    python ubereats_monitor.py --once    # Escanear ahora y salir
    python ubereats_monitor.py --debug   # Modo verbose
    python ubereats_monitor.py --reset   # Borrar estado
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import schedule
from dotenv import load_dotenv

from notifier import notify_delivery_promo
from ubereats_scraper import scrape_restaurants, UEPromo

load_dotenv()

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "ubereats_state.json"
LOG_FILE = BASE_DIR / "ubereats_monitor.log"

SCAN_INTERVAL_HOURS = float(os.getenv("UBEREATS_INTERVAL_HOURS", "2"))
MIN_DISCOUNT_PCT = int(os.getenv("UBEREATS_MIN_DISCOUNT", "20"))
MIN_DISCOUNT_CLP = int(os.getenv("UBEREATS_MIN_CLP", "2000"))
NOTIFY_FREE_DELIVERY = os.getenv("UBEREATS_FREE_DELIVERY", "true").lower() == "true"
NOTIFY_FREE_ITEM = os.getenv("UBEREATS_FREE_ITEM", "true").lower() == "true"


def setup_logging(debug: bool = False):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    level = logging.DEBUG if debug else logging.INFO
    handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)]
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S", handlers=handlers)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_scan(debug: bool = False):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    logging.info(f"{'='*50}")
    logging.info(f"Uber Eats scan {ts}")

    promos = scrape_restaurants(
        min_discount=MIN_DISCOUNT_PCT,
        min_clp=MIN_DISCOUNT_CLP,
        include_free_delivery=NOTIFY_FREE_DELIVERY,
        include_free_item=NOTIFY_FREE_ITEM,
        debug=debug,
    )

    if not promos:
        logging.warning("UberEats: 0 promos encontradas")
        return

    state = load_state()
    now = datetime.now().isoformat()
    new_count = 0
    updated_count = 0

    for p in promos:
        store_key = p.name
        prev = state.get(store_key)

        if prev is None:
            state[store_key] = {
                "promo_text": p.promo_text,
                "url": p.url,
                "first_seen": now,
                "last_seen": now,
            }
            logging.info(f"  NEW: {p.name} | {p.promo_text}")
            ok = notify_delivery_promo(
                name=p.name,
                promo_text=p.promo_text,
                url=p.url,
                eta=p.eta,
                delivery_cost=None,
                app="Uber Eats",
                is_new=True,
            )
            if ok:
                new_count += 1

        elif prev["promo_text"] != p.promo_text:
            prev_promo = prev["promo_text"]
            state[store_key].update({"promo_text": p.promo_text, "last_seen": now})
            logging.info(f"  CHANGED: {p.name} | {prev_promo!r} -> {p.promo_text!r}")
            ok = notify_delivery_promo(
                name=p.name,
                promo_text=p.promo_text,
                url=p.url,
                eta=p.eta,
                delivery_cost=None,
                app="Uber Eats",
                is_new=False,
                prev_promo=prev_promo,
            )
            if ok:
                updated_count += 1

        else:
            state[store_key]["last_seen"] = now
            logging.debug(f"  OK: {p.name} | {p.promo_text}")

    active_names = {p.name for p in promos}
    removed = [k for k in list(state.keys()) if k not in active_names]
    for k in removed:
        logging.info(f"  REMOVED: {k}")
        del state[k]

    save_state(state)
    logging.info(f"Uber Eats scan done — {len(promos)} promos | {new_count} nuevas | {updated_count} actualizadas | {len(removed)} removidas")


def main():
    parser = argparse.ArgumentParser(description="Monitor de promos Uber Eats Chile")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    setup_logging(args.debug)

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        logging.info("Estado borrado")

    if args.once:
        run_scan(debug=args.debug)
        sys.exit(0)

    logging.info(f"Uber Eats monitor iniciado — escaneo cada {SCAN_INTERVAL_HOURS}h")
    run_scan(debug=args.debug)

    schedule.every(SCAN_INTERVAL_HOURS).hours.do(run_scan, debug=args.debug)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
