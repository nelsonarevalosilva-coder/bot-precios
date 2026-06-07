"""
Scraper de Easy Chile usando la API de Constructor.io.
No requiere Playwright — usa requests directamente.
"""

import time
from dataclasses import dataclass

import requests

CNSTRC_KEY = "key_AimxrTjorsjiKQPy"
SEARCH_URL = "https://ac.cnstrc.com/search/{query}"
PAGE_SIZE = 50

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.easy.cl/",
    "Origin": "https://www.easy.cl",
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Easy"


def _calc_normal_price(sale_price: int, discount_pct: float) -> int:
    if discount_pct <= 0 or discount_pct >= 100:
        return sale_price
    return round(sale_price / (1 - discount_pct / 100))


def _extract_products(data: dict, category_name: str, min_discount: float) -> list[Product]:
    results = data.get("response", {}).get("results", [])
    products = []
    seen_ids = set()

    for item in results:
        try:
            d = item.get("data", {})
            name = item.get("value", "") or d.get("slug", "")
            if not name:
                continue

            url = d.get("url", "")
            if not url:
                continue

            sale_price = d.get("sellingPrice") or d.get("displayedPrice")
            if not sale_price or not isinstance(sale_price, (int, float)):
                continue
            sale_price = int(sale_price)

            discount_pct = float(d.get("discountPercentage", 0) or 0)
            normal_price = int(d.get("originalPrice") or d.get("listPrice") or 0) or _calc_normal_price(sale_price, discount_pct)

            is_price_error = sale_price < 1000 and normal_price > 5000

            if discount_pct < min_discount and not is_price_error:
                continue

            product_id = d.get("id", url)
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            products.append(Product(
                name=name[:120],
                url=url,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Easy",
            ))
        except Exception:
            continue

    return products


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 70.0,
    max_pages: int = 3,
    debug: bool = False,
) -> list[Product]:
    query = url.split("query=")[-1] if "query=" in url else category_name

    all_products: list[Product] = []
    seen_ids: set = set()

    for page_num in range(1, max_pages + 1):
        try:
            params = {
                "key": CNSTRC_KEY,
                "page": page_num,
                "num_results_per_page": PAGE_SIZE,
                "section": "Products",
                "sort_by": "relevance",
            }
            resp = requests.get(
                SEARCH_URL.format(query=query),
                params=params,
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                if debug:
                    print(f"    [easy] {category_name} p{page_num}: status {resp.status_code}")
                break

            data = resp.json()
            total = data.get("response", {}).get("total_num_results", 0)
            found = _extract_products(data, category_name, min_discount)

            unique = [p for p in found if p.url not in seen_ids]
            for p in unique:
                seen_ids.add(p.url)
            all_products.extend(unique)

            if debug:
                print(f"    [easy] {category_name} p{page_num}: total={total} con>={min_discount:.0f}%: {len(unique)}")

            if page_num * PAGE_SIZE >= total:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [easy] Error en {category_name} p{page_num}: {e}")
            break

    return all_products
