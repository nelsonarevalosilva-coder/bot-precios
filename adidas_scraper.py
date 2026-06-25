"""
Scraper para Adidas Chile.
Usa headless=False para evadir Akamai Bot Manager (detecta headless).
En servidor Windows funciona aunque no haya sesión activa de escritorio.
"""
import json
import logging
import re
import time
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
            model_id = (item.get("modelId") or item.get("id") or
                        item.get("productId") or item.get("sku") or "")
            name = (item.get("displayName") or item.get("name") or
                    item.get("title") or "").strip()
            if not name or not model_id or model_id in seen:
                continue
            product_url = f"{BASE_URL}/{model_id}.html"
            pricing = item.get("pricing") or item.get("price") or {}
            sale = _clean_price(
                pricing.get("currentPrice") or pricing.get("sale") or
                pricing.get("salePrice") or item.get("salePrice") or
                item.get("currentPrice")
            )
            normal = _clean_price(
                pricing.get("standardPrice") or pricing.get("original") or
                pricing.get("originalPrice") or item.get("originalPrice") or
                item.get("standardPrice")
            )
            imgs = item.get("image") or item.get("images") or {}
            if isinstance(imgs, dict):
                image_url = imgs.get("src") or imgs.get("url") or ""
            elif isinstance(imgs, list) and imgs:
                image_url = imgs[0].get("src", "") if isinstance(imgs[0], dict) else ""
            else:
                image_url = ""
            if not sale or not normal or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            seen.add(model_id)
            results.append(Product(
                name=name[:120], url=product_url, normal_price=normal,
                sale_price=sale, discount_pct=round(disc, 1),
                category=category_name, store="Adidas", image_url=image_url,
            ))
        except Exception:
            continue
    return results


def _deep_extract(data, category_name, min_discount, seen):
    if not isinstance(data, dict):
        return []
    items = (
        data.get("raw", {}).get("itemList", {}).get("items") or
        data.get("itemList", {}).get("items") or
        data.get("products") or data.get("items") or []
    )
    if items:
        return _parse_items(items, category_name, min_discount, seen)
    for v in data.values():
        if isinstance(v, dict):
            r = _deep_extract(v, category_name, min_discount, seen)
            if r:
                return r
    return []


def scrape_category(url, category_name, min_discount=25.0, max_pages=3, debug=False):
    logging.info("[adidas] Iniciando: %s", category_name)
    all_products, seen = [], set()

    # headless=False: Akamai no detecta el browser como bot
    for attempt in range(2):
        headless = (attempt == 1)  # intento 0: visible, intento 1: headless fallback
        try:
            with sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch(
                        headless=headless,
                        args=[
                            "--no-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--start-maximized",
                        ],
                    )
                except Exception as e:
                    logging.error("[adidas] No se pudo lanzar browser (headless=%s): %s", headless, e)
                    continue

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
                    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)

                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(5000)

                    title = page.title()
                    body_snippet = page.inner_text("body")[:200].replace("\n", " ")
                    blocked = any(w in body_snippet for w in [
                        "UNABLE TO GIVE YOU ACCESS", "Access Denied",
                        "Reference #", "security issue",
                    ])
                    if debug:
                        print(f"  [adidas] headless={headless} | title={title[:50]} | blocked={blocked}")

                    if blocked:
                        browser.close()
                        continue  # intenta con headless=True

                    # Scroll para cargar productos
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
                    page.wait_for_timeout(2000)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(3000)

                    # 1. __NEXT_DATA__
                    try:
                        nxt = page.evaluate("() => JSON.stringify(window.__NEXT_DATA__ || null)")
                        if nxt and nxt != "null":
                            found = _deep_extract(json.loads(nxt), category_name, min_discount, seen)
                            if debug:
                                print(f"  [adidas] __NEXT_DATA__: {len(found)} productos")
                            all_products.extend(found)
                    except Exception:
                        pass

                    # 2. In-browser fetch a content-engine
                    if not all_products:
                        path = url.replace(BASE_URL, "").strip("/")
                        for ep in [
                            f"/api/plp/content-engine?query={path}&start=0&count=48&sort=discount-desc",
                            f"/es-CL/plp-app/api/products?path=/{path}&start=0&count=48",
                        ]:
                            try:
                                result = page.evaluate(f"""async () => {{
                                    const r = await fetch('{ep}', {{credentials:'include', headers:{{'Accept':'application/json'}}}});
                                    return r.ok ? await r.text() : JSON.stringify({{error:r.status}});
                                }}""")
                                if result and '"error"' not in result[:20]:
                                    found = _deep_extract(json.loads(result), category_name, min_discount, seen)
                                    if debug:
                                        print(f"  [adidas] fetch {ep[:50]}: {len(found)} productos")
                                    all_products.extend(found)
                                    if all_products:
                                        break
                            except Exception:
                                pass

                except PlaywrightTimeout:
                    logging.warning("[adidas] Timeout en %s", category_name)
                except Exception as e:
                    logging.error("[adidas] Error navegando: %s", e)
                finally:
                    try:
                        browser.close()
                    except Exception:
                        pass

            if all_products or not blocked:
                break  # no reintentar si funcionó o si no hubo bloqueo

        except Exception as e:
            logging.error("[adidas] Error general (headless=%s): %s", headless, e)

    if debug:
        print(f"  [adidas] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    logging.info("[adidas] %s: %d productos >= %.0f%%", category_name, len(all_products), min_discount)
    return all_products
