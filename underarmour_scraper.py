"""
Scraper para Under Armour Chile — Playwright + parseo HTML.
UA bloquea requests con 418; Playwright navega y extrae precios del HTML renderizado.
"""
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

BASE_URL = "https://www.underarmour.com"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Under Armour"
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

    # UA SFCC usa product-tile o grid-tile con data-pid
    tiles = (soup.find_all("div", attrs={"data-pid": True}) or
             soup.find_all(class_=re.compile(r"product-tile|grid-tile|product-card", re.I)))

    for tile in tiles:
        try:
            pid = tile.get("data-pid") or tile.get("data-product-id") or ""
            link_tag = tile.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            uid = pid or product_url
            if uid in seen:
                continue

            name_tag = (tile.find(class_=re.compile(r"product-name|tile-name|pdp-name|product-title", re.I)) or
                        tile.find(["h2", "h3", "h4"], class_=re.compile(r"name|title", re.I)))
            name = name_tag.get_text(strip=True) if name_tag else link_tag.get_text(strip=True)
            if not name:
                continue

            # UA muestra precio tachado (normal) y precio de venta (sale)
            sale_tag = tile.find(class_=re.compile(r"price-sale|sale-price|price--sale|reduced", re.I))
            normal_tag = tile.find(class_=re.compile(r"price-standard|regular-price|price--regular|strike|was-price|original", re.I))

            if not sale_tag:
                # Fallback: buscar dos spans de precio donde el segundo está tachado
                prices = tile.find_all(class_=re.compile(r"price", re.I))
                if len(prices) >= 2:
                    sale_tag, normal_tag = prices[0], prices[1]

            if not sale_tag:
                continue

            sale = _clean_price(sale_tag.get_text())
            normal = _clean_price(normal_tag.get_text()) if normal_tag else None

            if not sale or not normal or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue

            img_tag = tile.find("img")
            image_url = (img_tag.get("src") or img_tag.get("data-src") or "") if img_tag else ""

            seen.add(uid)
            results.append(Product(name=name[:120], url=product_url, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="Under Armour", image_url=image_url))
        except Exception:
            continue
    return results


def scrape_category(url: str, category_name: str, min_discount: float = 40.0,
                    max_pages: int = 3, debug: bool = False) -> list[Product]:
    all_products: list[Product] = []
    seen: set = set()
    page_html: list[str] = []

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
                page.wait_for_timeout(4000)
                # Scroll para cargar lazy-load de productos
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3)")
                page.wait_for_timeout(1500)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6)")
                page.wait_for_timeout(1500)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

                title = page.title()
                html = page.content()
                page_html.append(html)

                if debug:
                    soup = BeautifulSoup(html, "html.parser")
                    tiles = (soup.find_all("div", attrs={"data-pid": True}) or
                             soup.find_all(class_=re.compile(r"product-tile|product-card", re.I)))
                    print(f"  [under armour] {category_name}: {title[:50]} | tiles: {len(tiles)}")

            except PlaywrightTimeout:
                logging.warning("[under armour] Timeout en %s — usando lo capturado", category_name)
                try:
                    page_html.append(page.content())
                except Exception:
                    pass
            except Exception as e:
                logging.error("[under armour] Error: %s", e)

            browser.close()

    except Exception as e:
        logging.error("[under armour] Error general: %s", e)

    for html in page_html:
        found = _parse_html(html, category_name, min_discount, seen)
        if found and debug:
            print(f"  [under armour] {len(found)} productos desde HTML")
        all_products.extend(found)

    if debug:
        print(f"  [under armour] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
