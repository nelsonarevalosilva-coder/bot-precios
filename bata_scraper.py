"""
Scraper para Bata Chile — Shopify JSON API directa con requests.
"""
import logging
import re
import time
from dataclasses import dataclass

import requests

BASE_URL = "https://www.bata.cl"
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
    store: str = "Bata"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_shopify_json(data, category_name: str, min_discount: float, seen: set) -> list[Product]:
    results = []
    for p in (data.get("products") or []):
        try:
            handle = p.get("handle", "")
            if not handle or handle in seen:
                continue
            name = p.get("title", "")
            product_url = f"{BASE_URL}/products/{handle}"
            image_url = (p.get("images") or [{}])[0].get("src", "")
            best_sale = best_normal = 0
            best_disc = 0.0
            for v in p.get("variants", []):
                price = int(float(v.get("price") or 0))
                compare = v.get("compare_at_price")
                if not compare:
                    continue
                compare = int(float(compare))
                if compare <= price or price <= 0:
                    continue
                disc = (compare - price) / compare * 100
                if disc > best_disc:
                    best_disc, best_sale, best_normal = disc, price, compare
            if not best_sale or best_disc < min_discount:
                continue
            seen.add(handle)
            results.append(Product(name=name[:120], url=product_url, normal_price=best_normal,
                                   sale_price=best_sale, discount_pct=round(best_disc, 1),
                                   category=category_name, store="Bata", image_url=image_url))
        except Exception:
            continue
    return results


def scrape_category(url: str, category_name: str, min_discount: float = 40.0,
                    max_pages: int = 5, debug: bool = False) -> list[Product]:
    all_products: list[Product] = []
    seen: set = set()

    # Derivar slug de colección desde la URL
    slug = url.rstrip("/").split("/collections/")[-1].split("/")[0]
    api_base = f"{BASE_URL}/collections/{slug}/products.json"

    session = requests.Session()
    session.headers.update(HEADERS)

    for page in range(1, max_pages + 1):
        try:
            resp = session.get(api_base, params={"limit": 250, "page": page}, timeout=20)
            if resp.status_code != 200:
                if debug:
                    print(f"  [bata] p{page}: status {resp.status_code}")
                break
            data = resp.json()
            products = data.get("products", [])
            if not products:
                break
            found = _parse_shopify_json({"products": products}, category_name, min_discount, seen)
            all_products.extend(found)
            if debug:
                print(f"  [bata] p{page}: {len(products)} productos | con desc: {len(found)}")
            if len(products) < 250:
                break
            time.sleep(0.5)
        except Exception as e:
            logging.error("[bata] Error p%d: %s", page, e)
            break

    if debug:
        print(f"  [bata] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
