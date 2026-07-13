import json
import sys
import time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="es-CL",
    )
    page = context.new_page()

    sale_body = None
    def on_response(resp):
        global sale_body
        try:
            if resp.status == 200 and "/sale.json" in resp.url and "_next/data" in resp.url and sale_body is None:
                sale_body = resp.json()
        except Exception:
            pass

    page.on("response", on_response)
    page.goto("https://cl.hm.com/es_cl/", wait_until="load", timeout=30000)
    time.sleep(2)
    page.goto("https://cl.hm.com/es_cl/sale/", wait_until="networkidle", timeout=50000)
    time.sleep(5)
    browser.close()

if sale_body is None:
    print("No se capturó sale.json")
    sys.exit(1)

edges = sale_body.get("pageProps", {}).get("data", {}).get("search", {}).get("products", {}).get("edges", [])
print(f"Total productos (edges): {len(edges)}")

if edges:
    node = edges[0].get("node", {})
    print(f"\nCampos de node[0]: {list(node.keys())}")
    for k, v in node.items():
        if isinstance(v, (list, dict)):
            if isinstance(v, list) and v:
                print(f"  {k}: [lista {len(v)}] primer_item={str(v[0])[:100]}")
            elif isinstance(v, dict):
                print(f"  {k}: {{dict}} keys={list(v.keys())[:10]}")
        else:
            print(f"  {k}: {str(v)[:120]}")

    print("\n=== Primeros 3 productos ===")
    for i, edge in enumerate(edges[:3]):
        node = edge.get("node", {})
        print(f"\nProducto {i+1}:")
        print(f"  name: {node.get('name') or node.get('itemName') or node.get('productName')}")
        # Buscar precio en todos los campos
        for k, v in node.items():
            if "price" in k.lower() or "Price" in k:
                print(f"  {k}: {str(v)[:120]}")
        # URL
        for k in ["url", "link", "slug", "productUrl", "canonicalUrl"]:
            if k in node:
                print(f"  {k}: {str(node[k])[:120]}")
        # Imagen
        for k in ["image", "images", "imageUrl", "thumbnail"]:
            if k in node:
                print(f"  {k}: {str(node[k])[:120]}")
        # Mostrar offers si existen
        if "offers" in node:
            print(f"  offers: {json.dumps(node['offers'])[:200]}")
