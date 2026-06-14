"""
Scraper para Decathlon Chile — VTEX Intelligent Search + fallback catalog API.
Requiere IP chilena (geo-bloqueado desde el exterior).
"""
import logging
import time
from dataclasses import dataclass

import requests

BASE_URL = "https://www.decathlon.cl"
PAGE_SIZE = 50
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": f"{BASE_URL}/",
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
    store: str = "Decathlon"


def _parse_vtex_items(products: list, category_name: str, min_discount: float, seen: set) -> list[Product]:
    results = []
    for p in products:
        try:
            pid = str(p.get("productId") or p.get("productReference") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            name = p.get("productName", "").strip()
            if not name:
                continue

            link = p.get("link", "")
            product_url = link if link.startswith("http") else f"{BASE_URL}{link}"

            price_range = p.get("priceRange", {})
            normal = int(price_range.get("listPrice", {}).get("highPrice") or 0)
            sale = int(price_range.get("sellingPrice", {}).get("lowPrice") or 0)

            if not normal or not sale:
                offer = (p.get("items") or [{}])[0].get("sellers", [{}])[0].get("commertialOffer", {})
                normal = int(offer.get("ListPrice") or 0)
                sale = int(offer.get("Price") or 0)

            if not normal or not sale or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            results.append(Product(
                name=name[:120], url=product_url,
                normal_price=normal, sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name, store="Decathlon",
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

    # Intento 1: intelligent-search (VTEX IO)
    api_url = f"{BASE_URL}/api/intelligent-search/product_search"
    for page_num in range(1, max_pages + 1):
        try:
            resp = requests.get(
                api_url,
                params={"query": "", "sort": "discount:desc", "page": page_num, "count": PAGE_SIZE, "locale": "es-CL"},
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code not in (200, 206):
                if debug:
                    print(f"  [decathlon] intelligent-search: status {resp.status_code}")
                break
            data = resp.json()
            products = data.get("products", [])
            if not products:
                break

            found = _parse_vtex_items(products, category_name, min_discount, seen)
            results.extend(found)
            if debug:
                print(f"  [decathlon] is-p{page_num}: {len(products)} items | desc: {len(found)}")

            total = data.get("recordsFiltered") or data.get("total") or 0
            if page_num * PAGE_SIZE >= total or len(products) < PAGE_SIZE:
                break
            time.sleep(0.5)
        except Exception as e:
            if debug:
                print(f"  [decathlon] is-error: {e}")
            break

    # Intento 2: catalog_system (VTEX clásico)
    if not results:
        api2 = f"{BASE_URL}/api/catalog_system/pub/products/search"
        for page_num in range(max_pages):
            start = page_num * PAGE_SIZE
            try:
                resp = requests.get(
                    api2,
                    params={"_from": start, "_to": start + PAGE_SIZE - 1, "O": "OrderByBestDiscountDESC"},
                    headers=HEADERS,
                    timeout=15,
                )
                if resp.status_code not in (200, 206):
                    break
                products = resp.json()
                if not isinstance(products, list) or not products:
                    break

                found = _parse_vtex_items(products, category_name, min_discount, seen)
                results.extend(found)
                if debug:
                    print(f"  [decathlon] cat-p{page_num+1}: {len(products)} items | desc: {len(found)}")

                if len(products) < PAGE_SIZE:
                    break
                time.sleep(0.5)
            except Exception as e:
                if debug:
                    print(f"  [decathlon] cat-error: {e}")
                break

    return results
