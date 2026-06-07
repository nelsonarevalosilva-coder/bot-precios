"""
Agente de monitoreo de precios de Ripley Chile.

Uso:
    python monitor.py                  # Inicia el monitoreo continuo
    python monitor.py --once           # Chequea una sola vez y sale
    python monitor.py --debug          # Muestra detalles del scraping
    python monitor.py --test-telegram  # Verifica la conexión con Telegram
    python monitor.py --add-product    # Asistente para agregar un producto
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import schedule
from dotenv import load_dotenv

from notifier import notify_error, notify_price_drop, notify_target_reached, test_connection
from scraper import scrape_price
from storage import get_last_price, init_db, save_price

load_dotenv()

PRODUCTS_FILE = Path(__file__).parent / "products.json"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))


def load_products() -> list[dict]:
    if not PRODUCTS_FILE.exists():
        print(f"[monitor] No se encontró {PRODUCTS_FILE}")
        return []
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def check_product(product: dict, debug: bool = False):
    name = product["name"]
    url = product["url"]
    target = product.get("target_price")
    selector = product.get("selector")

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Chequeando: {name}")

    price = scrape_price(url, custom_selector=selector, debug=debug)

    if price is None:
        print(f"  ✗ No se pudo obtener el precio")
        notify_error(name, url, "No se pudo extraer el precio del sitio")
        return

    print(f"  Precio actual: ${price:,}")

    last_price = get_last_price(url)
    save_price(name, url, price)

    if last_price is None:
        print(f"  → Primera lectura guardada")
        return

    print(f"  Precio anterior: ${last_price:,}")

    if price < last_price:
        diff_pct = ((last_price - price) / last_price) * 100
        print(f"  ↓ BAJÓ ${last_price - price:,} ({diff_pct:.1f}%)")
        notify_price_drop(name, url, last_price, price)

    if target and price <= target:
        print(f"  🎯 Precio objetivo alcanzado! ${price:,} ≤ ${target:,}")
        notify_target_reached(name, url, price, target)


def run_check(debug: bool = False):
    products = load_products()
    if not products:
        print("[monitor] No hay productos en products.json")
        return
    for product in products:
        check_product(product, debug=debug)


def add_product_wizard():
    print("\n=== Agregar nuevo producto ===")
    name = input("Nombre del producto: ").strip()
    url = input("URL del producto en ripley.cl: ").strip()
    target_str = input("Precio objetivo en CLP (Enter para omitir): ").strip()
    target = int(target_str.replace(".", "").replace(",", "")) if target_str else None

    products = load_products()
    products.append({
        "name": name,
        "url": url,
        "target_price": target,
        "selector": None,
    })

    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Producto agregado: {name}")
    print(f"  Chequeando precio inicial...")
    check_product(products[-1], debug=True)


def main():
    parser = argparse.ArgumentParser(description="Monitor de precios Ripley Chile")
    parser.add_argument("--once", action="store_true", help="Chequear una vez y salir")
    parser.add_argument("--debug", action="store_true", help="Modo debug del scraper")
    parser.add_argument("--test-telegram", action="store_true", help="Verificar conexión Telegram")
    parser.add_argument("--add-product", action="store_true", help="Asistente para agregar producto")
    args = parser.parse_args()

    init_db()

    if args.test_telegram:
        print("[monitor] Probando conexión con Telegram...")
        ok = test_connection()
        sys.exit(0 if ok else 1)

    if args.add_product:
        add_product_wizard()
        sys.exit(0)

    if args.once:
        run_check(debug=args.debug)
        sys.exit(0)

    # Modo continuo
    print(f"[monitor] Iniciando monitoreo cada {CHECK_INTERVAL} minutos")
    print(f"[monitor] Productos cargados: {len(load_products())}")
    print(f"[monitor] Presiona Ctrl+C para detener\n")

    run_check(debug=args.debug)  # chequeo inmediato al arrancar

    schedule.every(CHECK_INTERVAL).minutes.do(run_check, debug=args.debug)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
