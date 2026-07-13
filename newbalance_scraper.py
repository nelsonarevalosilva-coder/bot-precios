"""
Scraper para New Balance Chile — Magento, requests + BeautifulSoup.
Parsea data-price-type="oldPrice"/"finalPrice" del HTML de sale.
"""
import logging
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://newbalance.cl"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
    store: str = "New Balance"
    image_url: str = ""


def _parse_page(html: str, category_name: str, min_discount: float, seen: set) -> list[Product]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.find_all("li", class_="product-item"):
        try:
            link = item.find("a", href=True)
            if not link:
                continue
            product_url = link["href"]
            if product_url in seen:
                continue

            name_tag = item.find(class_=re.compile(r"product-item-name|product-name"))
            name = name_tag.get_text(strip=True) if name_tag else link.get("title", "")
            if not name:
                continue

            img_tag = item.find("img")
            image_url = (img_tag.get("data-src") or img_tag.get("src") or "") if img_tag else ""

            old_span = item.find("span", attrs={"data-price-type": "oldPrice"})
            final_span = item.find("span", attrs={"data-price-type": "finalPrice"})
            if not old_span or not final_span:
                continue
            normal = int(float(old_span.get("data-price-amount", 0)))
            sale = int(float(final_span.get("data-price-amount", 0)))
            if not normal or not sale or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue

            seen.add(product_url)
            results.append(Product(
                name=name[:120], url=product_url, normal_price=normal,
                sale_price=sale, discount_pct=round(disc, 1),
                category=category_name, store="New Balance", image_url=image_url,
            ))
        except Exception:
            continue
    return results


def scrape_category(url: str, category_name: str, min_discount: float = 40.0,
                    max_pages: int = 5, debug: bool = False) -> list[Product]:
    all_products: list[Product] = []
    seen: set = set()

    # Normalize URL to canonical (no www)
    base_url = url.replace("https://www.newbalance.cl", BASE_URL)

    session = requests.Session()
    session.headers.update(HEADERS)

    for page in range(1, max_pages + 1):
        page_url = base_url if page == 1 else f"{base_url}?p={page}"
        try:
            resp = session.get(page_url, timeout=20)
            if resp.status_code != 200:
                if debug:
                    print(f"  [new balance] p{page}: status {resp.status_code}")
                break
            found = _parse_page(resp.text, category_name, min_discount, seen)
            all_products.extend(found)
            if debug:
                print(f"  [new balance] {category_name} p{page}: {len(found)} productos con descuento")
            if not found:
                break
            time.sleep(0.3)
        except Exception as e:
            logging.error("[new balance] Error p%d: %s", page, e)
            break

    logging.info("[new balance] %s: %d productos >= %.0f%%", category_name, len(all_products), min_discount)
    if debug:
        print(f"  [new balance] Total {category_name}: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
