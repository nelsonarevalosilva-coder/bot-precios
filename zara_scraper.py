"""
Scraper para Zara Chile — API REST de Inditex.
Requiere IP chilena. Retorna [] si bloqueado por geo-restricción.
"""
import logging
import re
import time
from dataclasses import dataclass

import requests

BASE_URL = "https://www.zara.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "es-CL,es;q=0.9",
    "Referer": "https://www.zara.com/cl/es/",
    "X-Requested-With": "XMLHttpRequest",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Zara"


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 10 else None


def _parse_groups(data, category_name: str, min_discount: float, seen: set) -> list[Product]:
    results = []
    if not isinstance(data, dict):
        return results

    # Extraer todos los commercialComponents de cualquier estructura
    raw_items = []
    for group in (data.get("productGroups") or []):
        for elem in (group.get("elements") or []):
            raw_items.extend(elem.get("commercialComponents") or [])

    # Fallback: buscar en "sections"
    if not raw_items:
        for section in (data.get("sections") or []):
            for elem in (section.get("elements") or []):
                raw_items.extend(elem.get("commercialComponents") or [])

    for item in raw_items:
        try:
            name = item.get("name") or ""
            if not name:
                continue

            detail = item.get("detail") or {}
            link_obj = detail.get("link") or item.get("link") or {}
            product_url = link_obj.get("url") or (link_obj if isinstance(link_obj, str) else "")
            if not product_url:
                continue
            if not product_url.startswith("http"):
                product_url = f"{BASE_URL}{product_url}"
            if product_url in seen:
                continue

            # displayPrice = precio actual, oldPrice = precio original antes del descuento
            price_info = detail.get("displayPrice") or {}
            old_price_info = detail.get("oldPrice") or {}

            sale = _clean_price(price_info.get("value") or price_info.get("price"))
            normal = _clean_price(old_price_info.get("value") or old_price_info.get("price"))

            if not sale or not normal or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            seen.add(product_url)
            results.append(Product(
                name=name[:120], url=product_url,
                normal_price=normal, sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name, store="Zara",
            ))
        except Exception:
            continue
    return results


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 5,
    debug: bool = False,
) -> list[Product]:
    results: list[Product] = []
    seen: set = set()

    session = requests.Session()
    session.headers.update(HEADERS)

    # Calentar sesión para obtener cookies
    try:
        session.get("https://www.zara.com/cl/es/", timeout=15, allow_redirects=True)
    except Exception:
        pass

    # Extraer base de la URL (sin .html) y agregar parámetro AJAX
    base_page = re.sub(r"\.html$", "", url)

    for page_num in range(max_pages):
        try:
            params = {"ajax": "true", "action": "CATEGORYNAV"}
            if page_num > 0:
                params["start"] = str(page_num * 24)

            resp = session.get(base_page, params=params, timeout=15)
            if resp.status_code != 200:
                if debug:
                    print(f"  [zara] {category_name} status {resp.status_code}")
                break

            try:
                data = resp.json()
            except Exception:
                if debug:
                    print(f"  [zara] {category_name} respuesta no es JSON")
                break

            found = _parse_groups(data, category_name, min_discount, seen)
            results.extend(found)
            if debug:
                print(f"  [zara] {category_name} p{page_num+1}: {len(found)} productos")

            if not found:
                break
            time.sleep(1)

        except Exception as e:
            logging.error("[zara] Error en %s p%d: %s", category_name, page_num + 1, e)
            break

    return results
