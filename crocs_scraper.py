"""
Scraper para Crocs Chile (VTEX).
API: /api/catalog_system/pub/products/search?fq=productClusterIds:488&_from=0&_to=49
Price = precio oferta, ListPrice = precio normal.
"""
import re
import time
from dataclasses import dataclass

import requests

BASE_URL = "https://www.crocs.cl"
PAGE_SIZE = 50

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
    store: str = "Crocs"
    image_url: str = ""


def _cluster_id(url: str) -> str:
    m = re.search(r"productClusterIds[=:](\d+)", url)
    return m.group(1) if m else "488"


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 30.0,
    max_pages: int = 10,
    debug: bool = False,
) -> list[Product]:
    cluster = _cluster_id(url)
    api_base = f"{BASE_URL}/api/catalog_system/pub/products/search"
    results: list[Product] = []
    seen: set = set()

    for page in range(max_pages):
        from_idx = page * PAGE_SIZE
        to_idx = from_idx + PAGE_SIZE - 1
        params = {
            "fq": f"productClusterIds:{cluster}",
            "_from": from_idx,
            "_to": to_idx,
        }
        try:
            resp = requests.get(api_base, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            products = resp.json()
        except Exception as e:
            if debug:
                print(f"  [crocs] Error página {page}: {e}")
            break

        if not products:
            break

        found = 0
        for p in products:
            pid = p.get("productId", "")
            if pid in seen:
                continue
            seen.add(pid)

            name = (p.get("productName") or "").strip()
            link = p.get("link", "")
            if not name or not link:
                continue

            items = p.get("items") or []
            if not items:
                continue
            item0 = items[0]

            images = item0.get("images") or []
            image_url = images[0].get("imageUrl", "") if images else ""

            sellers = item0.get("sellers") or []
            if not sellers:
                continue
            offer = sellers[0].get("commertialOffer") or {}

            sale_price   = int(offer.get("Price", 0))
            normal_price = int(offer.get("ListPrice", 0))

            if not sale_price or not normal_price or sale_price >= normal_price:
                continue

            discount = (normal_price - sale_price) / normal_price * 100
            if discount < min_discount:
                continue

            if not offer.get("IsAvailable", True):
                continue

            results.append(Product(
                name=name[:120],
                url=link,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount, 1),
                category=category_name,
                image_url=image_url,
            ))
            found += 1

        if debug:
            print(f"  [crocs] página {page}: {len(products)} productos, {found} con >={min_discount:.0f}%")

        if len(products) < PAGE_SIZE:
            break

        time.sleep(0.5)

    return results
