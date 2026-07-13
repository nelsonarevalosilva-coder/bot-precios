"""
Scraper para HOKA Chile (WooCommerce Store API v1).
Endpoint: /wp-json/wc/store/v1/products?on_sale=true&per_page=30&page=N
prices.regular_price = precio normal, prices.sale_price = precio oferta.
"""
import time
from dataclasses import dataclass

import requests

BASE_URL = "https://cl.hoka.com"
API_URL = f"{BASE_URL}/wp-json/wc/store/v1/products"
PAGE_SIZE = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "HOKA"
    image_url: str = ""


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 30.0,
    max_pages: int = 10,
    debug: bool = False,
) -> list[Product]:
    results: list[Product] = []
    seen: set = set()

    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(
                API_URL,
                params={"on_sale": "true", "per_page": PAGE_SIZE, "page": page},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            products = resp.json()
        except Exception as e:
            if debug:
                print(f"  [hoka] Error página {page}: {e}")
            break

        if not products:
            break

        found = 0
        for p in products:
            pid = p.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            name = (p.get("name") or "").strip()
            permalink = p.get("permalink", "")
            if not name or not permalink:
                continue

            prices = p.get("prices") or {}
            try:
                normal_price = int(prices.get("regular_price") or 0)
                sale_price   = int(prices.get("sale_price") or 0)
            except (ValueError, TypeError):
                continue

            if not normal_price or not sale_price or sale_price >= normal_price:
                continue

            discount = (normal_price - sale_price) / normal_price * 100
            if discount < min_discount:
                continue

            images = p.get("images") or []
            image_url = images[0].get("src", "") if images else ""

            results.append(Product(
                name=name[:120],
                url=permalink,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount, 1),
                category=category_name,
                image_url=image_url,
            ))
            found += 1

        if debug:
            print(f"  [hoka] página {page}: {len(products)} productos, {found} con >={min_discount:.0f}%")

        if len(products) < PAGE_SIZE:
            break

        time.sleep(0.5)

    return results
