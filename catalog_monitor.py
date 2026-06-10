"""
Monitor de catálogo — Ripley Chile + Falabella Chile.
- Descuento >= 70%: alerta POSIBLE ERROR DE PRECIO
- Precio < $1.000 con normal > $5.000: alerta ERROR EXTREMO

Uso:
    python catalog_monitor.py                 # Monitoreo continuo
    python catalog_monitor.py --once          # Escanear ahora una vez
    python catalog_monitor.py --once --debug  # Con detalle del scraping
    python catalog_monitor.py --store ripley  # Solo Ripley
    python catalog_monitor.py --store falabella  # Solo Falabella
"""

import argparse
import concurrent.futures
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import schedule
from dotenv import load_dotenv

import abc_scraper
import bold_scraper
import catalog_scraper
import columbia_scraper
import doite_scraper
import easy_scraper
import falabella_scraper
import hushpuppies_scraper
import jumbo_scraper
import multimarcas_scraper
import paris_scraper
import reebok_scraper
import pcfactory_scraper
import sodimac_scraper
import wildlama_scraper
import mundovino_scraper
import liquidos_scraper
import booz_scraper
from notifier import notify_big_discount, notify_catalog_summary, notify_price_error
from storage import clear_old_notifications, get_min_price_with_date, get_last_prices, has_been_notified, init_db, mark_notified, save_price

load_dotenv()

BASE_DIR = Path(__file__).parent
CATEGORIES_FILE = BASE_DIR / "categories.json"
FALABELLA_CATEGORIES_FILE = BASE_DIR / "falabella_categories.json"
PARIS_CATEGORIES_FILE = BASE_DIR / "paris_categories.json"
EASY_CATEGORIES_FILE = BASE_DIR / "easy_categories.json"
SODIMAC_CATEGORIES_FILE = BASE_DIR / "sodimac_categories.json"
JUMBO_CATEGORIES_FILE = BASE_DIR / "jumbo_categories.json"
ABC_CATEGORIES_FILE = BASE_DIR / "abc_categories.json"
COLUMBIA_CATEGORIES_FILE = BASE_DIR / "columbia_categories.json"
DOITE_CATEGORIES_FILE = BASE_DIR / "doite_categories.json"
HUSHPUPPIES_CATEGORIES_FILE = BASE_DIR / "hushpuppies_categories.json"
PCFACTORY_CATEGORIES_FILE = BASE_DIR / "pcfactory_categories.json"
MULTIMARCAS_CATEGORIES_FILE = BASE_DIR / "multimarcas_categories.json"
REEBOK_CATEGORIES_FILE = BASE_DIR / "reebok_categories.json"
BOLD_CATEGORIES_FILE = BASE_DIR / "bold_categories.json"
WILDLAMA_CATEGORIES_FILE = BASE_DIR / "wildlama_categories.json"
MUNDOVINO_CATEGORIES_FILE = BASE_DIR / "mundovino_categories.json"
LIQUIDOS_CATEGORIES_FILE = BASE_DIR / "liquidos_categories.json"
BOOZ_CATEGORIES_FILE = BASE_DIR / "booz_categories.json"
LOG_FILE = BASE_DIR / "monitor.log"
CATALOG_INTERVAL_HOURS = float(os.getenv("CATALOG_INTERVAL_HOURS", "0.5"))
MIN_DISCOUNT = float(os.getenv("MIN_DISCOUNT_PCT", "70"))
PRICE_ERROR_THRESHOLD = float(os.getenv("PRICE_ERROR_THRESHOLD_PCT", "80"))
LICORES_MIN_DISCOUNT = 30.0  # umbral especial para tiendas de licores
LICORES_STORES = {"El Mundo del Vino", "Liquidos", "Booz"}


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if sys.stdout:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def load_json(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def scan_store(categories: list[dict], scraper_module, store_name: str, min_discount: float, debug: bool) -> tuple[int, int, int]:
    """Escanea todas las categorías de una tienda. Retorna (alertas, errores, total_cats)."""
    total_alerts = 0
    total_errors = 0

    for cat in categories:
        logging.info(f">> [{store_name}] {cat['name']}")
        try:
            products = scraper_module.scrape_category(
                url=cat["url"],
                category_name=cat["name"],
                min_discount=min_discount,
                max_pages=3,
                debug=debug,
            )

            if not products:
                logging.info(f"  Sin ofertas >= {min_discount:.0f}%")
                continue

            logging.info(f"  {len(products)} oferta(s) encontrada(s)")
            for p in products:
                tag = "ERROR PRECIO" if p.discount_pct >= PRICE_ERROR_THRESHOLD else "OFERTA"
                logging.info(f"    [{tag}] {p.name[:55]} | {p.discount_pct:.0f}% | ${p.sale_price:,}")

                # Registrar precio en historial ANTES de notificar
                min_data = get_min_price_with_date(p.url)
                last_prices = get_last_prices(p.url, limit=2)
                save_price(p.name, p.url, p.sale_price)

                if has_been_notified(p.url, p.sale_price):
                    logging.info(f"      (ya notificado)")
                    continue

                if p.discount_pct >= PRICE_ERROR_THRESHOLD:
                    ok = notify_price_error(p, min_data, last_prices)
                    if ok:
                        total_errors += 1
                else:
                    ok = notify_big_discount(p, min_data, last_prices)
                    if ok:
                        total_alerts += 1

                if ok:
                    mark_notified(p.url, p.name, p.discount_pct, p.sale_price)

            time.sleep(3)

        except Exception as e:
            logging.error(f"  Error al escanear {cat['name']}: {e}")
            continue

    return total_alerts, total_errors, len(categories)


def run_catalog_scan(
    min_discount: float = MIN_DISCOUNT,
    only_store: str | None = None,
    debug: bool = False,
):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    logging.info(f"{'='*60}")
    logging.info(f"Escaneo iniciado {ts} | descuento >= {min_discount:.0f}% | PARALELO")
    logging.info(f"{'='*60}")

    def _store_discount(store_name: str) -> float:
        return LICORES_MIN_DISCOUNT if store_name in LICORES_STORES else min_discount

    stores_to_run: list[tuple] = []
    if only_store is None or only_store.lower() == "ripley":
        stores_to_run.append((load_json(CATEGORIES_FILE), catalog_scraper, "Ripley", _store_discount("Ripley")))
    if only_store is None or only_store.lower() == "falabella":
        stores_to_run.append((load_json(FALABELLA_CATEGORIES_FILE), falabella_scraper, "Falabella", _store_discount("Falabella")))
    if only_store is None or only_store.lower() == "paris":
        stores_to_run.append((load_json(PARIS_CATEGORIES_FILE), paris_scraper, "Paris", _store_discount("Paris")))
    if only_store is None or only_store.lower() == "easy":
        stores_to_run.append((load_json(EASY_CATEGORIES_FILE), easy_scraper, "Easy", _store_discount("Easy")))
    if only_store is None or only_store.lower() == "sodimac":
        stores_to_run.append((load_json(SODIMAC_CATEGORIES_FILE), sodimac_scraper, "Sodimac", _store_discount("Sodimac")))
    if only_store is None or only_store.lower() == "jumbo":
        stores_to_run.append((load_json(JUMBO_CATEGORIES_FILE), jumbo_scraper, "Jumbo", _store_discount("Jumbo")))
    if only_store is None or only_store.lower() == "abc":
        stores_to_run.append((load_json(ABC_CATEGORIES_FILE), abc_scraper, "abc", _store_discount("abc")))
    if only_store is None or only_store.lower() == "columbia":
        stores_to_run.append((load_json(COLUMBIA_CATEGORIES_FILE), columbia_scraper, "Columbia", _store_discount("Columbia")))
    if only_store is None or only_store.lower() == "doite":
        stores_to_run.append((load_json(DOITE_CATEGORIES_FILE), doite_scraper, "Doite", _store_discount("Doite")))
    if only_store is None or only_store.lower() == "hushpuppies":
        stores_to_run.append((load_json(HUSHPUPPIES_CATEGORIES_FILE), hushpuppies_scraper, "Hush Puppies", _store_discount("Hush Puppies")))
    if only_store is None or only_store.lower() == "pcfactory":
        stores_to_run.append((load_json(PCFACTORY_CATEGORIES_FILE), pcfactory_scraper, "PC Factory", _store_discount("PC Factory")))
    if only_store is None or only_store.lower() == "multimarcas":
        stores_to_run.append((load_json(MULTIMARCAS_CATEGORIES_FILE), multimarcas_scraper, "Multimarcas Perfumes", _store_discount("Multimarcas Perfumes")))
    if only_store is None or only_store.lower() == "reebok":
        stores_to_run.append((load_json(REEBOK_CATEGORIES_FILE), reebok_scraper, "Reebok", _store_discount("Reebok")))
    if only_store is None or only_store.lower() == "bold":
        stores_to_run.append((load_json(BOLD_CATEGORIES_FILE), bold_scraper, "Bold", _store_discount("Bold")))
    if only_store is None or only_store.lower() == "wildlama":
        stores_to_run.append((load_json(WILDLAMA_CATEGORIES_FILE), wildlama_scraper, "Wild Lama", _store_discount("Wild Lama")))
    if only_store is None or only_store.lower() == "mundovino":
        stores_to_run.append((load_json(MUNDOVINO_CATEGORIES_FILE), mundovino_scraper, "El Mundo del Vino", _store_discount("El Mundo del Vino")))
    if only_store is None or only_store.lower() == "liquidos":
        stores_to_run.append((load_json(LIQUIDOS_CATEGORIES_FILE), liquidos_scraper, "Liquidos", _store_discount("Liquidos")))
    if only_store is None or only_store.lower() == "booz":
        stores_to_run.append((load_json(BOOZ_CATEGORIES_FILE), booz_scraper, "Booz", _store_discount("Booz")))

    logging.info(f"Escaneando en paralelo: {', '.join(s[2] for s in stores_to_run)}")

    total_alerts = 0
    total_errors = 0
    total_cats = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(stores_to_run)) as executor:
        future_to_store = {
            executor.submit(scan_store, cats, module, name, store_discount, debug): name
            for cats, module, name, store_discount in stores_to_run
        }
        for future in concurrent.futures.as_completed(future_to_store):
            store_name = future_to_store[future]
            try:
                a, e, n = future.result()
                total_alerts += a
                total_errors += e
                total_cats += n
                logging.info(f"[{store_name}] TERMINADO — ofertas: {a} | errores precio: {e} | categorías: {n}")
            except Exception as exc:
                logging.error(f"[{store_name}] Fallo crítico: {exc}")

    logging.info(f"{'='*60}")
    logging.info(f"Escaneo completado — Ofertas: {total_alerts} | Errores precio: {total_errors}")
    logging.info(f"{'='*60}")

    clear_old_notifications(days=7)

    notify_catalog_summary(total_alerts, total_cats, total_errors)


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Monitor de precios Ripley + Falabella Chile")
    parser.add_argument("--once", action="store_true", help="Escanear una vez y salir")
    parser.add_argument("--debug", action="store_true", help="Modo debug del scraper")
    parser.add_argument("--store", type=str, default=None, choices=["ripley", "falabella", "paris", "easy", "sodimac", "jumbo", "abc", "columbia", "doite", "hushpuppies", "pcfactory", "multimarcas", "reebok", "bold", "wildlama", "mundovino", "liquidos", "booz"], help="Solo esta tienda")
    args = parser.parse_args()

    setup_logging(debug=args.debug)
    init_db()

    if args.once:
        run_catalog_scan(only_store=args.store, debug=args.debug)
        sys.exit(0)

    logging.info(f"Monitor iniciado — intervalo: {CATALOG_INTERVAL_HOURS}h | descuento >= {MIN_DISCOUNT:.0f}% (licores >= {LICORES_MIN_DISCOUNT:.0f}%) | 18 tiendas")

    run_catalog_scan(debug=args.debug)  # escaneo inmediato al arrancar

    schedule.every(CATALOG_INTERVAL_HOURS).hours.do(run_catalog_scan, debug=args.debug)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
