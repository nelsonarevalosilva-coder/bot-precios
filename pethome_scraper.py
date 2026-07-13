"""
Scraper para PetHome Chile (Shopify).
Colecciones principales: /collections/perros, /collections/gatos
La API retorna compare_at_price vs price para calcular descuento real.
"""
from shopify_scraper import make_store_scraper

scrape_category = make_store_scraper("PetHome")
