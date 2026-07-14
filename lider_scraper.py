"""
Scraper de super.lider.cl usando Playwright (headless=False para pasar bot-detection).
"""

import re
import time
from dataclasses import dataclass

BASE_URL = "https://super.lider.cl"

OFFER_URLS = [
    "/content/estos-precios-no-se-tocan/94920941",
]

_HOMEPAGE = BASE_URL

_JS_PARSE = """
(function() {
    var tiles = Array.from(document.querySelectorAll('[data-testid^="product-tile-"]'));
    return tiles.map(function(tile) {
        var nameEl = tile.querySelector('[data-automation-id="product-title"]') || tile.querySelector('h3');
        var link = tile.querySelector('a[href]');
        var img = tile.querySelector('img[data-testid="productTileImage"]');
        var strikeEl = tile.querySelector('.strike');

        var spans = Array.from(tile.querySelectorAll('.ld_Ec'));
        var priceText = '';
        for (var i = 0; i < spans.length; i++) {
            var t = spans[i].textContent;
            if (t.indexOf('precio') !== -1 || t.indexOf('Costaba') !== -1) {
                priceText = t.trim();
                break;
            }
        }

        return {
            name: nameEl ? nameEl.textContent.trim() : '',
            href: link ? link.getAttribute('href') : '',
            img: img ? img.src : '',
            priceText: priceText,
            oldPrice: strikeEl ? strikeEl.textContent.trim() : ''
        };
    });
})()
"""

_JS_HOMEPAGE_LINKS = """
(function() {
    var links = Array.from(document.querySelectorAll('a[href]'));
    var offer = links
        .map(function(a) { return a.getAttribute('href'); })
        .filter(function(h) {
            return h && (h.indexOf('/content/') !== -1 || h.indexOf('/ofertas') !== -1);
        });
    return [...new Set(offer)];
})()
"""


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Lider"
    image_url: str = ""
    seller: str = ""
    author: str = ""


def _clean_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text.split("/")[0])
    return int(digits) if digits else 0


def _parse_price_text(price_text: str):
    """Returns (current_price, old_price) from 'precio actual $X, Costaba $Y'."""
    m_current = re.search(r'precio actual \$?([\d.,]+)', price_text)
    m_old = re.search(r'Costaba \$?([\d.,]+)', price_text)
    current = _clean_price(m_current.group(1)) if m_current else 0
    old = _clean_price(m_old.group(1)) if m_old else 0
    return current, old


def _fetch_offer_urls(page) -> list[str]:
    """Load homepage and collect content/offer page links."""
    try:
        page.goto(_HOMEPAGE, timeout=30000)
        page.wait_for_timeout(5000)
        links = page.evaluate(_JS_HOMEPAGE_LINKS)
        return [l for l in links if l.startswith("/content/") or l.startswith("/ofertas")]
    except Exception:
        return []


def _scrape_page(page, url: str, min_discount: float, seen: set, debug: bool) -> list[Product]:
    try:
        page.goto(BASE_URL + url, timeout=30000)
        page.wait_for_timeout(6000)
        # Scroll down once to trigger lazy loads
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        page.wait_for_timeout(2000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)
    except Exception as e:
        if debug:
            print(f"  [lider] Error loading {url}: {e}")
        return []

    try:
        raw_tiles = page.evaluate(_JS_PARSE)
    except Exception as e:
        if debug:
            print(f"  [lider] JS eval error on {url}: {e}")
        return []

    products = []
    for tile in raw_tiles:
        try:
            name = tile.get("name", "").strip()
            href = tile.get("href", "").strip()
            if not name or not href:
                continue

            product_url = BASE_URL + href if href.startswith("/") else href
            if product_url in seen:
                continue

            price_text = tile.get("priceText", "")
            current_price, old_price = _parse_price_text(price_text)

            # Fall back to .strike element
            if not old_price:
                old_price = _clean_price(tile.get("oldPrice", ""))

            if not current_price or not old_price or old_price <= current_price:
                continue

            discount_pct = (old_price - current_price) / old_price * 100
            if discount_pct < min_discount:
                continue

            seen.add(product_url)
            products.append(Product(
                name=name[:120],
                url=product_url,
                normal_price=old_price,
                sale_price=current_price,
                discount_pct=round(discount_pct, 1),
                category="supermercado",
                store="Lider",
                image_url=tile.get("img", ""),
            ))
        except Exception:
            continue

    if debug:
        print(f"  [lider] {url}: {len(products)} products (from {len(raw_tiles)} tiles)")
    return products


def scrape(min_discount: float = 30.0, debug: bool = False) -> list[Product]:
    from playwright.sync_api import sync_playwright

    all_products: list[Product] = []
    seen: set = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, args=["--window-size=1280,800"])
        ctx = browser.new_context(
            locale="es-CL",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        # Discover promo pages from homepage
        extra_urls = _fetch_offer_urls(page)
        all_urls = list(dict.fromkeys(OFFER_URLS + extra_urls))

        if debug:
            print(f"  [lider] URLs to scrape: {all_urls}")

        for url in all_urls:
            products = _scrape_page(page, url, min_discount, seen, debug)
            all_products.extend(products)
            time.sleep(1)

        browser.close()

    return all_products


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = scrape(min_discount=20.0, debug=True)
    print(f"\nTotal: {len(results)} products")
    for p in results[:10]:
        print(f"  {p.discount_pct:.0f}% | {p.name[:50]} | ${p.sale_price:,} (era ${p.normal_price:,})")
