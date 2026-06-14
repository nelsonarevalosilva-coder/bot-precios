"""
Scraper para Xiaomi Chile — mi.com/cl.
Requiere IP chilena. Retorna [] si bloqueado por geo-restricción.
"""
import logging
import re
import time
from dataclasses import dataclass

import requests

BASE_URL = "https://www.mi.com/cl"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Accept-Language": "es-CL,es;q=0.9",
    "Referer": f"{BASE_URL}/",
}

PAGE_SIZE = 50


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Xiaomi"


def _clean_price(val) -> int | None:
    if val is None:
        return None
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_products(items: list, category_name: str, min_discount: float, seen: set) -> list[Product]:
    results = []
    for item in items:
        try:
            name = item.get("name") or item.get("title") or item.get("product_name") or ""
            if not name:
                continue

            pid = str(item.get("id") or item.get("product_id") or "")
            product_url = item.get("url") or item.get("link") or (f"{BASE_URL}/product/{pid}" if pid else "")
            if not product_url or product_url in seen:
                continue
            if not product_url.startswith("http"):
                product_url = f"{BASE_URL}{product_url}"

            sale = _clean_price(
                item.get("price") or item.get("sale_price") or
                item.get("current_price") or item.get("market_price")
            )
            normal = _clean_price(
                item.get("original_price") or item.get("market_price") or
                item.get("compare_price") or item.get("old_price")
            )

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
                category=category_name, store="Xiaomi",
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

    try:
        session.get(BASE_URL, timeout=12, allow_redirects=True)
    except Exception:
        pass

    # Intentar la API de listado de productos de mi.com
    for page_num in range(1, max_pages + 1):
        try:
            resp = session.get(
                f"{BASE_URL}/shop/list",
                params={"page": page_num, "pageSize": PAGE_SIZE, "type": "all"},
                timeout=15,
            )
            if resp.status_code != 200:
                if debug:
                    print(f"  [xiaomi] shop/list status {resp.status_code}")
                break

            data = resp.json()
            items = (
                data.get("data", {}).get("products") or
                data.get("products") or
                data.get("items") or
                (data if isinstance(data, list) else [])
            )
            if not items:
                break

            found = _parse_products(items, category_name, min_discount, seen)
            results.extend(found)
            if debug:
                print(f"  [xiaomi] p{page_num}: {len(items)} items | desc: {len(found)}")

            if len(items) < PAGE_SIZE:
                break
            time.sleep(0.5)

        except Exception as e:
            logging.error("[xiaomi] Error p%d: %s", page_num, e)
            break

    return results
