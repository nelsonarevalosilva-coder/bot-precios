"""
Scraper para Under Armour Chile — Salesforce Commerce Cloud (SFCC).
Requiere IP chilena. Retorna [] si bloqueado por geo-restricción.
"""
import logging
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.underarmour.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,*/*",
    "Accept-Language": "es-CL,es;q=0.9",
    "Referer": "https://www.underarmour.com/es-cl/",
}

PAGE_SIZE = 48


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Under Armour"


def _clean_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", str(text or ""))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_sfcc_html(html: str, category_name: str, min_discount: float, seen: set) -> list[Product]:
    """Parsea la respuesta HTML paginada de SFCC."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for tile in soup.find_all("div", class_=re.compile(r"product-tile|grid-tile")):
        try:
            name_tag = tile.find(["h2", "a"], class_=re.compile(r"product-name|tile-name"))
            if not name_tag:
                continue
            name = name_tag.get_text(strip=True)

            link_tag = tile.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if product_url in seen:
                continue

            sale_tag = tile.find(class_=re.compile(r"sale-price|price-sale"))
            normal_tag = tile.find(class_=re.compile(r"regular-price|price-standard|strike"))
            if not sale_tag:
                continue

            sale = _clean_price(sale_tag.get_text())
            normal = _clean_price(normal_tag.get_text()) if normal_tag else None

            if not sale or not normal or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            seen.add(product_url)
            results.append(Product(
                name=name[:120], url=product_url,
                normal_price=normal, sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name, store="Under Armour",
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

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        session.get(f"{BASE_URL}/es-cl/", timeout=12, allow_redirects=True)
    except Exception:
        pass

    for page_num in range(max_pages):
        start = page_num * PAGE_SIZE
        try:
            resp = session.get(
                url,
                params={"start": start, "sz": PAGE_SIZE, "format": "ajax"},
                timeout=15,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                if debug:
                    print(f"  [under armour] {category_name} status {resp.status_code}")
                break

            found = _parse_sfcc_html(resp.text, category_name, min_discount, seen)
            results.extend(found)
            if debug:
                print(f"  [under armour] {category_name} p{page_num+1}: {len(found)} productos")

            if len(found) < 5:
                break
            time.sleep(1)

        except Exception as e:
            logging.error("[under armour] Error en %s p%d: %s", category_name, page_num + 1, e)
            break

    return results
