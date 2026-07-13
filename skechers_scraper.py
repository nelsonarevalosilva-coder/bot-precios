"""
Scraper para Skechers Chile — Playwright + parseo HTML plataforma Andain.
Productos en div.item-producto; precios en <s> (normal) y texto restante <h3> (sale).
URL correcta: /sale (no /catalogo/ que redirige al home)
"""
import logging
import re
from copy import copy
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

try:
    from playwright_stealth import stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

BASE_URL = "https://www.skechers.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Skechers"
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
    for item in soup.find_all("div", class_="item-producto"):
        try:
            link = item.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if product_url in seen:
                continue

            name_tag = item.find("h2")
            name = name_tag.get_text(strip=True) if name_tag else link.get_text(strip=True)
            if not name:
                continue

            img_tag = item.find("img")
            image_url = ""
            if img_tag:
                image_url = img_tag.get("data-src") or img_tag.get("src") or ""

            # Price: <h3><s>$XX.XXX</s> $YY.YYY</h3>
            h3 = item.find("h3")
            if not h3:
                continue
            s_tag = h3.find("s")
            if not s_tag:
                continue
            normal = _clean_price(s_tag.get_text())
            # Sale price = h3 text minus the s tag content
            h3_copy = BeautifulSoup(str(h3), "html.parser").find("h3")
            if h3_copy:
                for s in h3_copy.find_all("s"):
                    s.decompose()
                sale = _clean_price(h3_copy.get_text())
            else:
                sale = None
            if not normal or not sale or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue

            seen.add(product_url)
            results.append(Product(
                name=name[:120], url=product_url, normal_price=normal,
                sale_price=sale, discount_pct=round(disc, 1),
                category=category_name, store="Skechers", image_url=image_url,
            ))
        except Exception:
            continue
    return results


def scrape_category(url: str, category_name: str, min_discount: float = 40.0,
                    max_pages: int = 3, debug: bool = False) -> list[Product]:
    all_products: list[Product] = []
    seen: set = set()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"
            ])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="es-CL",
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
            if _HAS_STEALTH:
                stealth_sync(page)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                # Skechers carga productos vía jQuery AJAX después de domcontentloaded
                page.wait_for_timeout(6000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

                html = page.content()
                found = _parse_html(html, category_name, min_discount, seen)
                all_products.extend(found)

                if debug:
                    print(f"  [skechers] {category_name}: {page.title()[:40]} | {len(found)} productos")

            except PlaywrightTimeout:
                logging.warning("[skechers] Timeout en %s", category_name)
                try:
                    html = page.content()
                    found = _parse_html(html, category_name, min_discount, seen)
                    all_products.extend(found)
                except Exception:
                    pass
            except Exception as e:
                logging.error("[skechers] Error: %s", e)

            browser.close()

    except Exception as e:
        logging.error("[skechers] Error general: %s", e)

    logging.info("[skechers] %s: %d productos >= %.0f%%", category_name, len(all_products), min_discount)
    if debug:
        print(f"  [skechers] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
