"""
Monitor de las 9 tiendas nuevas — loop cada 30 min.
Corre en PC de desarrollo mientras el servidor maneja las 43 tiendas originales.
"""
import concurrent.futures
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import adidas_scraper
import bata_scraper
import newbalance_scraper
import converse_scraper
import skechers_scraper
import decathlon_scraper
import underarmour_scraper
import zara_scraper
import xiaomi_scraper
import corona_scraper
import mercadolibre_scraper
from catalog_monitor import scan_store, PRICE_ERROR_THRESHOLD
from notifier import notify_catalog_summary
from storage import clear_old_notifications, init_db

load_dotenv()

BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "monitor_nuevas.log"
INTERVAL_MIN = 30


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


STORES = [
    (load_json(BASE_DIR / "adidas_categories.json"),       adidas_scraper,       "Adidas",        25.0),
    (load_json(BASE_DIR / "bata_categories.json"),         bata_scraper,         "Bata",          40.0),
    (load_json(BASE_DIR / "newbalance_categories.json"),   newbalance_scraper,   "New Balance",   40.0),
    (load_json(BASE_DIR / "converse_categories.json"),     converse_scraper,     "Converse",      40.0),
    (load_json(BASE_DIR / "skechers_categories.json"),     skechers_scraper,     "Skechers",      40.0),
    (load_json(BASE_DIR / "decathlon_categories.json"),    decathlon_scraper,    "Decathlon",     40.0),
    (load_json(BASE_DIR / "underarmour_categories.json"),  underarmour_scraper,  "Under Armour",  40.0),
    (load_json(BASE_DIR / "zara_categories.json"),         zara_scraper,         "Zara",          40.0),
    (load_json(BASE_DIR / "xiaomi_categories.json"),       xiaomi_scraper,       "Xiaomi",        40.0),
    (load_json(BASE_DIR / "corona_categories.json"),       corona_scraper,       "Corona",        40.0),
    (load_json(BASE_DIR / "mercadolibre_categories.json"), mercadolibre_scraper, "Mercado Libre", 40.0),
]


def run_scan(debug=False):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    logging.info("=" * 60)
    logging.info("Escaneo nuevas tiendas — %s", ts)
    logging.info("=" * 60)

    total_alerts = total_errors = total_cats = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(STORES)) as executor:
        futures = {
            executor.submit(scan_store, cats, module, name, discount, debug): name
            for cats, module, name, discount in STORES
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                a, e, n = future.result()
                total_alerts += a
                total_errors += e
                total_cats += n
                logging.info("[%s] TERMINADO — ofertas: %d | errores: %d | cats: %d", name, a, e, n)
            except Exception as exc:
                logging.error("[%s] Fallo: %s", name, exc)

    logging.info("Escaneo completado — Ofertas: %d | Errores precio: %d", total_alerts, total_errors)
    notify_catalog_summary(total_alerts, total_cats, total_errors)
    clear_old_notifications(days=7)


def main():
    debug = "--debug" in sys.argv

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    init_db()
    logging.info("Monitor nuevas tiendas iniciado — intervalo: %d min", INTERVAL_MIN)

    while True:
        run_scan(debug=debug)
        logging.info("Próximo escaneo en %d minutos...", INTERVAL_MIN)
        time.sleep(INTERVAL_MIN * 60)


if __name__ == "__main__":
    main()
