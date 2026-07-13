"""
Scraper para Decathlon Chile — Playwright + parseo HTML PrestaShop/Oneshop.
URLs de formato: /NUMERO-ofertas-CATEGORIA
Clases de precio: price_amount (sale) y price_barred-amount (normal)
"""
import json
import logging
import re
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

try:
    from playwright_stealth import stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

BASE_URL = "https://www.decathlon.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Decathlon"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_html(html: str, category_name: str, min_discount: float, seen: set) -> list[Product]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for article in soup.find_all("article", class_="product-card"):
        try:
            sku = article.get("data-sku", "")
            link_tag = article.find("a", class_=re.compile(r"js-product-card-link"))
            if not link_tag:
                continue
            product_url = link_tag.get("href", "")
            if not product_url or product_url in seen:
                continue
            uid = sku or product_url
            if uid in seen:
                continue

            img_tag = article.find("img")
            name = img_tag.get("alt", "").strip() if img_tag else ""
            image_url = img_tag.get("src", "") if img_tag else ""
            if not name:
                continue

            sale_tag = article.find(class_="price_amount")
            normal_tag = article.find(class_="price_barred-amount")
            if not sale_tag or not normal_tag:
                continue
            sale = _clean_price(sale_tag.get_text())
            normal = _clean_price(normal_tag.get_text())
            if not sale or not normal or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue

            seen.add(uid)
            results.append(Product(
                name=name[:120], url=product_url, normal_price=normal,
                sale_price=sale, discount_pct=round(disc, 1),
                category=category_name, store="Decathlon", image_url=image_url,
            ))
        except Exception:
            continue
    return results


def scrape_category(url: str, category_name: str, min_discount: float = 40.0,
                    max_pages: int = 5, debug: bool = False) -> list[Product]:
    all_products: list[Product] = []
    seen: set = set()
    page_path = url.replace(BASE_URL, "")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"
            ])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="es-CL",
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={"Accept-Language": "es-CL,es;q=0.9"},
            )
            page = context.new_page()
            if _HAS_STEALTH:
                stealth_sync(page)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)

                title = page.title()
                if debug:
                    print(f"  [decathlon] p1: {title[:60]}")

                # Parse page 1
                html1 = page.content()
                found = _parse_html(html1, category_name, min_discount, seen)
                all_products.extend(found)
                if debug:
                    print(f"  [decathlon] p1: {len(found)} productos con descuento")

                # Pages 2+ via in-browser fetch (no navigation needed)
                for pg in range(2, max_pages + 1):
                    ep = f"{page_path}?page={pg}"
                    try:
                        html_pg = page.evaluate(f"""async () => {{
                            const r = await fetch('{ep}', {{credentials:'include'}});
                            if (!r.ok) return '';
                            return r.text();
                        }}""")
                        if not html_pg:
                            break
                        found_pg = _parse_html(html_pg, category_name, min_discount, seen)
                        if not found_pg and pg > 2:
                            break
                        all_products.extend(found_pg)
                        if debug:
                            print(f"  [decathlon] p{pg}: {len(found_pg)} productos con descuento")
                    except Exception as e:
                        if debug:
                            print(f"  [decathlon] p{pg} error: {e}")
                        break

            except PlaywrightTimeout:
                logging.warning("[decathlon] Timeout en %s — usando lo capturado", category_name)
            except Exception as e:
                logging.error("[decathlon] Error: %s", e)

            browser.close()

    except Exception as e:
        logging.error("[decathlon] Error general: %s", e)

    logging.info("[decathlon] %s: %d productos >= %.0f%%", category_name, len(all_products), min_discount)
    if debug:
        print(f"  [decathlon] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
