"""
Scraper de Paris Chile usando la API de Constructor.io.
No requiere Playwright — usa requests directamente.
"""

import time
from dataclasses import dataclass

import requests

CNSTRC_KEY = "key_8pjkPsSkEsJHKgxR"
SEARCH_URL = "https://ac.cnstrc.com/search/{query}"
PAGE_SIZE = 50

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.paris.cl/",
    "Origin": "https://www.paris.cl",
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
    store: str = "Paris"
    image_url: str = ""
    seller: str = ""


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

            sale_price = d.get("displayedPrice")
            if not sale_price or not isinstance(sale_price, (int, float)):
                continue
            sale_price = int(sale_price)

            discount_pct = float(d.get("discountPercentage", 0) or 0)
            normal_price = _calc_normal_price(sale_price, discount_pct)

            is_price_error = sale_price < 1000 and normal_price > 5000

            if discount_pct < min_discount and not is_price_error:
                continue

            product_id = d.get("id", url)
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            image_url = d.get("image_url") or d.get("ImageUrl") or ""
            if not image_url:
                img_list = d.get("image_urls") or []
                if img_list:
                    first = img_list[0]
                    image_url = first.get("url", "") if isinstance(first, dict) else str(first)

            sellers_list = d.get("sellers") or []
            seller = sellers_list[0] if sellers_list else "Paris"

            # Intentar obtener categoría real del producto desde la API
            # Constructor.io puede devolver: categories, group_names, department, group
            real_cat = ""
            for cat_field in ("categories", "group_names", "department", "group"):
                val = d.get(cat_field)
                if val:
                    if isinstance(val, list) and val:
                        real_cat = str(val[-1])  # la más específica (último elemento)
                    elif isinstance(val, str):
                        real_cat = val
                    break
            effective_category = real_cat if real_cat else category_name

            products.append(Product(
                name=name[:120],
                url=url,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount_pct, 1),
                category=effective_category,
                store="Paris",
                image_url=image_url,
                seller=seller,
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
    # url contiene el término de búsqueda en el parámetro "query"
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
                    print(f"    [paris] {category_name} p{page_num}: status {resp.status_code}")
                break

            data = resp.json()
            total = data.get("response", {}).get("total_num_results", 0)
            found = _extract_products(data, category_name, min_discount)

            # Deduplicar entre páginas
            unique = [p for p in found if p.url not in seen_ids]
            for p in unique:
                seen_ids.add(p.url)
            all_products.extend(unique)

            if debug:
                print(f"    [paris] {category_name} p{page_num}: total={total} con>={min_discount:.0f}%: {len(unique)}")

            # Verificar si hay más páginas
            if page_num * PAGE_SIZE >= total:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [paris] Error en {category_name} p{page_num}: {e}")
            break

    return all_products
