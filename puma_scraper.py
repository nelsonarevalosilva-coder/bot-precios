"""
Scraper para Puma Chile (Magento 2 HTML).
Página de sale: /sale.html?p=N
Precios en .old-price / .special-price.
"""
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://cl.puma.com"
PAGE_SIZE = 36

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
    store: str = "Puma"
    image_url: str = ""


def _clean_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits and 3 < len(digits) < 10 else None


def _parse_product(item, category_name: str, min_discount: float) -> Product | None:
    try:
        name_el = item.select_one(".product-item-name a, .product-item-link, h3.product-name")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            return None

        href = name_el.get("href", "") if name_el else ""
        if not href:
            link = item.select_one("a[href]")
            href = link["href"] if link else ""
        url = href if href.startswith("http") else BASE_URL + href

        img = item.select_one("img.product-image-photo, img[src*='puma.com']")
        image_url = img.get("src", "") if img else ""

        price_box = item.select_one(".price-box")
        normal_price = sale_price = None

        if price_box:
            old_el = price_box.select_one(".old-price .price, .regular-price .price")
            sp_el  = price_box.select_one(".special-price .price")
            if old_el:
                normal_price = _clean_price(old_el.get_text())
            if sp_el:
                sale_price = _clean_price(sp_el.get_text())

        if not normal_price or not sale_price:
            all_prices = [_clean_price(el.get_text()) for el in item.select(".price")]
            all_prices = sorted([p for p in all_prices if p], reverse=True)
            if len(all_prices) >= 2:
                normal_price, sale_price = all_prices[0], all_prices[-1]
            elif len(all_prices) == 1:
                return None

        if not normal_price or not sale_price or sale_price >= normal_price:
            return None

        discount = (normal_price - sale_price) / normal_price * 100
        if discount < min_discount:
            return None

        return Product(
            name=name[:120],
            url=url,
            normal_price=normal_price,
            sale_price=sale_price,
            discount_pct=round(discount, 1),
            category=category_name,
            image_url=image_url,
        )
    except Exception:
        return None


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 30.0,
    max_pages: int = 25,
    debug: bool = False,
) -> list[Product]:
    results: list[Product] = []
    seen: set = set()

    for page in range(1, max_pages + 1):
        page_url = f"{url}?p={page}" if page > 1 else url
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            if debug:
                print(f"  [puma] Error página {page}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("li.product-item, div.product-item")

        if not items:
            break

        found = 0
        for item in items:
            p = _parse_product(item, category_name, min_discount)
            if p and p.url not in seen:
                seen.add(p.url)
                results.append(p)
                found += 1

        if debug:
            print(f"  [puma] página {page}: {len(items)} items, {found} con >={min_discount:.0f}%")

        if len(items) < PAGE_SIZE:
            break

        time.sleep(1)

    return results
