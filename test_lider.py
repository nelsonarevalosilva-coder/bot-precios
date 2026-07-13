import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from pathlib import Path

try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# Intentar API VTEX directa
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
}

urls_to_try = [
    "https://www.lider.cl/api/catalog_system/pub/products/search?O=OrderByBestDiscountDESC&_from=0&_to=9&map=c",
    "https://www.lider.cl/supermercado/api/catalog_system/pub/products/search?O=OrderByBestDiscountDESC&_from=0&_to=9",
    "https://super.lider.cl/api/catalog_system/pub/products/search?O=OrderByBestDiscountDESC&_from=0&_to=9",
]

print("=== Probando APIs ===")
for url in urls_to_try:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"{url[:70]}: {r.status_code} | {len(r.text)} chars")
        if r.status_code == 200 and r.text.startswith("["):
            print("  ✓ JSON de productos encontrado!")
            import json
            data = r.json()
            print(f"  Productos: {len(data)}")
            if data:
                p = data[0]
                print(f"  Ejemplo: {p.get('productName','')[:60]}")
    except Exception as e:
        print(f"  Error: {e}")

print("\n=== Probando con Playwright + stealth ===")
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="es-CL",
        viewport={"width": 1920, "height": 1080},
    )
    page = context.new_page()
    if HAS_STEALTH:
        stealth_sync(page)
        print("Stealth activado")

    page.goto("https://www.lider.cl", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    print(f"Home: {page.title()[:50]} | {page.url[:60]}")

    page.goto("https://www.lider.cl/supermercado/category/ofertas", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    print(f"Ofertas: {page.title()[:50]} | {page.url[:60]}")

    html = page.content()
    Path("lider_debug.html").write_text(html, encoding="utf-8")
    print(f"HTML: {len(html)} chars")

    soup = BeautifulSoup(html, "html.parser")
    for tag in ["article", "li", "div"]:
        cards = soup.find_all(tag, class_=lambda c: c and any(k in c.lower() for k in ["product", "item", "card"]))
        if cards:
            print(f"<{tag}> con clase product/item/card: {len(cards)}")
            print(f"  Ejemplo clase: {cards[0].get('class')}")
            break

    browser.close()
