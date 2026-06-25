"""
Scraper para Adidas Chile — Playwright + __NEXT_DATA__ + fetch in-browser.
Adidas usa Akamai Bot Manager y Next.js.
"""
import json
import logging
import re
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

try:
    from playwright_stealth import stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

BASE_URL = "https://www.adidas.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Adidas"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 3 <= len(digits) <= 8 else None


def _parse_items(items, category_name, min_discount, seen):
    results = []
    for item in (items or []):
        try:
            model_id = item.get("modelId") or item.get("id") or item.get("productId") or ""
            name = (item.get("displayName") or item.get("name") or item.get("title") or "").strip()
            if not name or not model_id:
                continue
            if model_id in seen:
                continue
            product_url = f"{BASE_URL}/{model_id}.html"
            pricing = item.get("pricing") or item.get("price") or {}
            sale = _clean_price(pricing.get("currentPrice") or pricing.get("sale") or pricing.get("salePrice") or item.get("salePrice"))
            normal = _clean_price(pricing.get("standardPrice") or pricing.get("original") or pricing.get("originalPrice") or item.get("originalPrice"))
            image_url = ""
            imgs = item.get("image") or item.get("images") or {}
            if isinstance(imgs, dict):
                image_url = imgs.get("src") or imgs.get("url") or ""
            elif isinstance(imgs, list) and imgs:
                image_url = imgs[0].get("src") or imgs[0].get("url") or ""
            if not sale or not normal or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            seen.add(model_id)
            results.append(Product(name=name[:120], url=product_url, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="Adidas", image_url=image_url))
        except Exception:
            continue
    return results


def _extract_from_data(data, category_name, min_discount, seen):
    if not isinstance(data, dict):
        return []
    items = (data.get("raw", {}).get("itemList", {}).get("items") or
             data.get("itemList", {}).get("items") or
             data.get("products") or
             data.get("items") or [])
    if not items:
        for v in data.values():
            if isinstance(v, dict):
                items = _extract_from_data(v, category_name, min_discount, seen)
                if items:
                    return items
    return _parse_items(items, category_name, min_discount, seen)


def scrape_category(url, category_name, min_discount=25.0, max_pages=3, debug=False):
    all_products, seen = [], set()

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
                # Warmup en home
                try:
                    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                except Exception:
                    pass

                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)

                if debug:
                    title = page.title()
                    body_text = page.evaluate("() => document.body ? document.body.innerText.slice(0,200) : ''")
                    has_next = page.evaluate("() => !!window.__NEXT_DATA__")
                    print(f"  [adidas] title={title[:50]} | __NEXT_DATA__={has_next}")
                    print(f"  [adidas] body: {body_text[:150]}")

                # 1. Intentar __NEXT_DATA__ (Next.js)
                try:
                    next_json = page.evaluate("() => JSON.stringify(window.__NEXT_DATA__ || null)")
                    if next_json and next_json != "null":
                        next_data = json.loads(next_json)
                        found = _extract_from_data(next_data, category_name, min_discount, seen)
                        if debug:
                            print(f"  [adidas] __NEXT_DATA__: {len(found)} productos")
                        all_products.extend(found)
                except Exception as e:
                    if debug:
                        print(f"  [adidas] __NEXT_DATA__ error: {e}")

                # 2. Fetch in-browser al content-engine API
                if not all_products:
                    path = url.replace(BASE_URL, "")
                    endpoints = [
                        f"/api/plp/content-engine?query={path.strip('/')}&start=0&count=48&sort=discount-desc",
                        f"/es-CL/plp-app/api{path}?start=0&count=48&sort=discount-desc",
                    ]
                    for ep in endpoints:
                        try:
                            api_json = page.evaluate(f"""async () => {{
                                const r = await fetch('{ep}', {{credentials:'include', headers:{{'Accept':'application/json'}}}});
                                if (!r.ok) return JSON.stringify({{error: r.status}});
                                return r.text();
                            }}""")
                            if debug:
                                print(f"  [adidas] fetch {ep[:70]}: {str(api_json)[:80]}")
                            if not api_json or '"error"' in api_json[:20]:
                                continue
                            data = json.loads(api_json)
                            found = _extract_from_data(data, category_name, min_discount, seen)
                            if found:
                                if debug:
                                    print(f"  [adidas] {len(found)} productos desde API")
                                all_products.extend(found)
                                break
                        except Exception as e:
                            if debug:
                                print(f"  [adidas] fetch error: {e}")

            except PlaywrightTimeout:
                logging.warning("[adidas] Timeout")
            except Exception as e:
                logging.error("[adidas] Error: %s", e)

            browser.close()
    except Exception as e:
        logging.error("[adidas] Error general: %s", e)

    if debug:
        print(f"  [adidas] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
