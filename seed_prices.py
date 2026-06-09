"""
Pre-carga el historial de precios con TODOS los productos actuales
de Liquidos.cl y Booz.cl, sin filtro de descuento.
Corre una sola vez para tener una base de comparación real.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup
from storage import init_db, save_price

HEADERS_JSON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.liquidos.cl/",
}
HEADERS_HTML = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}


def seed_liquidos():
    categories = ["whisky", "vino", "cerveza", "pisco", "ron", "vodka", "gin", "tequila", "espumante", "licor"]
    total = 0
    for cat in categories:
        url = f"https://www.liquidos.cl/api/products/category/{cat}?store_id=9"
        try:
            r = requests.get(url, headers=HEADERS_JSON, timeout=15)
            products = r.json().get("data", {}).get("products", [])
        except Exception as e:
            print(f"  [liquidos] Error en {cat}: {e}")
            continue

        saved = 0
        for p in products:
            ref = p.get("reference_price")
            prices_list = p.get("prices", [])
            pid = p.get("id", "")
            slug = p.get("slug", "")
            name = p.get("name", "Sin nombre")
            product_url = f"https://www.liquidos.cl/productos/{pid}/{slug}"

            if ref and ref > 0 and name:
                save_price(name, product_url, int(round(ref)))

            if prices_list and name:
                sale = int(round(prices_list[0]["price"]))
                if sale > 0:
                    save_price(name, product_url, sale)
                    saved += 1

        print(f"  [liquidos] {cat}: {saved}/{len(products)} productos guardados")
        total += saved

    print(f"  [liquidos] TOTAL: {total} precios guardados")
    return total


def seed_booz():
    catalogs = [
        ("Cervezas",      "https://www.booz.cl/catalogo/cervezas"),
        ("Vinos Tintos",  "https://www.booz.cl/catalogo/vinos-tintos"),
        ("Vinos Blancos",  "https://www.booz.cl/catalogo/vinos-blancos"),
        ("Whisky",        "https://www.booz.cl/catalogo/especial-de-whisky"),
        ("Pisco",         "https://www.booz.cl/catalogo/pisco-clasico"),
        ("Ofertas",       "https://www.booz.cl/catalogo/ofertas-de-la-semana"),
        ("Liquidacion",   "https://www.booz.cl/catalogo/liquidacion-licores-y-destilados"),
    ]
    total = 0
    for cat_name, cat_url in catalogs:
        try:
            r = requests.get(cat_url, headers=HEADERS_HTML, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"  [booz] Error en {cat_name}: {e}")
            continue

        links = [a for a in soup.find_all("a", href=True) if "/productos/" in a.get("href", "")]
        saved = 0
        seen = set()
        for a in links:
            href = a.get("href", "")
            product_url = f"https://www.booz.cl{href}"
            if product_url in seen:
                continue
            seen.add(product_url)

            img = a.find("img")
            name = img.get("alt", "").strip() if img else ""
            if not name:
                continue

            card = a
            for _ in range(10):
                card = card.parent
                if not card:
                    break
                if card.find("span", class_=lambda c: c and "line-through" in (c if isinstance(c, str) else " ".join(c))):
                    break

            if not card:
                continue

            import re
            def parse_price(text):
                digits = re.sub(r"[^\d]", "", text)
                return int(digits) if digits else 0

            sale_span = card.find("span", class_=lambda c: c and "text-red-700" in (c if isinstance(c, str) else " ".join(c)))
            normal_span = card.find("span", class_=lambda c: c and "line-through" in (c if isinstance(c, str) else " ".join(c)))

            if normal_span:
                normal = parse_price(normal_span.get_text())
                if normal > 0:
                    save_price(name, product_url, normal)

            if sale_span:
                sale = parse_price(sale_span.get_text())
                if sale > 0:
                    save_price(name, product_url, sale)
                    saved += 1

        print(f"  [booz] {cat_name}: {saved} productos guardados")
        total += saved

    print(f"  [booz] TOTAL: {total} precios guardados")
    return total


if __name__ == "__main__":
    init_db()
    print("Cargando historial de precios de Liquidos.cl...")
    n1 = seed_liquidos()
    print()
    print("Cargando historial de precios de Booz.cl...")
    n2 = seed_booz()
    print()
    print(f"Historial pre-cargado: {n1 + n2} entradas en prices.db")
    print("El proximo escaneo del bot ya tendra base de comparacion real.")
