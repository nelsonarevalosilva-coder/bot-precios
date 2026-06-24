"""
Scraper genérico para tiendas VTEX chilenas.
Usado por Blush-Bar, Sally Beauty.
API pública: /api/catalog_system/pub/products/search?_from=N&_to=M
"""
import time
from dataclasses import dataclass

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
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
    store: str = "VTEX"
    image_url: str = ""


def _vtex_scrape(
    base_url: str,
    category_name: str,
    store_name: str,
    min_discount: float,
    max_pages: int,
    debug: bool,
) -> list[Product]:
    api = base_url.rstrip("/") + "/api/catalog_system/pub/products/search"
    results: list[Product] = []
    seen: set = set()

    for page in range(max_pages):
        _from = page * PAGE_SIZE
        _to = _from + PAGE_SIZE - 1
        try:
            resp = requests.get(
                api,
                params={"_from": _from, "_to": _to},
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code not in (200, 206):
                if debug:
                    print(f"    [{store_name}] status {resp.status_code} en pág {page + 1}")
                break

            items = resp.json()
            if not items:
                break

            for p in items:
                url = p.get("link", "")
                if not url or url in seen:
                    continue
                seen.add(url)

                name = p.get("productName", "").strip()
                if not name:
                    continue

                item = (p.get("items") or [{}])[0]
                offer = (item.get("sellers") or [{}])[0].get("commertialOffer", {})
                list_price = int(offer.get("ListPrice") or 0)
                sale_price = int(offer.get("Price") or 0)
                image_url = (item.get("images") or [{}])[0].get("imageUrl", "")

                if not list_price or not sale_price or list_price <= sale_price:
                    continue

                discount_pct = (list_price - sale_price) / list_price * 100
                if discount_pct < min_discount:
                    continue

                results.append(Product(
                    name=name[:120],
                    url=url,
                    normal_price=list_price,
                    sale_price=sale_price,
                    discount_pct=round(discount_pct, 1),
                    category=category_name,
                    store=store_name,
                    image_url=image_url,
                ))

            if debug:
                print(f"    [{store_name}] pág {page + 1}: {len(items)} productos")

            if len(items) < PAGE_SIZE:
                break

            time.sleep(0.5)

        except Exception as e:
            if debug:
                print(f"    [{store_name}] Error: {e}")
            break

    return results


def make_store_scraper(store_name: str):
    def scrape_category(
        url: str,
        category_name: str,
        min_discount: float = 40.0,
        max_pages: int = 30,
        debug: bool = False,
    ) -> list[Product]:
        return _vtex_scrape(url, category_name, store_name, min_discount, max_pages, debug)
    return scrape_category
