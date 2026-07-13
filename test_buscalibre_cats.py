import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import re, json, time
from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup

session = cf_requests.Session(impersonate="chrome124")
session.headers.update({"Accept-Language": "es-CL,es;q=0.9", "Referer": "https://www.buscalibre.cl/"})

# 1. Todos los slugs del JS de la homepage
r = session.get("https://www.buscalibre.cl/libros/", timeout=15)
soup = BeautifulSoup(r.text, "html.parser")
js_slugs = set()
for script in soup.select("script"):
    text = script.string or ""
    matches = re.findall(r'["\'/]libros/([a-z0-9\-]+)/?["\']', text)
    for m in matches:
        if len(m) > 2:
            js_slugs.add(m)

print(f"Slugs JS: {sorted(js_slugs)}\n")

# 2. Probar slugs adicionales que podrían existir
extra_slugs = [
    "biografia", "autobiografia", "poesia", "teatro", "cuento",
    "aventura", "thriller", "misterio", "terror", "romance",
    "fantasia", "ciencia-ficcion", "humor", "ensayo",
    "politica", "economia", "sociologia", "antropologia",
    "geografia", "viajes", "arquitectura", "fotografia", "musica",
    "cine", "gastronomia", "salud", "nutricion", "yoga",
    "empresas", "marketing", "administracion", "contabilidad",
    "informatica", "programacion", "inteligencia-artificial",
    "educacion", "pedagogia", "idiomas", "idioma-ingles",
    "manga", "comics", "graphic-novel",
    "literatura-infantil", "cuentos-infantiles",
    "no-ficcion", "divulgacion", "periodismo",
    "esoterismo", "espiritualidad", "new-age",
    "guias-practicas", "bricolaje", "jardineria",
    "animales", "naturaleza",
]

all_slugs = js_slugs | set(extra_slugs)

# 3. Verificar cuáles tienen productos con descuento=70
print("=== Todas las categorías con descuento=70 ===")
valid = []
for slug in sorted(all_slugs):
    url = f"https://www.buscalibre.cl/libros/{slug}/?descuento=70"
    r2 = session.get(url, timeout=10, allow_redirects=True)
    prods = BeautifulSoup(r2.text, "html.parser").select(".box-producto")
    status = "OK" if prods else "--"
    print(f"  {status} | {len(prods):3d} | {slug}")
    if prods:
        valid.append(slug)
    time.sleep(0.3)

print(f"\nTotal con productos: {len(valid)}")
print(f"Ya en categorias.json: {json.load(open('buscalibre_categories.json'))}")
