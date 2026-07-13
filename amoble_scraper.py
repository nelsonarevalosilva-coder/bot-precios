"""
Scraper para Amoble.cl — plataforma Magento, HTML BeautifulSoup.
La página de ofertas y categorías expone precio normal (oldPrice) y precio oferta (finalPrice)
en atributos data-price-amount / data-price-type del price-box.
"""
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
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
    store: str = "Amoble"
    image_url: str = ""


def _parse_price(amount_str: str) -> int:
    digits = re.sub(r"[^\d]", "", amount_str)
    return int(digits) if digits else 0


def _extract_products(soup: BeautifulSoup, category_name: str, min_discount: float) -> list[Product]:
    results = []
    for item in soup.select("li.item.product"):
        price_box = item.find(class_="price-box")
        if not price_box:
            continue

        data_amounts = {
            el.get("data-price-type"): _parse_price(el.get("data-price-amount", ""))
            for el in price_box.find_all(attrs={"data-price-amount": True})
        }
        final_price = data_amounts.get("finalPrice")
        old_price = data_amounts.get("oldPrice")

        if not final_price or not old_price or old_price <= final_price:
            continue

        discount_pct = (old_price - final_price) / old_price * 100
        if discount_pct < min_discount:
            continue

        name_el = item.find("strong", class_="product-item-name")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if not name:
            continue

        link_el = item.find("a", class_="product-item-link")
        url = link_el.get("href", "") if link_el else ""
        if not url:
            continue

        img_tag = item.find("img", class_="product-image-photo") or item.find("img")
        image_url = ""
        if img_tag:
            image_url = img_tag.get("data-src") or img_tag.get("src") or ""

        results.append(Product(
            name=name,
            url=url,
            normal_price=old_price,
            sale_price=final_price,
            discount_pct=discount_pct,
            category=category_name,
            store="Amoble",
            image_url=image_url,
        ))

    seen = set()
    deduped = []
    for p in results:
        if p.url not in seen:
            seen.add(p.url)
            deduped.append(p)
    return deduped


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 3,
    debug: bool = False,
) -> list[Product]:
    results = []
    for page in range(1, max_pages + 1):
        page_url = url if page == 1 else f"{url}?p={page}"
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            if debug:
                print(f"  [amoble] Error al obtener {page_url}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        page_results = _extract_products(soup, category_name, min_discount)

        if debug:
            total = len(soup.select("li.item.product"))
            print(f"  [amoble] pág {page}: {total} productos total, {len(page_results)} con >= {min_discount:.0f}%")

        results.extend(page_results)

        if len(soup.select("li.item.product")) < 48:
            break

    seen = set()
    deduped = []
    for p in results:
        if p.url not in seen:
            seen.add(p.url)
            deduped.append(p)
    return deduped
