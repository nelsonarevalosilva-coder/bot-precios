"""
Scraper para Santiago Perfumes — WooCommerce Store API.
"""
import json
import time
from dataclasses import dataclass

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
API_BASE = "https://www.santiagoperfumes.cl/wp-json/wc/store/products"
PAGE_SIZE = 25


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Santiago Perfumes"


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 20,
    debug: bool = False,
) -> list[Product]:
    results: list[Product] = []
    page = 1

    while page <= max_pages:
        try:
            resp = requests.get(
                API_BASE,
                params={"per_page": PAGE_SIZE, "on_sale": "true", "page": page},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            try:
                data = json.loads(resp.content.decode("utf-8-sig"))
            except Exception:
                data = resp.json()
        except Exception as e:
            if debug:
                print(f"  [santiagoperfumes] Error página {page}: {e}")
            break

        if not data:
            break

        total_pages = int(resp.headers.get("x-wp-totalpages", 1))

        for item in data:
            prices = item.get("prices", {})
            try:
                raw_normal = int(prices.get("regular_price") or 0)
                raw_sale = int(prices.get("sale_price") or 0)
                decimals = int(prices.get("currency_minor_unit", 0))
                divisor = 10 ** decimals if decimals else 1
                normal = raw_normal // divisor
                sale = raw_sale // divisor
            except Exception:
                continue

            if not normal or not sale or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            name = item.get("name", "").strip()
            product_url = item.get("permalink", "")
            if not name or not product_url:
                continue

            if debug:
                print(f"  [santiagoperfumes] {name[:60]} — ${sale:,} (normal ${normal:,}) {discount_pct:.1f}%")

            results.append(Product(
                name=name[:120],
                url=product_url,
                normal_price=normal,
                sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Santiago Perfumes",
            ))

        if debug:
            print(f"  [santiagoperfumes] Página {page}/{total_pages}: {len(data)} items")

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.4)

    return results
