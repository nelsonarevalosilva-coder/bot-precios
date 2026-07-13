"""
Monitor de promociones en Rappi Chile.
Scraping vía __NEXT_DATA__ (SSR) — sin auth.

Uso:
    python rappi_monitor.py           # Monitoreo continuo (cada 2h)
    python rappi_monitor.py --once    # Escanear ahora y salir
    python rappi_monitor.py --debug   # Modo verbose
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
from rappi_scraper import scrape_restaurants, RappiPromo

load_dotenv()

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "rappi_state.json"
LOG_FILE = BASE_DIR / "rappi_monitor.log"

SCAN_INTERVAL_HOURS = float(os.getenv("RAPPI_INTERVAL_HOURS", "2"))
MIN_DISCOUNT_PCT = int(os.getenv("RAPPI_MIN_DISCOUNT", "20"))
NOTIFY_FREE_DELIVERY = os.getenv("RAPPI_FREE_DELIVERY", "true").lower() == "true"


def setup_logging(debug: bool = False):
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    level = logging.DEBUG if debug else logging.INFO
    handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)]
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S", handlers=handlers)


def load_state() -> dict:
    """State: {store_id: {promo_text, first_seen, last_seen}}"""
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


def _promo_key(p: RappiPromo) -> str:
    """Unique key for a restaurant's current promo state."""
    return f"{p.name}::{p.promo_text}"


def run_scan(debug: bool = False):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    logging.info(f"{'='*50}")
    logging.info(f"Rappi scan {ts}")

    promos = scrape_restaurants(
        min_discount=MIN_DISCOUNT_PCT,
        include_free_delivery=NOTIFY_FREE_DELIVERY,
        debug=debug,
    )

    if not promos:
        logging.warning("Rappi: 0 promos encontradas — puede ser error de scraping")
        return

    state = load_state()
    now = datetime.now().isoformat()
    new_count = 0
    updated_count = 0

    for p in promos:
        store_key = str(p.name)  # use name as key (IDs sometimes missing from URL)
        prev = state.get(store_key)

        if prev is None:
            # Primera vez que vemos esta promo
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
                delivery_cost=p.delivery_cost,
                app="Rappi",
                is_new=True,
            )
            if ok:
                new_count += 1

        elif prev["promo_text"] != p.promo_text:
            # Promo cambió (ej: 30% → 40%)
            prev_promo = prev["promo_text"]
            state[store_key].update({"promo_text": p.promo_text, "last_seen": now})
            logging.info(f"  CHANGED: {p.name} | {prev_promo!r} → {p.promo_text!r}")
            ok = notify_delivery_promo(
                name=p.name,
                promo_text=p.promo_text,
                url=p.url,
                eta=p.eta,
                delivery_cost=p.delivery_cost,
                app="Rappi",
                is_new=False,
                prev_promo=prev_promo,
            )
            if ok:
                updated_count += 1

        else:
            # Promo sin cambios — solo actualizar last_seen
            state[store_key]["last_seen"] = now
            logging.debug(f"  OK (sin cambio): {p.name} | {p.promo_text}")

    # Eliminar restaurantes que ya no tienen promo activa (no aparecen en esta scan)
    active_names = {p.name for p in promos}
    removed = [k for k in list(state.keys()) if k not in active_names]
    for k in removed:
        logging.info(f"  REMOVED (ya sin promo): {k}")
        del state[k]

    save_state(state)

    logging.info(f"Rappi scan done — {len(promos)} promos | {new_count} nuevas | {updated_count} actualizadas | {len(removed)} removidas")


def main():
    parser = argparse.ArgumentParser(description="Monitor de promos Rappi Chile")
    parser.add_argument("--once", action="store_true", help="Escanear una vez y salir")
    parser.add_argument("--debug", action="store_true", help="Modo verbose")
    parser.add_argument("--reset", action="store_true", help="Borrar estado (notificará todo como nuevo)")
    args = parser.parse_args()

    setup_logging(args.debug)

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        logging.info("Estado borrado — próxima scan notificará todo")

    if args.once:
        run_scan(debug=args.debug)
        sys.exit(0)

    logging.info(f"Rappi monitor iniciado — escaneo cada {SCAN_INTERVAL_HOURS}h")
    run_scan(debug=args.debug)

    schedule.every(SCAN_INTERVAL_HOURS).hours.do(run_scan, debug=args.debug)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
