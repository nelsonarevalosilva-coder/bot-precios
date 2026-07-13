"""
Scraper de Jumbo Chile usando la API de Constructor.io (Cencosud).
Soporta dos modos:
  - browse: URL con group_id=N → endpoint /browse/group_id/N, sort best-discount
  - search: URL con query=X   → endpoint /search/X
"""
import re
import time
from dataclasses import dataclass

import requests

CNSTRC_KEY = "key_JopvNXKS61kwGkBe"
SEARCH_URL = "https://ac.cnstrc.com/search/{query}"
BROWSE_URL = "https://ac.cnstrc.com/browse/group_id/{group_id}"
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
    image_url: str = ""
    seller: str = ""


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

            full_url = d.get("url", "")
            detail_url = d.get("DetailUrl", "")
            if full_url and full_url.startswith("http"):
                url = full_url
            elif detail_url:
                url = f"https://www.jumbo.cl{detail_url}" if not detail_url.startswith("http") else detail_url
            else:
                continue

            sale_price = d.get("sellingPrice") or d.get("price")
            if not sale_price or not isinstance(sale_price, (int, float)):
                continue
            sale_price = int(sale_price)

            normal_price = int(d.get("originalPrice") or d.get("listPrice") or 0)
            if not normal_price or normal_price <= sale_price:
                normal_price = sale_price

            # Corregir precio cuando el producto se vende por fracción de kg
            # (MeasurementUnit=kg, UnitMultiplier<1 → sale_price es por fracción, normal_price es por kg)
            unit_mult = d.get("UnitMultiplier")
            if d.get("MeasurementUnit") == "kg" and unit_mult and 0 < float(unit_mult) < 1.0:
                proportional_normal = normal_price * float(unit_mult)
                discount_pct = max(0.0, (proportional_normal - sale_price) / proportional_normal * 100) if proportional_normal > 0 else 0.0
                normal_price = int(proportional_normal)  # precio para la misma fracción de kg
            else:
                discount_pct = 0.0
                if normal_price > sale_price:
                    discount_pct = (normal_price - sale_price) / normal_price * 100

                # Falso descuento por unidades: precio por 100g vs precio por kg (ratio ~10x)
                if normal_price > 0 and abs(normal_price / sale_price - 10) < 0.5:
                    continue

            is_price_error = sale_price < 1000 and normal_price > 5000

            if discount_pct < min_discount and not is_price_error:
                continue

            product_id = d.get("id", url)
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            image_url = (
                d.get("image_url") or d.get("ImageUrl") or
                d.get("thumbnail_url") or d.get("ThumbnailUrl") or ""
            )
            if not image_url:
                img_list = d.get("image_urls") or []
                if img_list:
                    first = img_list[0]
                    image_url = first.get("url", "") if isinstance(first, dict) else str(first)

            products.append(Product(
                name=name[:120],
                url=url,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Jumbo",
                image_url=image_url,
                seller="Jumbo",
            ))
        except Exception:
            continue

    return products


def _scrape_browse(
    group_id: str,
    category_name: str,
    min_discount: float,
    max_pages: int,
    debug: bool,
) -> list[Product]:
    all_products: list[Product] = []
    seen_ids: set = set()

    for page_num in range(1, max_pages + 1):
        try:
            params = {
                "key": CNSTRC_KEY,
                "page": page_num,
                "num_results_per_page": PAGE_SIZE,
                "section": "Products",
                "sort_by": "best-discount",
                "sort_order": "descending",
            }
            resp = requests.get(
                BROWSE_URL.format(group_id=group_id),
                params=params,
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                if debug:
                    print(f"    [jumbo browse] {category_name} p{page_num}: status {resp.status_code}")
                break

            data = resp.json()
            total = data.get("response", {}).get("total_num_results", 0)
            found = _extract_products(data, category_name, min_discount)

            unique = [p for p in found if p.url not in seen_ids]
            for p in unique:
                seen_ids.add(p.url)
            all_products.extend(unique)

            if debug:
                print(f"    [jumbo browse] {category_name} p{page_num}: total={total} >={min_discount:.0f}%: {len(unique)}")

            # Con best-discount sort, si la página no devolvió descuentos suficientes, parar
            if not found or page_num * PAGE_SIZE >= total:
                break

            time.sleep(0.5)

        except Exception as e:
            if debug:
                print(f"    [jumbo browse] Error en {category_name} p{page_num}: {e}")
            break

    return all_products


def _scrape_search(
    query: str,
    category_name: str,
    min_discount: float,
    max_pages: int,
    debug: bool,
) -> list[Product]:
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
                    print(f"    [jumbo search] {category_name} p{page_num}: status {resp.status_code}")
                break

            data = resp.json()
            total = data.get("response", {}).get("total_num_results", 0)
            found = _extract_products(data, category_name, min_discount)

            unique = [p for p in found if p.url not in seen_ids]
            for p in unique:
                seen_ids.add(p.url)
            all_products.extend(unique)

            if debug:
                print(f"    [jumbo search] {category_name} p{page_num}: total={total} >={min_discount:.0f}%: {len(unique)}")

            if page_num * PAGE_SIZE >= total:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [jumbo search] Error en {category_name} p{page_num}: {e}")
            break

    return all_products


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 20.0,
    max_pages: int = 2,
    debug: bool = False,
) -> list[Product]:
    m = re.search(r'group_id=(\d+)', url)
    if m:
        return _scrape_browse(m.group(1), category_name, min_discount, max_pages, debug)
    query = url.split("query=")[-1] if "query=" in url else category_name
    return _scrape_search(query, category_name, min_discount, max_pages, debug)
