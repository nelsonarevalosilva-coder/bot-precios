import os
import threading
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Rate limiter global: máximo 1 mensaje cada 0.5s para no saturar Telegram
_tg_lock = threading.Lock()
_tg_last_send = 0.0
_TG_MIN_INTERVAL = 0.5


def _tg_post(endpoint: str, payload: dict, timeout: int = 15) -> requests.Response:
    """POST a Telegram con rate limiting y retry automático en 429."""
    global _tg_last_send
    with _tg_lock:
        elapsed = time.time() - _tg_last_send
        if elapsed < _TG_MIN_INTERVAL:
            time.sleep(_TG_MIN_INTERVAL - elapsed)
        _tg_last_send = time.time()

    for attempt in range(3):
        try:
            resp = requests.post(f"{TELEGRAM_API}/{endpoint}", json=payload, timeout=timeout)
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                print(f"[notifier] Telegram rate limit — esperando {retry_after}s")
                time.sleep(retry_after)
                continue
            return resp
        except Exception as e:
            if attempt == 2:
                print(f"[notifier] Error en {endpoint}: {e}")
            time.sleep(1)
    return None


def _tg_post_file(endpoint: str, data: dict, files: dict, timeout: int = 30) -> requests.Response:
    """POST a Telegram con archivo multipart + rate limiting."""
    global _tg_last_send
    with _tg_lock:
        elapsed = time.time() - _tg_last_send
        if elapsed < _TG_MIN_INTERVAL:
            time.sleep(_TG_MIN_INTERVAL - elapsed)
        _tg_last_send = time.time()

    for attempt in range(3):
        try:
            resp = requests.post(f"{TELEGRAM_API}/{endpoint}", data=data, files=files, timeout=timeout)
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(retry_after)
                continue
            return resp
        except Exception as e:
            if attempt == 2:
                print(f"[notifier] Error en {endpoint} (file): {e}")
            time.sleep(1)
    return None

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # canal principal / fallback
PRICE_ERROR_CHANNEL = -1004415049589     # canal "Error de precios"
OWNER_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))  # mensaje directo al dueño

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# IDs de los canales por categoría
CHANNEL_IDS = {
    "tecnologia":    -1003633911277,
    "muebles_hogar": -1003804002653,
    "electro":       -1003911147571,
    "perfumes":      -1003980648018,
    "gaming":        -1004290755569,
    "zapatillas":    -1003900467811,
    "outdoor":       -1003907913373,
    "deportes":      -1003998383372,
    "ropa":          -1003932337515,
    "automotriz":    -1003962932016,
    "ferreteria":    -1003848024596,
    "licores":       -1004053668233,
    "belleza":       -1003936872606,
    "farmacia":      -1003636628389,
    "jugueteria":    -1003791149328,
    "mascotas":      -1004287587407,
    "libros":        -1004298629705,
    "audio":          -1003975359758,
    "supermercado":   -1003713534233,
    "error_precios":  -1004415049589,
    "delivery":       int(os.getenv("DELIVERY_CHANNEL_ID", "-1004304585105")),
}

# Tiendas que siempre van a un canal específico
STORE_CHANNEL = {
    "PC Factory":           "tecnologia",
    "Multimarcas Perfumes": "perfumes",
    "Columbia":             "outdoor",
    "Doite":                "outdoor",
    "Wild Lama":            "outdoor",
    "El Mundo del Vino":   "licores",
    "Liquidos":            "licores",
    "Booz":               "licores",
    "Hush Puppies":         "zapatillas",
    "IKEA":                 "muebles_hogar",
    "Amoble":               "muebles_hogar",
    "Rosen":                "muebles_hogar",
    "Silk Perfumes":        "perfumes",
    "Blush-Bar":            "belleza",
    "Sally Beauty":         "belleza",
    "Sokobox":              "belleza",
    "Gotta":                "zapatillas",
    "Saxoline":             "zapatillas",
    "Kippy Chile":          "zapatillas",
    "Farmacia Ahumada":     "farmacia",
    "Cruz Verde":           "farmacia",
    "The Body Shop":        "belleza",
    "Mundo Aromas":         "perfumes",
    "Alisha Perfumes":      "perfumes",
    "Lo Doro":              "perfumes",
    "Santiago Perfumes":    "perfumes",
    "Cosmetic":             "belleza",
    "Adidas":               "zapatillas",
    "Nike":                 "zapatillas",
    "Oferta Perfumes":      "perfumes",
    "Yauras":               "perfumes",
    "Elite Perfumes":       "perfumes",
    "Sairam":               "perfumes",
    "Easy":                 "ferreteria",
    "Jumbo":                "supermercado",
    "Santa Isabel":         "supermercado",
    "Unimarc":              "supermercado",
    "Bata":                 "zapatillas",
    "New Balance":          "zapatillas",
    "Converse":             "zapatillas",
    "Skechers":             "zapatillas",
    "Decathlon":            "deportes",
    "Under Armour":         "deportes",
    "Xiaomi":               "tecnologia",
    "Corona":               "muebles_hogar",
    "Merrell":              "zapatillas",
    "Lippi":                "outdoor",
    "Fila":                 "zapatillas",
    "Puma":                 "zapatillas",
    "Crocs":                "zapatillas",
    "Vans":                 "zapatillas",
    "Asics":                "zapatillas",
    "HOKA":                 "zapatillas",
    "Reebok":               "zapatillas",
    "PetHome":              "mascotas",
    "SuperZoo":             "mascotas",
    "Laika":                "mascotas",
    "Lider":                "supermercado",
}

# Keywords de categoría → canal (el primer match gana)
CATEGORY_KEYWORDS = [
    ("zapatilla",       "zapatillas"),
    ("zapatos",         "zapatillas"),
    ("calzado",         "zapatillas"),
    ("consola",         "gaming"),
    ("gaming",          "gaming"),
    ("electrodom",      "electro"),
    ("refriger",        "electro"),
    ("lavadora",        "electro"),
    ("microondas",      "electro"),
    ("electro",         "electro"),
    ("televisí",        "tecnologia"),
    ("televisor",       "tecnologia"),
    ("television",      "tecnologia"),
    ("tv y video",      "tecnologia"),
    ("smart tv",        "tecnologia"),
    ("computador",      "tecnologia"),
    ("celular",         "tecnologia"),
    ("smartphone",      "tecnologia"),
    ("notebook",        "tecnologia"),
    ("monitor",         "tecnologia"),
    ("tablet",          "tecnologia"),
    ("audio",           "tecnologia"),
    ("tecno",           "tecnologia"),
    ("almacenamiento",  "tecnologia"),
    ("memorias",        "tecnologia"),
    ("impresora",       "tecnologia"),
    ("componente",      "tecnologia"),
    ("perfume",         "perfumes"),
    ("fragancia",       "perfumes"),
    ("colonia",         "perfumes"),
    ("belleza",          "belleza"),
    ("maquillaje",       "belleza"),
    ("cosmetico",        "belleza"),
    ("cosmético",        "belleza"),
    ("skincare",         "belleza"),
    ("shampoo",          "belleza"),
    ("serum",            "belleza"),
    ("cuidado personal", "belleza"),
    ("cuidado de piel",  "belleza"),
    ("baño y cuerpo",    "belleza"),
    ("cuerpo y baño",    "belleza"),
    ("body care",        "belleza"),
    ("higiene",          "belleza"),
    ("deporte",         "deportes"),
    ("ferreteria",      "ferreteria"),
    ("ferretería",      "ferreteria"),
    ("herramienta",     "ferreteria"),
    ("electricidad",    "ferreteria"),
    ("jardín",          "ferreteria"),
    ("jardin",          "ferreteria"),
    ("pintura",         "ferreteria"),
    ("plomería",        "ferreteria"),
    ("plomeria",        "ferreteria"),
    ("climatizaci",     "ferreteria"),
    ("seguridad",       "ferreteria"),
    ("mueble",          "muebles_hogar"),
    ("dormitorio",      "muebles_hogar"),
    ("baño",            "muebles_hogar"),
    ("bano",            "muebles_hogar"),
    ("cocina",          "muebles_hogar"),
    ("decoraci",        "muebles_hogar"),
    ("iluminaci",       "muebles_hogar"),
    ("hogar",           "muebles_hogar"),
    ("mascota",         "mascotas"),
    ("salud",           "farmacia"),
    ("farmacia",        "farmacia"),
    ("ropa",            "ropa"),
    ("moda",            "ropa"),
    ("hombre",          "ropa"),
    ("mujer",           "ropa"),
    ("infantil",        "ropa"),
    ("niño",            "ropa"),
    ("bebe",            "ropa"),
    ("juguete",         "jugueteria"),
    ("juguetería",      "jugueteria"),
    ("jugueteria",      "jugueteria"),
    ("bebé",            "jugueteria"),
    ("bebe",            "jugueteria"),
    ("automotriz",      "automotriz"),
    ("licor",           "licores"),
    ("vino",            "licores"),
    ("cerveza",         "licores"),
    ("whisky",          "licores"),
    ("pisco",           "licores"),
    ("ron",             "licores"),
    ("vodka",           "licores"),
    ("gin",             "licores"),
    ("tequila",         "licores"),
    ("espumante",       "licores"),
]


# Keywords en el nombre del producto que fuerzan un canal específico
# (tienen prioridad sobre el override de tienda)
PRODUCT_NAME_KEYWORDS = [
    # Perfumes / Fragancias — máxima prioridad para evitar que categoría "Belleza" los capture
    ("perfume",      "perfumes"),
    ("eau de",       "perfumes"),
    ("fragancia",    "perfumes"),
    ("colonia ",     "perfumes"),   # "Colonia Acqua Di Gio" — espacio final evita matchear "colonial"
    (" edt ",        "perfumes"),
    (" edp ",        "perfumes"),
    ("parfum",       "perfumes"),
    # Ferretería / herramientas (para ML y tiendas que categorizan herramientas como tecnología)
    ("taladro",            "ferreteria"),
    ("atornillador",       "ferreteria"),
    ("llave de impacto",   "ferreteria"),
    ("llave inglesa",      "ferreteria"),
    ("amoladora",          "ferreteria"),
    ("lijadora",           "ferreteria"),
    ("esmeril",            "ferreteria"),
    ("soldadora",          "ferreteria"),
    ("compresor de aire",  "ferreteria"),
    ("sierra circular",    "ferreteria"),
    ("sierra caladora",    "ferreteria"),
    ("sierra sable",       "ferreteria"),
    ("martillo eléctrico", "ferreteria"),
    ("martillo electrico", "ferreteria"),
    ("pistola de calor",   "ferreteria"),
    ("tronzadora",         "ferreteria"),
    ("fresadora",          "ferreteria"),
    ("kit de herramienta", "ferreteria"),
    ("set de herramienta", "ferreteria"),
    ("piezas bosch",       "ferreteria"),
    ("piezas dewalt",      "ferreteria"),
    ("piezas makita",      "ferreteria"),
    # Accesorios de moda
    ("cartera",   "ropa"),
    ("bolso",     "ropa"),
    ("mochila",   "outdoor"),
    ("morral",    "outdoor"),
    ("billetera", "ropa"),
    ("tarjetero", "ropa"),
    ("monedero",  "ropa"),
    ("cinturón",  "ropa"),
    ("cinturon",  "ropa"),
    ("correa",    "ropa"),
    # Belleza / higiene / skincare
    ("desodorante",     "belleza"),
    ("antitranspirante","belleza"),
    ("shampoo",         "belleza"),
    ("acondicionador",  "belleza"),
    ("maquillaje",      "belleza"),
    ("makeup",          "belleza"),
    ("crema facial",    "belleza"),
    ("crema hidratante","belleza"),
    ("crema corporal",  "belleza"),
    ("crema antiedad",  "belleza"),
    ("crema de manos",  "belleza"),
    ("crema antiarrug", "belleza"),
    ("crema exfoliant", "belleza"),
    ("facial",          "belleza"),
    ("hidratante",      "belleza"),
    ("contorno de ojos","belleza"),
    ("desmaquillante",  "belleza"),
    ("tónico",          "belleza"),
    ("tonico",          "belleza"),
    ("mascarilla",      "belleza"),
    ("loción",          "belleza"),
    ("locion",          "belleza"),
    ("esmalte al agua",  "ferreteria"),
    ("esmalte acrílico", "ferreteria"),
    ("esmalte acrilico", "ferreteria"),
    ("esmalte de uñas",  "belleza"),
    ("esmalte uñas",     "belleza"),
    ("labial",          "belleza"),
    ("bronceador",      "belleza"),
    ("corrector",       "belleza"),
    ("base maquillaje", "belleza"),
    ("sérum",           "belleza"),
    ("limpiador",       "belleza"),
    ("gel limpiador",   "belleza"),
    ("agua micelar",    "belleza"),
    ("gel de baño",     "belleza"),
    ("gel de ducha",    "belleza"),
    ("exfoliante",      "belleza"),
    ("antimanchas",     "belleza"),
    ("anti-manchas",    "belleza"),
    ("antipigment",     "belleza"),
    ("anti-pigment",    "belleza"),
    ("rutina",          "belleza"),
    ("duplo",           "belleza"),
    ("jabón",           "belleza"),
    ("jabon",           "belleza"),
    ("mousse",          "belleza"),
    ("micelar",         "belleza"),
    ("pack rutina",     "belleza"),
    ("set belleza",     "belleza"),
    ("cuidado de manos","belleza"),
    ("uñas",            "belleza"),
    # Muebles del hogar — para tiendas con categoría genérica (Outlet, etc.)
    ("maceta",         "muebles_hogar"),
    ("macetero",       "muebles_hogar"),
    ("rejilla para",   "muebles_hogar"),
    ("rejilla cocina", "muebles_hogar"),
    ("closet",    "muebles_hogar"),
    ("clóset",    "muebles_hogar"),
    ("cómoda",    "muebles_hogar"),
    ("comoda",    "muebles_hogar"),
    ("ropero",    "muebles_hogar"),
    ("velador",   "muebles_hogar"),
    ("cajonera",  "muebles_hogar"),
    ("sillón",    "muebles_hogar"),
    ("sillon",    "muebles_hogar"),
    ("baulera",   "muebles_hogar"),
    ("estantería","muebles_hogar"),
    ("estanteria","muebles_hogar"),
    ("escritorio","muebles_hogar"),
    ("librero",   "muebles_hogar"),
    # Ropa
    ("polera",    "ropa"),
    ("camiseta",  "ropa"),
    ("camisa",    "ropa"),
    ("pantalon",  "ropa"),
    ("pantalón",  "ropa"),
    ("vestido",   "ropa"),
    ("chaqueta",  "ropa"),
    ("parka",     "ropa"),
    ("polar",     "ropa"),
    ("buzo",      "ropa"),
    ("falda",     "ropa"),
    ("calza",     "ropa"),
    ("jeans",     "ropa"),
    ("short",     "ropa"),
    ("bikini",    "ropa"),
    ("traje",     "ropa"),
    ("pijama",    "ropa"),
    ("blusa",     "ropa"),
    ("chaleco",   "ropa"),
    ("calcetín",  "ropa"),
    ("calcetin",  "ropa"),
    ("ropa interior", "ropa"),
    # Calzado
    ("zapatilla", "zapatillas"),
    ("sneaker",   "zapatillas"),
    ("tenis",     "zapatillas"),
    ("bota",      "zapatillas"),
    ("sandalia",  "zapatillas"),
    ("zapato",    "zapatillas"),
    ("mocasín",   "zapatillas"),
    ("mocasin",   "zapatillas"),
    ("deportiva", "zapatillas"),
    ("running",   "zapatillas"),
    # Televisores / Smart TVs
    ("smart tv",  "tecnologia"),
    ("televisor", "tecnologia"),
    ("television","tecnologia"),
    ("televisión","tecnologia"),
    ("qled",      "tecnologia"),
    ("neo qled",  "tecnologia"),
    ("oled tv",   "tecnologia"),
    # Tecnología en nombre
    ("notebook",  "tecnologia"),
    ("celular",   "tecnologia"),
    ("smartwatch","tecnologia"),
    ("auricular", "audio"),
    ("audifono",  "audio"),
    ("audífono",  "audio"),
    ("parlante",  "audio"),
    ("altavoz",   "audio"),
    ("soundbar",  "audio"),
    ("earbuds",   "audio"),
    ("earphone",  "audio"),
    ("subwoofer", "audio"),
    ("woofer",    "audio"),
    ("airpods",   "audio"),
    ("headphone", "audio"),
    ("in-ear",    "audio"),
    ("on-ear",    "audio"),
    ("over-ear",  "audio"),
    ("bocina",    "audio"),
    ("tablet",    "tecnologia"),
    ("iphone",    "tecnologia"),
    ("ipad",      "tecnologia"),
    ("airpods",   "audio"),
    ("macbook",   "tecnologia"),
    ("moto g",    "tecnologia"),
    ("moto e",    "tecnologia"),
    ("galaxy s",  "tecnologia"),
    ("galaxy a",  "tecnologia"),
    ("redmi",     "tecnologia"),
    ("poco x",    "tecnologia"),
    ("poco m",    "tecnologia"),
    ("pixel",     "tecnologia"),
    (" 5g",       "tecnologia"),
    ("4g lte",    "tecnologia"),
    ("snapdragon","tecnologia"),
    ("helio",     "tecnologia"),
    ("ram 8gb",   "tecnologia"),
    ("ram 6gb",   "tecnologia"),
    ("ram 4gb",   "tecnologia"),
    ("256gb",     "tecnologia"),
    ("128gb",     "tecnologia"),
    # Juguetes (en nombre del producto)
    ("juguete",          "jugueteria"),
    ("bicicleta niño",   "jugueteria"),
    ("triciclo",         "jugueteria"),
    ("cochecito bebe",   "jugueteria"),
    ("andador bebe",     "jugueteria"),
    ("cuna bebe",        "jugueteria"),
    # Belleza — sets y productos no capturados por keywords genéricos
    ("body butter",      "belleza"),
    ("body lotion",      "belleza"),
    ("body splash",      "belleza"),
    ("body cream",       "belleza"),
    ("body milk",        "belleza"),
    ("aceite corporal",  "belleza"),
    ("aceite de coco",   "belleza"),
    ("aceite de argán",  "belleza"),
    ("aceite de argan",  "belleza"),
    ("set de baño",      "belleza"),
    ("set corporal",     "belleza"),
    ("set de cuerpo",    "belleza"),
    ("crema de cuerpo",  "belleza"),
    ("butter corporal",  "belleza"),
    # Mascotas — keywords generales primero, específicos después
    ("mascota",              "mascotas"),
    ("para perro",           "mascotas"),
    ("para gato",            "mascotas"),
    ("cama perro",           "mascotas"),
    ("cama gato",            "mascotas"),
    ("cama mascota",         "mascotas"),
    ("comedero",             "mascotas"),
    ("bebedero",             "mascotas"),
    ("correa perro",         "mascotas"),
    ("collar perro",         "mascotas"),
    ("collar gato",          "mascotas"),
    ("arnés perro",          "mascotas"),
    ("arnes perro",          "mascotas"),
    ("alimento para perro",  "mascotas"),
    ("alimento para gato",   "mascotas"),
    ("croquetas para perro", "mascotas"),
    ("croquetas para gato",  "mascotas"),
    ("pipeta antiparasit",   "mascotas"),
    ("collar antipulgas",    "mascotas"),
    ("arena para gato",      "mascotas"),
    ("snack para perro",     "mascotas"),
    ("snack para gato",      "mascotas"),
    ("antiparasitario para", "mascotas"),
]


def get_channel_for_product(product) -> int:
    """Retorna el chat_id del canal correcto para el producto."""
    store = getattr(product, "store", "")
    category = getattr(product, "category", "").lower()
    name = getattr(product, "name", "").lower()

    # 0a. Buscalibre: siempre va a libros
    if store == "Buscalibre":
        return CHANNEL_IDS["libros"]

    # 0. Cosmetic: perfumes vs belleza
    if store == "Cosmetic":
        is_perfume = any(kw in name for kw in ("perfume", "eau de", "edp", "edt", "colonia", "fragancia", "parfum"))
        return CHANNEL_IDS["perfumes"] if is_perfume else CHANNEL_IDS["belleza"]

    # 1. Tiendas de moda — keywords primero, fallback ropa
    _FASHION_STORES = {
        "Zara", "Bershka", "Pull&Bear", "Stradivarius",
        "H&M", "Levi's", "Tommy Hilfiger", "Calvin Klein", "Tricot",
    }
    if store in _FASHION_STORES:
        for keyword, channel_key in PRODUCT_NAME_KEYWORDS:
            if keyword in name:
                ch = CHANNEL_IDS.get(channel_key, 0)
                if ch != 0:
                    return ch
        for keyword, channel_key in CATEGORY_KEYWORDS:
            if keyword in category:
                ch = CHANNEL_IDS.get(channel_key, 0)
                if ch != 0:
                    return ch
        return CHANNEL_IDS["ropa"]

    # 2. Hush Puppies: accesorios a ropa, calzado a zapatillas
    if store == "Hush Puppies":
        if any(kw in name for kw in ("tarjetero", "billetera", "cartera", "bolso", "monedero")):
            return CHANNEL_IDS["ropa"]
        return CHANNEL_IDS["zapatillas"]

    # 2. Cruz Verde: higiene/belleza → belleza, resto → farmacia
    if store == "Cruz Verde":
        _belleza_cv = (
            "desodorante", "antitranspirante", "shampoo", "acondicionador",
            "crema", "gel de baño", "gel de ducha", "jabón", "jabon",
            "maquillaje", "facial", "hidratante", "mascarilla", "serum",
            "labial", "esmalte", "locion", "loción", "mousse", "exfoliante",
            "protector solar", "bloqueador", "tónico", "tonico",
        )
        if any(kw in name for kw in _belleza_cv):
            return CHANNEL_IDS["belleza"]
        return CHANNEL_IDS["farmacia"]

    # 3. Marcas deportivas/calzado que también venden ropa — detectar ropa por nombre del producto
    _SPORT_SHOE_BRANDS = {
        "Skechers", "New Balance", "Nike", "Adidas", "Puma", "Fila",
        "Reebok", "HOKA", "Asics", "Vans", "Converse", "Merrell",
    }
    _ROPA_KW_SPORT = (
        "short", "calza", "polera", "camiseta", "camisa", "buzo", "chaqueta",
        "parka", "bra", "legging", "pantalon", "pantalón", "jeans", "falda",
        "vestido", "pijama", "blusa", "chaleco", "jersey", "hoodie", "sudadera",
        "gorra", "calcetín", "calcetin", "calcetines", "medias", "peto",
        "polo", "remera", "musculosa", "sweater", "suéter", "hat", "cap",
        "bomber", "anorak", "chomba", "top ",
    )
    if store in _SPORT_SHOE_BRANDS:
        if any(kw in name for kw in _ROPA_KW_SPORT):
            return CHANNEL_IDS["ropa"]
        return CHANNEL_IDS["zapatillas"]

    # 3b. Marcas outdoor que también venden ropa — detectar por nombre
    _OUTDOOR_BRANDS = {"Wild Lama", "Lippi", "Columbia", "Doite"}
    if store in _OUTDOOR_BRANDS:
        if any(kw in name for kw in _ROPA_KW_SPORT):
            return CHANNEL_IDS["ropa"]

    # 4. Override por tienda (tiene prioridad sobre nombre del producto).
    # Tiendas especializadas (farmacia, licores, muebles, etc.) siempre van a su canal.
    if store in STORE_CHANNEL:
        ch = CHANNEL_IDS.get(STORE_CHANNEL[store], 0)
        return ch if ch != 0 else CHANNEL_IDS["tecnologia"]

    # 3. Chequeo por nombre del producto (para tiendas sin canal fijo: Paris, ML, etc.)
    for keyword, channel_key in PRODUCT_NAME_KEYWORDS:
        if keyword in name:
            ch = CHANNEL_IDS.get(channel_key, 0)
            if ch != 0:
                return ch

    # 4. Bold: por categoría
    if store == "Bold":
        if "zapatilla" in category:
            return CHANNEL_IDS["zapatillas"]
        return CHANNEL_IDS["ropa"]

    # 6. Paris / Falabella / Ripley: tiendas departamentales — keyword de categoría, luego nombre, fallback ropa
    if store in ("Paris", "Falabella", "Ripley"):
        for keyword, channel_key in CATEGORY_KEYWORDS:
            ch = CHANNEL_IDS.get(channel_key, 0)
            if keyword in category and ch != 0:
                return ch
        # Categoría no matcheó — revisar nombre del producto con todas las keywords
        for keyword, channel_key in PRODUCT_NAME_KEYWORDS:
            if keyword in name:
                ch = CHANNEL_IDS.get(channel_key, 0)
                if ch != 0:
                    return ch
        return CHANNEL_IDS["ropa"]

    # 7. Keyword de categoría
    for keyword, channel_key in CATEGORY_KEYWORDS:
        ch = CHANNEL_IDS.get(channel_key, 0)
        if keyword in category and ch != 0:
            return ch

    # 8. Fallback: tecnologia
    return CHANNEL_IDS["tecnologia"]


_CHANNEL_KEYS = {v: k for k, v in CHANNEL_IDS.items()}


def get_channel_key_for_product(product) -> str:
    """Retorna el key (string) del canal correcto para el producto."""
    channel_id = get_channel_for_product(product)
    return _CHANNEL_KEYS.get(channel_id, "tecnologia")


def _send(text: str, chat_id=None) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("[notifier] TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados.")
        return False
    target = chat_id if chat_id is not None else int(CHAT_ID)
    resp = _tg_post("sendMessage", {"chat_id": target, "text": text, "parse_mode": "HTML"})
    return resp is not None and resp.status_code == 200


_IMG_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _send_with_image(text: str, image_url: str, chat_id: int) -> bool:
    if image_url:
        # Intento 1: pasar URL directo a Telegram (más rápido, sin descargar)
        resp = _tg_post("sendPhoto", {
            "chat_id": chat_id,
            "photo": image_url,
            "caption": text[:1024],
            "parse_mode": "HTML",
        })
        if resp is not None and resp.status_code == 200 and resp.json().get("ok"):
            return True
        # Intento 2: descargar y subir como archivo
        try:
            img_resp = requests.get(image_url, headers=_IMG_HEADERS, timeout=10)
            if img_resp.status_code == 200:
                ct = img_resp.headers.get("content-type", "image/jpeg").split(";")[0]
                resp = _tg_post_file(
                    "sendPhoto",
                    data={"chat_id": chat_id, "caption": text[:1024], "parse_mode": "HTML"},
                    files={"photo": ("photo.jpg", img_resp.content, ct)},
                )
                if resp is not None and resp.status_code == 200 and resp.json().get("ok"):
                    return True
                if resp is not None:
                    print(f"[notifier] sendPhoto falló: {resp.json().get('description', '')} | url={image_url[:60]}")
        except Exception as e:
            print(f"[notifier] Error imagen: {e} | url={image_url[:60]}")
    return _send(text, chat_id=chat_id)


def notify_price_drop(product_name: str, url: str, old_price: int, new_price: int):
    diff = old_price - new_price
    pct = (diff / old_price) * 100
    print(f"[notifier] Baja de precio: {product_name} bajó ${diff:,} ({pct:.1f}%) → {url}")


def notify_target_reached(product_name: str, url: str, price: int, target: int):
    print(f"[notifier] Precio objetivo: {product_name} en ${price:,} (objetivo ${target:,}) → {url}")


def _fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return f"{dt.day:02d}/{dt.month:02d}/{dt.year}"
    except Exception:
        return iso[:10]


def _fmt_price(price: int) -> str:
    """Formato chileno: $233.990"""
    return "$" + f"{price:,}".replace(",", ".")


def _seller_line(product) -> str:
    seller = getattr(product, "seller", "")
    store = getattr(product, "store", "")
    if not seller:
        return ""
    if seller.lower() == store.lower():
        return f"\n🏪 Vendedor: <b>{seller}</b> ✅ <i>(tienda oficial)</i>"
    return f"\n🏪 Vendedor: <b>{seller}</b> ⚠️ <i>(marketplace)</i>"


def _history_block(sale_price: int, min_data: tuple | None, last_prices: list) -> str:
    """Genera el bloque de historial de precios en formato lista vertical, sin repetidos."""
    lines = ["\n📊 <b>Precio histórico:</b>"]

    if last_prices:
        # Deduplicar: mostrar solo cuando el precio cambia
        seen = []
        for price, date in last_prices:
            if not seen or seen[-1][0] != price:
                seen.append((price, date))
        for price, date in seen[:5]:
            lines.append(f"{_fmt_date(date)} {_fmt_price(price)}")
    else:
        lines.append("<i>Primera vez registrado</i>")

    return "\n".join(lines)


def notify_price_error(product, min_data=None, last_prices=None) -> bool:
    """Alerta especial para posibles errores de precio (>= 80% descuento)."""
    savings = product.normal_price - product.sale_price
    store = getattr(product, "store", "Ripley")
    image_url = getattr(product, "image_url", "")
    channel = get_channel_for_product(product)
    hist = _history_block(product.sale_price, min_data, last_prices or [])
    seller_info = _seller_line(product)

    if product.sale_price < 1000 and product.normal_price > 5000:
        text = (
            f"🆘 <b>ERROR DE PRECIO EXTREMO en {store}</b>\n\n"
            f"📦 <b>{product.name}</b>\n"
            f"🏷️ Categoría: {product.category}"
            f"{seller_info}\n"
            f"💰 Precio normal: <s>{_fmt_price(product.normal_price)}</s>\n"
            f"🔴 Precio actual: <b>{_fmt_price(product.sale_price)}</b>\n"
            f"📉 Descuento: <b>{product.discount_pct:.0f}%</b>"
            f"{hist}\n\n"
            f"⚠️ <i>Precio probablemente incorrecto — compra ahora antes de que lo corrijan</i>\n"
            f"🔗 <a href=\"{product.url}\">Comprar ahora</a>"
        )
        ok = _send_with_image(text, image_url, channel)
        _send_with_image(text, image_url, PRICE_ERROR_CHANNEL)  # 1 peso → siempre al canal error
        if ok:
            print(f"  → ERROR EXTREMO enviado: {product.name} ({product.discount_pct:.0f}% off) → canal {channel} + error_precios")
        return ok
    else:
        text = (
            f"🚨 <b>POSIBLE ERROR DE PRECIO en {store}</b>\n\n"
            f"📦 <b>{product.name}</b>\n"
            f"🏷️ Categoría: {product.category}"
            f"{seller_info}\n"
            f"💰 Precio normal: <s>{_fmt_price(product.normal_price)}</s>\n"
            f"🔴 Precio actual: <b>{_fmt_price(product.sale_price)}</b>\n"
            f"📉 Descuento: <b>{product.discount_pct:.0f}%</b> — ahorras {_fmt_price(savings)}"
            f"{hist}\n\n"
            f"⚡ <i>Compra antes de que lo corrijan</i>\n"
            f"🔗 <a href=\"{product.url}\">Comprar ahora</a>"
        )
    ok = _send_with_image(text, image_url, channel)
    if product.discount_pct >= 99:
        _send_with_image(text, image_url, PRICE_ERROR_CHANNEL)  # ≥99% → canal error
    if ok:
        print(f"  → ERROR PRECIO enviado: {product.name} ({product.discount_pct:.0f}% off) → canal {channel}")
    return ok


def notify_big_discount(product, min_data=None, last_prices=None, prev_notified_price=None) -> bool:
    """Alerta de descuento encontrado en el catálogo."""
    savings = product.normal_price - product.sale_price
    store = getattr(product, "store", "Ripley")
    image_url = getattr(product, "image_url", "")
    channel = get_channel_for_product(product)
    hist = _history_block(product.sale_price, min_data, last_prices or [])
    seller_info = _seller_line(product)
    author = getattr(product, "author", "")
    author_line = f"\n✍️ Autor: <b>{author}</b>" if author else ""

    prev_line = ""
    if prev_notified_price and prev_notified_price > product.sale_price:
        extra = prev_notified_price - product.sale_price
        prev_line = (
            f"\n⬇️ <b>Bajó desde última alerta:</b> "
            f"<s>{_fmt_price(prev_notified_price)}</s> → <b>{_fmt_price(product.sale_price)}</b> "
            f"(−{_fmt_price(extra)} adicional)"
        )

    text = (
        f"🔥 <b>OFERTA {product.discount_pct:.0f}% DESCUENTO en {store}</b>\n\n"
        f"📦 <b>{product.name}</b>"
        f"{author_line}\n"
        f"🏷️ Categoría: {product.category}"
        f"{seller_info}\n"
        f"💰 Precio normal: <s>{_fmt_price(product.normal_price)}</s>\n"
        f"✅ Precio oferta: <b>{_fmt_price(product.sale_price)}</b>\n"
        f"📉 Descuento: <b>{product.discount_pct:.0f}%</b> (ahorras {_fmt_price(savings)})"
        f"{prev_line}"
        f"{hist}\n\n"
        f"🔗 <a href=\"{product.url}\">Ver oferta</a>"
    )
    ok = _send_with_image(text, image_url, channel)
    if ok:
        print(f"  → Alerta enviada: {product.name} ({product.discount_pct:.0f}% off) → canal {channel}")
    return ok


def notify_catalog_summary(total_found: int, categories_scanned: int, errors_found: int = 0):
    """Resumen del escaneo — solo consola, no va a Telegram."""
    error_line = f" | Errores precio: {errors_found}" if errors_found > 0 else ""
    print(f"[notifier] Escaneo completo — {total_found} ofertas enviadas | {categories_scanned} cats{error_line}")


def notify_error(product_name: str, url: str, error: str):
    print(f"[notifier] Error monitoreando {product_name}: {error}")


def notify_delivery_promo(
    name: str,
    promo_text: str,
    url: str,
    eta: str,
    delivery_cost: int | None,
    app: str = "Rappi",
    is_new: bool = True,
    prev_promo: str = "",
) -> bool:
    """Notifica una promo de restaurante en app de delivery (Rappi, etc.)."""
    channel = CHANNEL_IDS.get("delivery") or int(CHAT_ID or 0)
    if not channel:
        return False

    cost_str = "Gratis" if (delivery_cost == 0) else (f"${delivery_cost:,}" if delivery_cost else "?")

    # Ícono según tipo de promo
    if "%" in promo_text:
        import re
        pct_m = re.search(r"(\d+)\s*%", promo_text)
        pct = int(pct_m.group(1)) if pct_m else 0
        icon = "🔥" if pct >= 40 else "🏷️"
    elif any(kw in promo_text.lower() for kw in ("gratis", "free", "despacho")):
        icon = "🚚"
        pct = 0
    else:
        icon = "🎁"
        pct = 0

    change_line = ""
    if not is_new and prev_promo:
        change_line = f"\n🔄 <i>Antes: {prev_promo}</i>"

    text = (
        f"{icon} <b>{'NUEVA PROMO' if is_new else 'PROMO ACTUALIZADA'} en {app}</b>\n\n"
        f"🍽️ <b>{name}</b>\n"
        f"🏷️ <b>{promo_text}</b>"
        f"{change_line}\n"
        f"⏱️ Tiempo estimado: {eta}\n"
        f"🚚 Envío: {cost_str}\n\n"
        f"🔗 <a href=\"{url}\">Ver restaurante en {app}</a>"
    )
    resp = _tg_post("sendMessage", {"chat_id": channel, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False})
    ok = resp is not None and resp.status_code == 200
    if ok:
        print(f"  → Delivery promo enviada: {name} | {promo_text}")
    return ok


def test_connection() -> bool:
    resp = requests.get(f"{TELEGRAM_API}/getMe", timeout=10)
    if resp.status_code == 200:
        bot_name = resp.json()["result"]["username"]
        print(f"[notifier] Conectado al bot: @{bot_name}")
        return True
    print(f"[notifier] Error de conexión: {resp.text}")
    return False
