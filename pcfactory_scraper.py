"""
Scraper para PC Factory Chile.
API: /pcfactory-services-catalogo/v1/catalogo/productos?search=&orden=descuento
     /pcfactory-services-web-landing/v1/campanas/outlet-online/dest
precio.referencia = precio normal, precio.efectivo = precio oferta.
"""
import time
from dataclasses import dataclass

import requests

BASE_URL      = "https://www.pcfactory.cl"
ASSETS_URL    = "https://assets.pcfactory.cl"
CATALOG_API   = "https://api.pcfactory.cl/pcfactory-services-catalogo/v1/catalogo/productos"
OUTLET_API    = "https://api.pcfactory.cl/pcfactory-services-web-landing/v1/campanas/outlet-online/dest"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.pcfactory.cl/",
    "Origin": "https://www.pcfactory.cl",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "PC Factory"
    image_url: str = ""


def _parse_item(item: dict, category_name: str, min_discount: float) -> Product | None:
    try:
        nombre = (item.get("nombre") or "").strip()
        if not nombre:
            return None

        slug = item.get("slug", "")
        url = f"{BASE_URL}/producto/{slug}" if slug else BASE_URL

        precio = item.get("precio") or {}
        normal_price = int(precio.get("referencia") or 0)
        sale_price   = int(precio.get("efectivo") or 0)

        if not normal_price or not sale_price or sale_price >= normal_price:
            return None

        discount = (normal_price - sale_price) / normal_price * 100
        if discount < min_discount:
            return None

        thumbnail = item.get("thumbnail", "")
        image_url = f"{ASSETS_URL}{thumbnail}" if thumbnail else ""

        cat = category_name or (item.get("categoria") or {}).get("nombre", "")

        return Product(
            name=nombre[:120],
            url=url,
            normal_price=normal_price,
            sale_price=sale_price,
            discount_pct=round(discount, 1),
            category=cat,
            image_url=image_url,
        )
    except Exception:
        return None


def _scrape_catalog(category_name: str, min_discount: float, max_pages: int, debug: bool) -> list[Product]:
    results: list[Product] = []
    seen: set = set()

    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(
                CATALOG_API,
                params={"pagina": page, "porPagina": 50, "search": "", "orden": "descuento"},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if debug:
                print(f"  [pcfactory] Error catalogo p{page}: {e}")
            break

        items = data.get("content", {}).get("items", [])
        if not items:
            break

        found = 0
        below_threshold = 0
        for item in items:
            pid = str(item.get("id", ""))
            if pid in seen:
                continue
            seen.add(pid)

            precio = item.get("precio") or {}
            ref = float(precio.get("referencia") or 0)
            ef  = float(precio.get("efectivo") or 0)
            if ref > 0 and ef > 0 and ef < ref:
                discount = (ref - ef) / ref * 100
                if discount < min_discount:
                    below_threshold += 1
            
            p = _parse_item(item, category_name, min_discount)
            if p:
                results.append(p)
                found += 1

        if debug:
            print(f"  [pcfactory] catalogo p{page}: {len(items)} items, {found} con >={min_discount:.0f}%")

        # Si mas de la mitad de los items estan bajo el umbral, parar
        if below_threshold > len(items) * 0.5:
            break

        total_pages = data.get("content", {}).get("pageable", {}).get("totalPages", 1)
        if page >= total_pages:
            break

        time.sleep(0.5)

    return results


def _scrape_outlet(category_name: str, min_discount: float, debug: bool) -> list[Product]:
    results: list[Product] = []
    seen: set = set()

    for page in range(10):
        try:
            resp = requests.get(
                OUTLET_API,
                params={"size": 50, "page": page},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if debug:
                print(f"  [pcfactory] Error outlet p{page}: {e}")
            break

        items = data.get("content", {}).get("items", [])
        if not items:
            break

        found = 0
        for item in items:
            pid = str(item.get("id", ""))
            if pid in seen:
                continue
            seen.add(pid)

            p = _parse_item(item, category_name, min_discount)
            if p:
                results.append(p)
                found += 1

        if debug:
            print(f"  [pcfactory] outlet p{page}: {len(items)} items, {found} con >={min_discount:.0f}%")

        pageable = data.get("content", {}).get("pageable", {})
        if page + 1 >= pageable.get("totalPages", 1):
            break

        time.sleep(0.5)

    return results


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 30.0,
    max_pages: int = 20,
    debug: bool = False,
) -> list[Product]:
    if "outlet" in url.lower():
        return _scrape_outlet(category_name, min_discount, debug)
    return _scrape_catalog(category_name, min_discount, max_pages, debug)
