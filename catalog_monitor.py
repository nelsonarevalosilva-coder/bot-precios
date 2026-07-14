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
import ikea_scraper
import amoble_scraper
import silkperfumes_scraper
import blushbar_scraper
import sallybeauty_scraper
import sokobox_scraper
import gotta_scraper
import saxoline_scraper
import kippichile_scraper
import rosen_scraper
import ahumada_scraper
import cruzverde_scraper
import pethome_scraper
import merrell_scraper
import lippi_scraper
import fila_scraper
import puma_scraper
import crocs_scraper
import vans_scraper
import asics_scraper
import hoka_scraper
import reebok_scraper
import pcfactory_scraper
import superzoo_scraper
import laika_scraper
import thebodyshop_scraper
import mundoaromas_scraper
import cosmetic_scraper
import alishaperfumes_scraper
import lodoro_scraper
import santiagoperfumes_scraper
import adidas_scraper
import nike_scraper
import ofertaperfumes_scraper
import yauras_scraper
import eliteperfumes_scraper
import sairam_scraper
import mercadolibre_scraper
import bata_scraper
import newbalance_scraper
import converse_scraper
import skechers_scraper
import decathlon_scraper
import underarmour_scraper
import zara_scraper
import bershka_scraper
import pullandbear_scraper
import stradivarius_scraper
import hm_scraper
import levis_scraper
import tommy_scraper
import calvinklein_scraper
import tricot_scraper
import xiaomi_scraper
import corona_scraper
import buscalibre_scraper
import santa_isabel_scraper
import unimarc_scraper
import lider_scraper
import rappi_monitor
import ubereats_monitor
from notifier import notify_big_discount, notify_catalog_summary, notify_price_error, get_channel_key_for_product
from storage import clear_old_notifications, get_min_price_with_date, get_last_prices, has_been_notified, get_last_notified_price, init_db, mark_notified, save_price

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
IKEA_CATEGORIES_FILE = BASE_DIR / "ikea_categories.json"
AMOBLE_CATEGORIES_FILE = BASE_DIR / "amoble_categories.json"
SILKPERFUMES_CATEGORIES_FILE = BASE_DIR / "silkperfumes_categories.json"
BLUSHBAR_CATEGORIES_FILE = BASE_DIR / "blushbar_categories.json"
SALLYBEAUTY_CATEGORIES_FILE = BASE_DIR / "sallybeauty_categories.json"
SOKOBOX_CATEGORIES_FILE = BASE_DIR / "sokobox_categories.json"
GOTTA_CATEGORIES_FILE = BASE_DIR / "gotta_categories.json"
SAXOLINE_CATEGORIES_FILE = BASE_DIR / "saxoline_categories.json"
KIPPICHILE_CATEGORIES_FILE = BASE_DIR / "kippichile_categories.json"
ROSEN_CATEGORIES_FILE = BASE_DIR / "rosen_categories.json"
AHUMADA_CATEGORIES_FILE = BASE_DIR / "ahumada_categories.json"
CRUZVERDE_CATEGORIES_FILE  = BASE_DIR / "cruzverde_categories.json"
PETHOME_CATEGORIES_FILE    = BASE_DIR / "pethome_categories.json"
MERRELL_CATEGORIES_FILE    = BASE_DIR / "merrell_categories.json"
LIPPI_CATEGORIES_FILE      = BASE_DIR / "lippi_categories.json"
FILA_CATEGORIES_FILE       = BASE_DIR / "fila_categories.json"
PUMA_CATEGORIES_FILE       = BASE_DIR / "puma_categories.json"
CROCS_CATEGORIES_FILE      = BASE_DIR / "crocs_categories.json"
VANS_CATEGORIES_FILE       = BASE_DIR / "vans_categories.json"
ASICS_CATEGORIES_FILE      = BASE_DIR / "asics_categories.json"
HOKA_CATEGORIES_FILE       = BASE_DIR / "hoka_categories.json"
REEBOK_CATEGORIES_FILE     = BASE_DIR / "reebok_categories.json"
PCFACTORY_CATEGORIES_FILE  = BASE_DIR / "pcfactory_categories.json"
SUPERZOO_CATEGORIES_FILE   = BASE_DIR / "superzoo_categories.json"
LAIKA_CATEGORIES_FILE      = BASE_DIR / "laika_categories.json"
THEBODYSHOP_CATEGORIES_FILE = BASE_DIR / "thebodyshop_categories.json"
MUNDOAROMAS_CATEGORIES_FILE = BASE_DIR / "mundoaromas_categories.json"
COSMETIC_CATEGORIES_FILE = BASE_DIR / "cosmetic_categories.json"
ALISHAPERFUMES_CATEGORIES_FILE = BASE_DIR / "alishaperfumes_categories.json"
LODORO_CATEGORIES_FILE = BASE_DIR / "lodoro_categories.json"
SANTIAGOPERFUMES_CATEGORIES_FILE = BASE_DIR / "santiagoperfumes_categories.json"
ADIDAS_CATEGORIES_FILE = BASE_DIR / "adidas_categories.json"
NIKE_CATEGORIES_FILE = BASE_DIR / "nike_categories.json"
OFERTAPERFUMES_CATEGORIES_FILE = BASE_DIR / "ofertaperfumes_categories.json"
YAURAS_CATEGORIES_FILE = BASE_DIR / "yauras_categories.json"
ELITEPERFUMES_CATEGORIES_FILE = BASE_DIR / "eliteperfumes_categories.json"
SAIRAM_CATEGORIES_FILE = BASE_DIR / "sairam_categories.json"
MERCADOLIBRE_CATEGORIES_FILE = BASE_DIR / "mercadolibre_categories.json"
BATA_CATEGORIES_FILE = BASE_DIR / "bata_categories.json"
NEWBALANCE_CATEGORIES_FILE = BASE_DIR / "newbalance_categories.json"
CONVERSE_CATEGORIES_FILE = BASE_DIR / "converse_categories.json"
SKECHERS_CATEGORIES_FILE = BASE_DIR / "skechers_categories.json"
DECATHLON_CATEGORIES_FILE = BASE_DIR / "decathlon_categories.json"
UNDERARMOUR_CATEGORIES_FILE = BASE_DIR / "underarmour_categories.json"
ZARA_CATEGORIES_FILE = BASE_DIR / "zara_categories.json"
BERSHKA_CATEGORIES_FILE = BASE_DIR / "bershka_categories.json"
PULLANDBEAR_CATEGORIES_FILE = BASE_DIR / "pullandbear_categories.json"
STRADIVARIUS_CATEGORIES_FILE = BASE_DIR / "stradivarius_categories.json"
HM_CATEGORIES_FILE = BASE_DIR / "hm_categories.json"
LEVIS_CATEGORIES_FILE = BASE_DIR / "levis_categories.json"
TOMMY_CATEGORIES_FILE = BASE_DIR / "tommy_categories.json"
CALVINKLEIN_CATEGORIES_FILE = BASE_DIR / "calvinklein_categories.json"
TRICOT_CATEGORIES_FILE = BASE_DIR / "tricot_categories.json"
XIAOMI_CATEGORIES_FILE = BASE_DIR / "xiaomi_categories.json"
CORONA_CATEGORIES_FILE = BASE_DIR / "corona_categories.json"
BUSCALIBRE_CATEGORIES_FILE = BASE_DIR / "buscalibre_categories.json"
SANTA_ISABEL_CATEGORIES_FILE = BASE_DIR / "santa_isabel_categories.json"
UNIMARC_CATEGORIES_FILE = BASE_DIR / "unimarc_categories.json"
LOG_FILE = BASE_DIR / "monitor.log"
CATALOG_INTERVAL_HOURS = float(os.getenv("CATALOG_INTERVAL_HOURS", "0.5"))
RAPPI_INTERVAL_HOURS = float(os.getenv("RAPPI_INTERVAL_HOURS", "2"))
UBEREATS_INTERVAL_HOURS = float(os.getenv("UBEREATS_INTERVAL_HOURS", "2"))
MIN_DISCOUNT = float(os.getenv("MIN_DISCOUNT_PCT", "70"))
PRICE_ERROR_THRESHOLD = float(os.getenv("PRICE_ERROR_THRESHOLD_PCT", "80"))
LICORES_MIN_DISCOUNT = 30.0  # umbral para licores y tiendas con descuentos bajos
LICORES_STORES = {"El Mundo del Vino", "Liquidos", "Booz", "Sokobox", "Cruz Verde"}
PERFUMES_MIN_DISCOUNT = 90.0
PERFUMES_STORES = {
    "Multimarcas Perfumes", "Silk Perfumes", "Mundo Aromas", "Alisha Perfumes",
    "Lo Doro", "Santiago Perfumes", "Oferta Perfumes", "Yauras", "Elite Perfumes", "Sairam",
}


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
                max_pages=cat.get("max_pages", 3),
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
                last_prices = get_last_prices(p.url, limit=5)
                prev_notified_price = get_last_notified_price(p.url)
                save_price(p.name, p.url, p.sale_price)

                if has_been_notified(p.url, p.sale_price):
                    prev_str = f"${prev_notified_price:,}" if prev_notified_price else "precio anterior"
                    logging.info(f"      (ya notificado a {prev_str} — sin mejora)")
                    continue

                if p.discount_pct >= PRICE_ERROR_THRESHOLD:
                    ok = notify_price_error(p, min_data, last_prices)
                    if ok:
                        total_errors += 1
                else:
                    ok = notify_big_discount(p, min_data, last_prices, prev_notified_price=prev_notified_price)
                    if ok:
                        total_alerts += 1

                if ok:
                    ch_key = get_channel_key_for_product(p)
                    mark_notified(p.url, p.name, p.discount_pct, p.sale_price, ch_key)

            time.sleep(3)

        except Exception as e:
            logging.error(f"  Error al escanear {cat['name']}: {e}")
            continue

    return total_alerts, total_errors, len(categories)


def scan_lider(min_discount: float = 20.0, debug: bool = False) -> tuple[int, int]:
    """Escanea Lider (Playwright). Retorna (alertas, errores)."""
    logging.info(">> [Lider] Escaneando con Playwright...")
    try:
        products = lider_scraper.scrape(min_discount=min_discount, debug=debug)
    except Exception as e:
        logging.error(f"  [Lider] Error al escanear: {e}")
        return 0, 0

    total_alerts = 0
    total_errors = 0

    for p in products:
        tag = "ERROR PRECIO" if p.discount_pct >= PRICE_ERROR_THRESHOLD else "OFERTA"
        logging.info(f"    [{tag}] {p.name[:55]} | {p.discount_pct:.0f}% | ${p.sale_price:,}")

        min_data = get_min_price_with_date(p.url)
        last_prices = get_last_prices(p.url, limit=5)
        prev_notified_price = get_last_notified_price(p.url)
        save_price(p.name, p.url, p.sale_price)

        if has_been_notified(p.url, p.sale_price):
            prev_str = f"${prev_notified_price:,}" if prev_notified_price else "precio anterior"
            logging.info(f"      (ya notificado a {prev_str} — sin mejora)")
            continue

        ok = False
        if p.discount_pct >= PRICE_ERROR_THRESHOLD:
            ok = notify_price_error(p, min_data, last_prices)
            if ok:
                total_errors += 1
        else:
            ok = notify_big_discount(p, min_data, last_prices, prev_notified_price=prev_notified_price)
            if ok:
                total_alerts += 1

        if ok:
            ch_key = get_channel_key_for_product(p)
            mark_notified(p.url, p.name, p.discount_pct, p.sale_price, ch_key)

    logging.info(f"[Lider] TERMINADO — ofertas: {total_alerts} | errores precio: {total_errors}")
    return total_alerts, total_errors


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
        if store_name in PERFUMES_STORES:
            return PERFUMES_MIN_DISCOUNT
        if store_name in LICORES_STORES:
            return LICORES_MIN_DISCOUNT
        if store_name == "The Body Shop":
            return 20.0
        if store_name in {"Nike", "Adidas"}:
            return 25.0
        if store_name in {"SuperZoo", "PetHome", "Laika"}:
            return 25.0
        if store_name in {"IKEA", "Merrell", "Lippi", "Fila", "Puma", "Crocs", "Vans", "Asics", "HOKA", "Reebok"}:
            return 30.0
        if store_name in {"Bershka", "Pull&Bear", "Stradivarius", "H&M", "Levi's", "Tommy Hilfiger", "Calvin Klein", "Tricot", "Zara"}:
            return 25.0
        if store_name == "Buscalibre":
            return 70.0
        if store_name in {"Jumbo", "Santa Isabel", "Unimarc", "Lider"}:
            return 20.0
        return min_discount

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
    if only_store is None or only_store.lower() == "ikea":
        stores_to_run.append((load_json(IKEA_CATEGORIES_FILE), ikea_scraper, "IKEA", _store_discount("IKEA")))
    if only_store is None or only_store.lower() == "amoble":
        stores_to_run.append((load_json(AMOBLE_CATEGORIES_FILE), amoble_scraper, "Amoble", _store_discount("Amoble")))
    if only_store is None or only_store.lower() == "silkperfumes":
        stores_to_run.append((load_json(SILKPERFUMES_CATEGORIES_FILE), silkperfumes_scraper, "Silk Perfumes", _store_discount("Silk Perfumes")))
    if only_store is None or only_store.lower() == "blushbar":
        stores_to_run.append((load_json(BLUSHBAR_CATEGORIES_FILE), blushbar_scraper, "Blush-Bar", _store_discount("Blush-Bar")))
    if only_store is None or only_store.lower() == "sallybeauty":
        stores_to_run.append((load_json(SALLYBEAUTY_CATEGORIES_FILE), sallybeauty_scraper, "Sally Beauty", _store_discount("Sally Beauty")))
    if only_store is None or only_store.lower() == "sokobox":
        stores_to_run.append((load_json(SOKOBOX_CATEGORIES_FILE), sokobox_scraper, "Sokobox", _store_discount("Sokobox")))
    if only_store is None or only_store.lower() == "gotta":
        stores_to_run.append((load_json(GOTTA_CATEGORIES_FILE), gotta_scraper, "Gotta", _store_discount("Gotta")))
    if only_store is None or only_store.lower() == "saxoline":
        stores_to_run.append((load_json(SAXOLINE_CATEGORIES_FILE), saxoline_scraper, "Saxoline", _store_discount("Saxoline")))
    if only_store is None or only_store.lower() == "kippichile":
        stores_to_run.append((load_json(KIPPICHILE_CATEGORIES_FILE), kippichile_scraper, "Kippy Chile", _store_discount("Kippy Chile")))
    if only_store is None or only_store.lower() == "rosen":
        stores_to_run.append((load_json(ROSEN_CATEGORIES_FILE), rosen_scraper, "Rosen", _store_discount("Rosen")))
    if only_store is None or only_store.lower() == "ahumada":
        stores_to_run.append((load_json(AHUMADA_CATEGORIES_FILE), ahumada_scraper, "Farmacia Ahumada", _store_discount("Farmacia Ahumada")))
    if only_store is None or only_store.lower() == "cruzverde":
        stores_to_run.append((load_json(CRUZVERDE_CATEGORIES_FILE), cruzverde_scraper, "Cruz Verde", _store_discount("Cruz Verde")))
    if only_store is None or only_store.lower() == "pethome":
        stores_to_run.append((load_json(PETHOME_CATEGORIES_FILE), pethome_scraper, "PetHome", _store_discount("PetHome")))
    if only_store is None or only_store.lower() == "merrell":
        stores_to_run.append((load_json(MERRELL_CATEGORIES_FILE), merrell_scraper, "Merrell", _store_discount("Merrell")))
    if only_store is None or only_store.lower() == "lippi":
        stores_to_run.append((load_json(LIPPI_CATEGORIES_FILE), lippi_scraper, "Lippi", _store_discount("Lippi")))
    if only_store is None or only_store.lower() == "fila":
        stores_to_run.append((load_json(FILA_CATEGORIES_FILE), fila_scraper, "Fila", _store_discount("Fila")))
    if only_store is None or only_store.lower() == "puma":
        stores_to_run.append((load_json(PUMA_CATEGORIES_FILE), puma_scraper, "Puma", _store_discount("Puma")))
    if only_store is None or only_store.lower() == "crocs":
        stores_to_run.append((load_json(CROCS_CATEGORIES_FILE), crocs_scraper, "Crocs", _store_discount("Crocs")))
    if only_store is None or only_store.lower() == "vans":
        stores_to_run.append((load_json(VANS_CATEGORIES_FILE), vans_scraper, "Vans", _store_discount("Vans")))
    if only_store is None or only_store.lower() == "asics":
        stores_to_run.append((load_json(ASICS_CATEGORIES_FILE), asics_scraper, "Asics", _store_discount("Asics")))
    if only_store is None or only_store.lower() == "hoka":
        stores_to_run.append((load_json(HOKA_CATEGORIES_FILE), hoka_scraper, "HOKA", _store_discount("HOKA")))
    if only_store is None or only_store.lower() == "superzoo":
        stores_to_run.append((load_json(SUPERZOO_CATEGORIES_FILE), superzoo_scraper, "SuperZoo", _store_discount("SuperZoo")))
    if only_store is None or only_store.lower() == "laika":
        stores_to_run.append((load_json(LAIKA_CATEGORIES_FILE), laika_scraper, "Laika", _store_discount("Laika")))
    if only_store is None or only_store.lower() == "thebodyshop":
        stores_to_run.append((load_json(THEBODYSHOP_CATEGORIES_FILE), thebodyshop_scraper, "The Body Shop", _store_discount("The Body Shop")))
    if only_store is None or only_store.lower() == "mundoaromas":
        stores_to_run.append((load_json(MUNDOAROMAS_CATEGORIES_FILE), mundoaromas_scraper, "Mundo Aromas", _store_discount("Mundo Aromas")))
    if only_store is None or only_store.lower() == "cosmetic":
        stores_to_run.append((load_json(COSMETIC_CATEGORIES_FILE), cosmetic_scraper, "Cosmetic", _store_discount("Cosmetic")))
    if only_store is None or only_store.lower() == "alishaperfumes":
        stores_to_run.append((load_json(ALISHAPERFUMES_CATEGORIES_FILE), alishaperfumes_scraper, "Alisha Perfumes", _store_discount("Alisha Perfumes")))
    if only_store is None or only_store.lower() == "lodoro":
        stores_to_run.append((load_json(LODORO_CATEGORIES_FILE), lodoro_scraper, "Lo Doro", _store_discount("Lo Doro")))
    if only_store is None or only_store.lower() == "santiagoperfumes":
        stores_to_run.append((load_json(SANTIAGOPERFUMES_CATEGORIES_FILE), santiagoperfumes_scraper, "Santiago Perfumes", _store_discount("Santiago Perfumes")))
    if only_store is None or only_store.lower() == "adidas":
        stores_to_run.append((load_json(ADIDAS_CATEGORIES_FILE), adidas_scraper, "Adidas", _store_discount("Adidas")))
    if only_store is None or only_store.lower() == "nike":
        stores_to_run.append((load_json(NIKE_CATEGORIES_FILE), nike_scraper, "Nike", _store_discount("Nike")))
    if only_store is None or only_store.lower() == "ofertaperfumes":
        stores_to_run.append((load_json(OFERTAPERFUMES_CATEGORIES_FILE), ofertaperfumes_scraper, "Oferta Perfumes", _store_discount("Oferta Perfumes")))
    if only_store is None or only_store.lower() == "yauras":
        stores_to_run.append((load_json(YAURAS_CATEGORIES_FILE), yauras_scraper, "Yauras", _store_discount("Yauras")))
    if only_store is None or only_store.lower() == "eliteperfumes":
        stores_to_run.append((load_json(ELITEPERFUMES_CATEGORIES_FILE), eliteperfumes_scraper, "Elite Perfumes", _store_discount("Elite Perfumes")))
    if only_store is None or only_store.lower() == "sairam":
        stores_to_run.append((load_json(SAIRAM_CATEGORIES_FILE), sairam_scraper, "Sairam", _store_discount("Sairam")))
    if only_store is None or only_store.lower() == "mercadolibre":
        stores_to_run.append((load_json(MERCADOLIBRE_CATEGORIES_FILE), mercadolibre_scraper, "Mercado Libre", _store_discount("Mercado Libre")))
    if only_store is None or only_store.lower() == "bata":
        stores_to_run.append((load_json(BATA_CATEGORIES_FILE), bata_scraper, "Bata", _store_discount("Bata")))
    if only_store is None or only_store.lower() == "newbalance":
        stores_to_run.append((load_json(NEWBALANCE_CATEGORIES_FILE), newbalance_scraper, "New Balance", _store_discount("New Balance")))
    if only_store is None or only_store.lower() == "converse":
        stores_to_run.append((load_json(CONVERSE_CATEGORIES_FILE), converse_scraper, "Converse", _store_discount("Converse")))
    if only_store is None or only_store.lower() == "skechers":
        stores_to_run.append((load_json(SKECHERS_CATEGORIES_FILE), skechers_scraper, "Skechers", _store_discount("Skechers")))
    if only_store is None or only_store.lower() == "decathlon":
        stores_to_run.append((load_json(DECATHLON_CATEGORIES_FILE), decathlon_scraper, "Decathlon", _store_discount("Decathlon")))
    if only_store is None or only_store.lower() == "underarmour":
        stores_to_run.append((load_json(UNDERARMOUR_CATEGORIES_FILE), underarmour_scraper, "Under Armour", _store_discount("Under Armour")))
    if only_store is None or only_store.lower() == "zara":
        stores_to_run.append((load_json(ZARA_CATEGORIES_FILE), zara_scraper, "Zara", _store_discount("Zara")))
    if only_store is None or only_store.lower() == "bershka":
        stores_to_run.append((load_json(BERSHKA_CATEGORIES_FILE), bershka_scraper, "Bershka", _store_discount("Bershka")))
    if only_store is None or only_store.lower() == "pullandbear":
        stores_to_run.append((load_json(PULLANDBEAR_CATEGORIES_FILE), pullandbear_scraper, "Pull&Bear", _store_discount("Pull&Bear")))
    if only_store is None or only_store.lower() == "stradivarius":
        stores_to_run.append((load_json(STRADIVARIUS_CATEGORIES_FILE), stradivarius_scraper, "Stradivarius", _store_discount("Stradivarius")))
    if only_store is None or only_store.lower() == "hm":
        stores_to_run.append((load_json(HM_CATEGORIES_FILE), hm_scraper, "H&M", _store_discount("H&M")))
    if only_store is None or only_store.lower() == "levis":
        stores_to_run.append((load_json(LEVIS_CATEGORIES_FILE), levis_scraper, "Levi's", _store_discount("Levi's")))
    if only_store is None or only_store.lower() == "tommy":
        stores_to_run.append((load_json(TOMMY_CATEGORIES_FILE), tommy_scraper, "Tommy Hilfiger", _store_discount("Tommy Hilfiger")))
    if only_store is None or only_store.lower() == "calvinklein":
        stores_to_run.append((load_json(CALVINKLEIN_CATEGORIES_FILE), calvinklein_scraper, "Calvin Klein", _store_discount("Calvin Klein")))
    if only_store is None or only_store.lower() == "tricot":
        stores_to_run.append((load_json(TRICOT_CATEGORIES_FILE), tricot_scraper, "Tricot", _store_discount("Tricot")))
    if only_store is None or only_store.lower() == "xiaomi":
        stores_to_run.append((load_json(XIAOMI_CATEGORIES_FILE), xiaomi_scraper, "Xiaomi", _store_discount("Xiaomi")))
    if only_store is None or only_store.lower() == "corona":
        stores_to_run.append((load_json(CORONA_CATEGORIES_FILE), corona_scraper, "Corona", _store_discount("Corona")))
    if only_store is None or only_store.lower() == "buscalibre":
        stores_to_run.append((load_json(BUSCALIBRE_CATEGORIES_FILE), buscalibre_scraper, "Buscalibre", _store_discount("Buscalibre")))
    if only_store is None or only_store.lower() == "santaisabel":
        stores_to_run.append((load_json(SANTA_ISABEL_CATEGORIES_FILE), santa_isabel_scraper, "Santa Isabel", _store_discount("Santa Isabel")))
    if only_store is None or only_store.lower() == "unimarc":
        stores_to_run.append((load_json(UNIMARC_CATEGORIES_FILE), unimarc_scraper, "Unimarc", _store_discount("Unimarc")))

    logging.info(f"Escaneando en paralelo: {', '.join(s[2] for s in stores_to_run) or '(ninguna)'}")

    total_alerts = 0
    total_errors = 0
    total_cats = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(stores_to_run))) as executor:
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

    # Lider: Playwright, corre aparte del pool paralelo
    if only_store is None or only_store.lower() == "lider":
        a, e = scan_lider(min_discount=_store_discount("Lider"), debug=debug)
        total_alerts += a
        total_errors += e

    # Supermercados: re-notificar al día siguiente (precios cambian diario)
    clear_old_notifications(days=1, url_pattern="%jumbo%")
    clear_old_notifications(days=1, url_pattern="%santaisabel%")
    clear_old_notifications(days=1, url_pattern="%unimarc%")
    clear_old_notifications(days=1, url_pattern="%lider.cl%")
    # Resto de tiendas: 7 días
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
    parser.add_argument("--store", type=str, default=None, choices=["ripley", "falabella", "paris", "easy", "sodimac", "jumbo", "abc", "columbia", "doite", "hushpuppies", "pcfactory", "multimarcas", "reebok", "bold", "wildlama", "mundovino", "liquidos", "booz", "ikea", "amoble", "silkperfumes", "blushbar", "sallybeauty", "sokobox", "gotta", "saxoline", "kippichile", "rosen", "ahumada", "cruzverde", "thebodyshop", "mundoaromas", "cosmetic", "alishaperfumes", "lodoro", "santiagoperfumes", "adidas", "nike", "ofertaperfumes", "yauras", "eliteperfumes", "sairam", "mercadolibre", "bata", "newbalance", "converse", "skechers", "decathlon", "underarmour", "zara", "bershka", "pullandbear", "stradivarius", "hm", "levis", "tommy", "calvinklein", "tricot", "xiaomi", "corona", "buscalibre", "santaisabel", "unimarc", "lider"], help="Solo esta tienda")
    args = parser.parse_args()

    setup_logging(debug=args.debug)
    init_db()

    if args.once:
        run_catalog_scan(only_store=args.store, debug=args.debug)
        sys.exit(0)

    logging.info(f"Monitor iniciado — intervalo: {CATALOG_INTERVAL_HOURS}h | descuento >= {MIN_DISCOUNT:.0f}% | 73 tiendas")
    logging.info(f"Rappi delivery monitor — intervalo: {RAPPI_INTERVAL_HOURS}h")
    logging.info(f"Uber Eats monitor — intervalo: {UBEREATS_INTERVAL_HOURS}h")

    run_catalog_scan(only_store=args.store, debug=args.debug)  # escaneo inmediato al arrancar

    # Delivery monitors: escaneo inicial diferido para no solapar con el catalog scan
    schedule.every(RAPPI_INTERVAL_HOURS).hours.do(rappi_monitor.run_scan)
    schedule.every(UBEREATS_INTERVAL_HOURS).hours.do(ubereats_monitor.run_scan)
    time.sleep(30)
    rappi_monitor.run_scan()
    ubereats_monitor.run_scan()

    schedule.every(CATALOG_INTERVAL_HOURS).hours.do(run_catalog_scan, only_store=args.store, debug=args.debug)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
