# Configuración de canales de suscripción y precios

CHANNELS = {
    "tecnologia":    {"id": -1003633911277, "name": "💻 Tecnología"},
    "muebles_hogar": {"id": -1003804002653, "name": "🛋️ Muebles y Hogar"},
    "electro":       {"id": -1003911147571, "name": "🏠 Electrodomésticos"},
    "perfumes":      {"id": -1003980648018, "name": "💄 Perfumes y Belleza"},
    "gaming":        {"id": -1004290755569, "name": "🎮 Gaming"},
    "zapatillas":    {"id": -1003900467811, "name": "👟 Zapatillas"},
    "outdoor":       {"id": -1003907913373, "name": "⛺ Outdoor y Camping"},
    "deportes":      {"id": -1003998383372, "name": "⚽ Deportes"},
    "ropa":          {"id": -1003932337515, "name": "👗 Ropa y Moda"},
    "automotriz":    {"id": -1003962932016, "name": "🚗 Automotriz"},
    "ferreteria":    {"id": -1003848024596, "name": "🔧 Ferretería"},
    "licores":       {"id": -1004053668233, "name": "🍷 Licores"},
}

# Precios en CLP — ajusta según tus objetivos
PLANS = {
    "mensual": {
        "days": 30,
        "label": "1 mes",
        "price_single": 990,     # 1 canal
        "price_all": 4990,       # todos los canales
    },
    "trimestral": {
        "days": 90,
        "label": "3 meses",
        "price_single": 2490,    # 1 canal (~16% descuento)
        "price_all": 11990,      # todos los canales
    },
}
