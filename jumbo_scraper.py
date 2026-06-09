"""
Scraper de Jumbo Chile usando la API de Constructor.io (Cencosud).
"""
import time
from dataclasses import dataclass

import requests

CNSTRC_KEY = "key_JopvNXKS61kwGkBe"
SEARCH_URL = "https://ac.cnstrc.com/search/{query}"
PAGE_SIZE = 50

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.jumbo.cl/",
    "Origin": "https://www.jumbo.cl",
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
    store: str = "Jumbo"


def _extract_products(data: dict, category_name: str, min_discount: float) -> list[Product]:
    results = data.get("response", {}).get("results", [])
    products = []
    seen_ids: set = set()

    for item in results:
        try:
            d = item.get("data", {})
            name = item.get("value", "") or d.get("slug", "")
            if not name:
                continue

            url = d.get("DetailUrl", "") or d.get("url", "")
            if not url:
                continue

            sale_price = d.get("sellingPrice") or d.get("price")
            if not sale_price or not isinstance(sale_price, (int, float)):
                continue
            sale_price = int(sale_price)

            normal_price = int(d.get("originalPrice") or d.get("listPrice") or 0)
            if not normal_price or normal_price <= sale_price:
                normal_price = sale_price

            discount_pct = 0.0
            if normal_price > sale_price:
                discount_pct = (normal_price - sale_price) / normal_price * 100

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
                store="Jumbo",
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
                    print(f"    [jumbo] {category_name} p{page_num}: status {resp.status_code}")
                break

            data = resp.json()
            total = data.get("response", {}).get("total_num_results", 0)
            found = _extract_products(data, category_name, min_discount)

            unique = [p for p in found if p.url not in seen_ids]
            for p in unique:
                seen_ids.add(p.url)
            all_products.extend(unique)

            if debug:
                print(f"    [jumbo] {category_name} p{page_num}: total={total} con>={min_discount:.0f}%: {len(unique)}")

            if page_num * PAGE_SIZE >= total:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [jumbo] Error en {category_name} p{page_num}: {e}")
            break

    return all_products
