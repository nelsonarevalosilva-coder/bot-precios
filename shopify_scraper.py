"""
Scraper genérico para tiendas Shopify chilenas.
Usado por Columbia, Doite, Hush Puppies.
"""
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
    store: str = "Shopify"
    image_url: str = ""


def _base_url(collection_url: str) -> str:
    p = urlparse(collection_url)
    return f"{p.scheme}://{p.netloc}"


def _shopify_scrape(
    collection_url: str,
    category_name: str,
    store_name: str,
    min_discount: float,
    max_pages: int,
    debug: bool,
) -> list[Product]:
    base = _base_url(collection_url)
    api_url = collection_url.rstrip("/") + "/products.json"
    all_products: list[Product] = []
    seen_handles: set = set()

    for page_num in range(1, max_pages + 1):
        try:
            resp = requests.get(
                api_url,
                params={"limit": 250, "page": page_num},
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                if debug:
                    print(f"    [{store_name}] {category_name} p{page_num}: status {resp.status_code}")
                break

            products = resp.json().get("products", [])
            if not products:
                break

            for p in products:
                handle = p.get("handle", "")
                if not handle or handle in seen_handles:
                    continue
                seen_handles.add(handle)

                name = p.get("title", "")
                product_url = f"{base}/products/{handle}"
                image_url = (p.get("images") or [{}])[0].get("src", "")

                best_sale = best_normal = 0
                best_discount = 0.0

                for v in p.get("variants", []):
                    try:
                        price = int(float(v.get("price") or 0))
                        compare = v.get("compare_at_price")
                        if not compare:
                            continue
                        compare = int(float(compare))
                        if compare <= price or price <= 0:
                            continue

                        discount = (compare - price) / compare * 100
                        if discount > best_discount:
                            best_discount = discount
                            best_sale = price
                            best_normal = compare
                    except Exception:
                        continue

                if not best_sale:
                    continue

                is_price_error = best_sale < 1000 and best_normal > 5000
                if best_discount < min_discount and not is_price_error:
                    continue

                all_products.append(Product(
                    name=name[:120],
                    url=product_url,
                    normal_price=best_normal,
                    sale_price=best_sale,
                    discount_pct=round(best_discount, 1),
                    category=category_name,
                    store=store_name,
                    image_url=image_url,
                ))

            if debug:
                print(f"    [{store_name}] {category_name} p{page_num}: {len(products)} productos")

            if len(products) < 250:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [{store_name}] Error: {e}")
            break

    return all_products


def make_store_scraper(store_name: str):
    def scrape_category(
        url: str,
        category_name: str,
        min_discount: float = 70.0,
        max_pages: int = 3,
        debug: bool = False,
    ) -> list[Product]:
        return _shopify_scrape(url, category_name, store_name, min_discount, max_pages, debug)
    return scrape_category
