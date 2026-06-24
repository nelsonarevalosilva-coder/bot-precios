"""
Scraper para New Balance Chile — Playwright con intercepción de red.
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

BASE_URL = "https://www.newbalancechile.cl"


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


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_shopify_json(data, category_name, min_discount, seen):
    results = []
    for p in (data.get("products") or []):
        try:
            handle = p.get("handle", "")
            if not handle or handle in seen:
                continue
            name = p.get("title", "")
            product_url = f"{BASE_URL}/products/{handle}"
            image_url = (p.get("images") or [{}])[0].get("src", "")
            best_sale = best_normal = 0
            best_disc = 0.0
            for v in p.get("variants", []):
                price = int(float(v.get("price") or 0))
                compare = v.get("compare_at_price")
                if not compare:
                    continue
                compare = int(float(compare))
                if compare <= price or price <= 0:
                    continue
                disc = (compare - price) / compare * 100
                if disc > best_disc:
                    best_disc, best_sale, best_normal = disc, price, compare
            if not best_sale or best_disc < min_discount:
                continue
            seen.add(handle)
            results.append(Product(name=name[:120], url=product_url, normal_price=best_normal,
                                   sale_price=best_sale, discount_pct=round(best_disc, 1),
                                   category=category_name, store="New Balance", image_url=image_url))
        except Exception:
            continue
    return results


def _parse_html(html, category_name, min_discount, seen):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.find_all(class_=re.compile(r"product|card", re.I)):
        try:
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if url in seen:
                continue
            name_tag = card.find(class_=re.compile(r"title|name", re.I))
            name = name_tag.get_text(strip=True) if name_tag else link.get_text(strip=True)
            sale_tag = card.find(class_=re.compile(r"sale|price", re.I))
            normal_tag = card.find(class_=re.compile(r"compare|original|regular", re.I))
            if not sale_tag:
                continue
            sale = _clean_price(sale_tag.get_text())
            normal = _clean_price(normal_tag.get_text()) if normal_tag else None
            if not sale or not normal or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            seen.add(url)
            results.append(Product(name=name[:120], url=url, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="New Balance"))
        except Exception:
            continue
    return results


def scrape_category(url, category_name, min_discount=40.0, max_pages=3, debug=False):
    all_products, seen, api_responses, page_html = [], set(), [], []

    def handle_response(resp):
        try:
            if resp.status == 200 and "json" in resp.headers.get("content-type", "") and "newbalancechile.cl" in resp.url:
                body = resp.json()
                if isinstance(body, dict) and "products" in body:
                    api_responses.append(body)
        except Exception:
            pass

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", locale="es-CL", viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            if _HAS_STEALTH:
                stealth_sync(page)
            page.on("response", handle_response)
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(3000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
                page.wait_for_timeout(2000)
                page_html.append(page.content())
                if debug:
                    print(f"  [new balance] {page.title()[:60]}")
            except PlaywrightTimeout:
                logging.warning("[new balance] Timeout")
                try:
                    page_html.append(page.content())
                except Exception:
                    pass
            except Exception as e:
                logging.error("[new balance] Error: %s", e)
            browser.close()
    except Exception as e:
        logging.error("[new balance] Error general: %s", e)

    for data in api_responses:
        all_products.extend(_parse_shopify_json(data, category_name, min_discount, seen))
    if not all_products:
        for html in page_html:
            all_products.extend(_parse_html(html, category_name, min_discount, seen))
    return all_products
