"""
Scraper para Booz.cl — HTML SSR + BeautifulSoup.
Cada "catálogo" de Booz es una colección curada con productos en descuento.
URL: https://www.booz.cl/catalogo/{slug}
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
BASE_URL = "https://www.booz.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Booz"


def _parse_price(text: str) -> int:
    """Convierte '$14.990' → 14990."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def _extract_products(soup: BeautifulSoup, category_name: str, min_discount: float) -> list[Product]:
    results = []
    links = [a for a in soup.find_all("a", href=True) if "/productos/" in a.get("href", "")]

    for a in links:
        href = a.get("href", "")
        product_url = f"{BASE_URL}{href}"

        img = a.find("img")
        name = img.get("alt", "").strip() if img else ""
        if not name:
            continue

        # Walk up to find the card container (has both prices)
        card = a
        for _ in range(10):
            card = card.parent
            if not card:
                break
            if card.find("span", class_=lambda c: c and "line-through" in (c if isinstance(c, str) else " ".join(c))):
                break

        if not card:
            continue

        # Sale price: first span with text-red-700 class
        sale_span = card.find("span", class_=lambda c: c and "text-red-700" in (c if isinstance(c, str) else " ".join(c)))
        # Normal price: span with line-through class
        normal_span = card.find("span", class_=lambda c: c and "line-through" in (c if isinstance(c, str) else " ".join(c)))

        if not sale_span or not normal_span:
            continue

        sale_price = _parse_price(sale_span.get_text())
        normal_price = _parse_price(normal_span.get_text())

        if not sale_price or not normal_price or sale_price >= normal_price:
            continue

        discount_pct = (normal_price - sale_price) / normal_price * 100
        if discount_pct < min_discount:
            continue

        results.append(Product(
            name=name,
            url=product_url,
            normal_price=normal_price,
            sale_price=sale_price,
            discount_pct=discount_pct,
            category=category_name,
            store="Booz",
        ))

    # Deduplicate by URL
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
    min_discount: float = 30.0,
    max_pages: int = 1,
    debug: bool = False,
) -> list[Product]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        if debug:
            print(f"  [booz] Error al obtener {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = _extract_products(soup, category_name, min_discount)

    if debug:
        all_links = [a for a in soup.find_all("a", href=True) if "/productos/" in a.get("href", "")]
        print(f"  [booz] {url.split('/')[-1]}: {len(all_links)} productos total, {len(results)} con >= {min_discount:.0f}%")

    return results
