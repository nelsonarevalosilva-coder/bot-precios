"""
Scraper para Sairam Perfumes — Jumpseller HTML scraping.
Página de descuentos: /perfumes-descuento?page=N
Precio normal: div.product-block__price--old
Precio oferta: div.product-block__price--new
"""
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://sairam.cl"
SALE_PATH = "/perfumes-descuento"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
    store: str = "Sairam"


def _clean_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits and 2 < len(digits) < 9 else None


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 10,
    debug: bool = False,
) -> list[Product]:
    results: list[Product] = []

    for page_num in range(1, max_pages + 1):
        page_url = f"{BASE_URL}{SALE_PATH}" + (f"?page={page_num}" if page_num > 1 else "")
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            if debug:
                print(f"  [sairam] Error p{page_num}: {e}")
            break

        products = soup.select("article.product-block-product-feed")
        if not products:
            break

        for item in products:
            try:
                name_tag = item.select_one("h2.product-block__title a.product-block__name")
                if not name_tag:
                    continue
                name = name_tag.get_text(strip=True)
                href = name_tag.get("href", "")
                product_url = href if href.startswith("http") else f"{BASE_URL}{href}"

                # Usar Precio Retail (MSRP fabricante) como precio de referencia
                # da descuentos reales del 30-60% vs el 5-10% del precio "normal" propio
                retail_tag = item.select_one("span.product-block-retail")
                new_tag = item.select_one("div.product-block__price--new")
                if not new_tag:
                    continue

                normal = _clean_price(retail_tag.get_text()) if retail_tag else None
                # Fallback a precio --old si no hay retail
                if not normal:
                    old_tag = item.select_one("div.product-block__price--old")
                    normal = _clean_price(old_tag.get_text()) if old_tag else None

                sale = _clean_price(new_tag.get_text())
                if not normal or not sale or normal <= sale:
                    continue

                discount_pct = (normal - sale) / normal * 100
                if discount_pct < min_discount:
                    continue

                if debug:
                    print(f"  [sairam] {name[:55]} — ${sale:,} (normal ${normal:,}) {discount_pct:.1f}%")

                results.append(Product(
                    name=name[:120],
                    url=product_url,
                    normal_price=normal,
                    sale_price=sale,
                    discount_pct=round(discount_pct, 1),
                    category=category_name,
                    store="Sairam",
                ))
            except Exception:
                continue

        if debug:
            print(f"  [sairam] p{page_num}: {len(products)} productos")

        if len(products) < 40:
            break
        time.sleep(0.5)

    return results
