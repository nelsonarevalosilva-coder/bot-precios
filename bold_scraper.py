"""
Scraper de Bold Chile usando su API SAP Commerce Cloud (Hybris).
Sin Playwright — requests directo.
"""
import time
from dataclasses import dataclass

import requests

API_URL = "https://api-prd.ynk.cl/rest/v2/boldb2cstore/products/search"
PAGE_SIZE = 48

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
    "Referer": "https://www.bold.cl/",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Bold"
    image_url: str = ""


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 3,
    debug: bool = False,
) -> list[Product]:
    category = url.split("category=")[-1].split("&")[0] if "category=" in url else "sale-bold"
    all_products: list[Product] = []
    seen_ids: set = set()

    for page_num in range(max_pages):
        try:
            params = {
                "query": f":relevance:allCategories:{category}",
                "pageSize": PAGE_SIZE,
                "currentPage": page_num,
                "fields": "FULL",
            }
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                if debug:
                    print(f"    [bold] {category_name} p{page_num+1}: status {resp.status_code}")
                break

            data = resp.json()
            products = data.get("products", [])
            if not products:
                break

            for item in products:
                try:
                    product_id = item.get("code", "")
                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    name = item.get("name", "")
                    if not name:
                        continue

                    url_path = item.get("url", "") or f"/p/{product_id}"
                    product_url = "https://www.bold.cl" + url_path if not url_path.startswith("http") else url_path

                    sale_price = int(item.get("price", {}).get("value", 0) or 0)
                    normal_price = int(item.get("regularPrice", {}).get("value", 0) or 0)

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

                    all_products.append(Product(
                        name=name[:120],
                        url=product_url,
                        normal_price=normal_price,
                        sale_price=sale_price,
                        discount_pct=round(discount_pct, 1),
                        category=category_name,
                        store="Bold",
                    ))
                except Exception:
                    continue

            if debug:
                print(f"    [bold] {category_name} p{page_num+1}: {len(products)} items")

            total_pages = data.get("pagination", {}).get("totalPages", 1)
            if page_num + 1 >= total_pages:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [bold] Error: {e}")
            break

    return all_products
