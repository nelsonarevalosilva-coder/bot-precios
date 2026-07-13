import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import buscalibre_scraper

products = buscalibre_scraper.scrape_category(
    "https://www.buscalibre.cl/libros/search/?q=libro&descuento=70",
    "Libros con 70%+ descuento",
    min_discount=70.0,
    max_pages=3,
    debug=True,
)
print(f"\nTotal: {len(products)} libros encontrados")
for p in products[:5]:
    print(f"  {p.name[:60]} | {p.discount_pct:.0f}% | {p.normal_price} -> {p.sale_price}")
    print(f"    img: {p.image_url[:70]}")
