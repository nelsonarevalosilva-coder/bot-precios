"""
Scraper de PC Factory Chile usando su API REST propia.
Sin Playwright — requests directo.
"""
import time
from dataclasses import dataclass

import requests

API_URL = "https://api.pcfactory.cl/pcfactory-services-catalogo/v1/catalogo/productos"
PRODUCT_BASE = "https://www.pcfactory.cl/producto"
PAGE_SIZE = 24

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
    "Referer": "https://www.pcfactory.cl/",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "PC Factory"


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 70.0,
    max_pages: int = 3,
    debug: bool = False,
) -> list[Product]:
    query = url.split("q=")[-1].split("&")[0] if "q=" in url else category_name
    all_products: list[Product] = []
    seen_ids: set = set()

    for page_num in range(1, max_pages + 1):
        try:
            params = {"search": query, "pagina": page_num, "cantidad": PAGE_SIZE}
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                if debug:
                    print(f"    [pcfactory] {category_name} p{page_num}: status {resp.status_code}")
                break

            data = resp.json()
            items = data if isinstance(data, list) else []
            if not items:
                break

            pageable = items[0].get("pageable") if items else None

            for item in items:
                try:
                    precio = item.get("precio", {})
                    sale_price = int(precio.get("efectivo") or precio.get("normal") or 0)
                    normal_price = int(precio.get("referencia") or precio.get("normal") or 0)

                    if not sale_price:
                        continue
                    if not normal_price or normal_price <= sale_price:
                        normal_price = sale_price

                    discount_pct = 0.0
                    if normal_price > sale_price:
                        discount_pct = (normal_price - sale_price) / normal_price * 100

                    is_price_error = sale_price < 1000 and normal_price > 5000
                    if discount_pct < min_discount and not is_price_error:
                        continue

                    slug = item.get("slug", "")
                    product_id = str(item.get("id", slug))
                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    name = item.get("nombre", "") or item.get("name", "")
                    product_url = f"{PRODUCT_BASE}/{slug}" if slug else ""
                    if not product_url:
                        continue

                    all_products.append(Product(
                        name=name[:120],
                        url=product_url,
                        normal_price=normal_price,
                        sale_price=sale_price,
                        discount_pct=round(discount_pct, 1),
                        category=category_name,
                        store="PC Factory",
                    ))
                except Exception:
                    continue

            if debug:
                print(f"    [pcfactory] {category_name} p{page_num}: {len(items)} items")

            if pageable:
                if page_num >= pageable.get("totalPages", 1):
                    break
            elif len(items) < PAGE_SIZE:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [pcfactory] Error: {e}")
            break

    return all_products
