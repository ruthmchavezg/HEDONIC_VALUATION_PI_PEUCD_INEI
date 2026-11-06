import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
INTERIM_DIR = BASE_DIR / "data" / "interim"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
LOG_DIR = BASE_DIR / "logs"

for d in [
    RAW_DIR / "portals",
    RAW_DIR / "sessions",
    RAW_DIR / "sessions" / "chrome_cdp_profile",
    INTERIM_DIR / "portals_clean",
    INTERIM_DIR / "checkpoints",
    PROCESSED_DIR,
    LOG_DIR / "scraping",
]:
    d.mkdir(parents=True, exist_ok=True)

BCRP_API_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD/json"
TIPO_CAMBIO_FALLBACK = 3.75

MAX_PAGINAS_DEFAULT = 999
CHECKPOINT_INTERVAL = 10
ROTATE_CONTEXT_EVERY = 50
USE_FREE_PROXIES = False
PROXY_SERVER = None

DISTRITOS_LIMA = [
    "Ancón", "Ate", "Barranco", "Breña", "Carabayllo", "Chaclacayo", "Chorrillos",
    "Cieneguilla", "Comas", "El Agustino", "Independencia", "Jesús María", "La Molina",
    "La Victoria", "Cercado de Lima", "Lince", "Los Olivos", "Lurigancho", "Chosica",
    "Lurín", "Magdalena del Mar", "Magdalena", "Miraflores", "Pachacámac", "Pucusana",
    "Pueblo Libre", "Puente Piedra", "Punta Hermosa", "Punta Negra", "Rímac",
    "San Bartolo", "San Borja", "San Isidro", "San Juan de Lurigancho",
    "San Juan de Miraflores", "San Luis", "San Martín de Porres", "San Miguel",
    "Santa Anita", "Santa María del Mar", "Santa Rosa", "Santiago de Surco", "Surco",
    "Surquillo", "Villa El Salvador", "Villa María del Triunfo", "Callao", "Bellavista",
    "La Perla", "La Punta", "Ventanilla", "Mi Perú"
]

REGEX_PATTERNS = {
    "id_anuncio": re.compile(r"(?:-|_id_|/|id=)(\d{5,12})(?:\.html|/|&|$)", re.IGNORECASE),
    "area_total": re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:m²|m2|mt2|mts2)\s*(?:totales|total|de terreno|terreno)?", re.IGNORECASE),
    "area_construida": re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:m²|m2|mt2|mts2)\s*(?:construidos|techados|cubiertos|construida|construcción)", re.IGNORECASE),
    "dormitorios": re.compile(r"(\d+)\s*(?:dormitorios?|dorms?|habitaciones?|hab|cuartos?|rec[áa]maras?|rec\.)", re.IGNORECASE),
    "banos": re.compile(r"(\d+)\s*(?:baños?|banos?)", re.IGNORECASE),
    "estacionamientos": re.compile(r"(\d+)\s*(?:estacionamientos?|estac\.?|cocheras?|garajes?)", re.IGNORECASE),
    "antiguedad": re.compile(r"(\d+)\s*años?\s*(?:de\s*antigüedad)?", re.IGNORECASE),
    "mantenimiento": re.compile(r"mantenimiento\s*[:.]?\s*(?:s/|s/\.|usd|\$)?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE),
}

REGLAS_GENERICAS = {
    "titulo": ['h1', '[class*="title"]', '[class*="header-title"]'],
    "estado_proyecto": ['[class*="status"]', '[class*="badge"]', '[class*="tag"]', '[class*="operation"]'],
    "bloque_precio": ['[class*="price"]', '[data-qa*="price"]', '[class*="precio"]', '[class*="valor"]'],
    "ubicacion": ['[class*="address"]', '[class*="location"]', '[class*="ubicacion"]', 'h2[class*="subtitle"]', '#map-section'],
    "datos_principales_generales": ['[class*="features"]', '[class*="details"]', '[class*="characteristics"]', '[class*="caracteristicas"]', 'ul[class*="main"]'],
    "otras_caracteristicas": ['[class*="amenities"]', '[class*="facilities"]', '[class*="other-features"]', '[class*="adicionales"]'],
    "caracteristicas": ['[class*="general-features"]', '[class*="property-details"]', 'section[class*="features"]', '[class*="specs"]'],
    "comodidades": ['[class*="comforts"]', '[class*="amenities-list"]', '[class*="icons-grid"]', '[class*="equipamiento"]'],
    "descripcion": ['[class*="description"]', '#description', '#longDescription', '[class*="descripcion"]', 'article']
}

PERFILES_PORTALES = {
    "babilonia": {
        "dominio": "https://babilonia.pe",
        "urls_semilla": [
            ("casa", ["https://babilonia.pe/inmuebles/casas-en-alquiler-en-lima"]),
            ("departamento", ["https://babilonia.pe/inmuebles/departamentos-en-alquiler-en-lima"]),
            ("habitacion", [
                "https://babilonia.pe/inmuebles/habitaciones-en-alquiler-en-lima",
                "https://babilonia.pe/inmuebles/propiedades-en-alquiler-en-lima?q=cuarto"
            ]),
        ],
        "selector_enlaces_listado": 'a[href*="/inmueble/"], a[href*="/propiedades/"], div[class*="card"] a[href]',
        "filtro_url_inmueble": ["/inmueble/", "/propiedades/"],
        "patron_paginacion": "?page={page}",
        "selector_siguiente_pagina": ['a[rel="next"]', 'button[aria-label*="Next"]', 'button[aria-label*="Siguiente"]', 'li.pagination-next a'],
        "reglas_extraccion": REGLAS_GENERICAS
    },
    "properati": {
        "dominio": "https://www.properati.com.pe",
        "urls_semilla": [
            ("casa", ["https://www.properati.com.pe/s/lima/casa/alquiler"]),
            ("departamento", ["https://www.properati.com.pe/s/lima/departamento/alquiler"]),
            ("habitacion", [
                "https://www.properati.com.pe/s/lima/habitacion/alquiler",
                "https://www.properati.com.pe/s/lima/alquiler?q=cuarto",
                "https://www.properati.com.pe/s/lima/alquiler"
            ]),
        ],
        "selector_enlaces_listado": 'a[href*="/detalle/"], article a[href], div[class*="snippet"] a[href]',
        "filtro_url_inmueble": ["/detalle/"],
        "patron_paginacion": "/{page}",
        "selector_siguiente_pagina": ['a[rel="next"]', 'a[class*="pagination__next"]'],
        "reglas_extraccion": REGLAS_GENERICAS
    },
    "laencontre": {
        "dominio": "https://www.laencontre.com.pe",
        "urls_semilla": [
            ("casa", ["https://www.laencontre.com.pe/alquiler/casas/lima-departamento/list"]),
            ("departamento", ["https://www.laencontre.com.pe/alquiler/departamentos/lima-departamento/list"]),
            ("habitacion", [
                "https://www.laencontre.com.pe/alquiler/habitaciones/lima-departamento/list",
                "https://www.laencontre.com.pe/alquiler/cuartos/lima-departamento/list"
            ]),
        ],
        "selector_enlaces_listado": 'a[href*="/inmueble/"], h2 a[href], article a[href], div[class*="card"] a[href]',
        "filtro_url_inmueble": ["/inmueble/"],
        "patron_paginacion": "/p_{page}",
        "selector_siguiente_pagina": ['a[rel="next"]', 'li.next a', 'a[class*="next"]'],
        "reglas_extraccion": REGLAS_GENERICAS
    },
    "remax": {
        "dominio": "https://www.remax.pe",
        "urls_semilla": [
            ("casa", ["https://www.remax.pe/web/search/property?type=alquiler&property_type=casa&department=lima"]),
            ("departamento", ["https://www.remax.pe/web/search/property?type=alquiler&property_type=departamento&department=lima"]),
            ("habitacion", [
                "https://www.remax.pe/web/search/property?type=alquiler&property_type=habitacion&department=lima",
                "https://www.remax.pe/web/search/property?type=alquiler&q=cuarto&department=lima"
            ]),
        ],
        "selector_enlaces_listado": 'a[href*="propiedad"], a[href*="/inmueble"], a[href*="property"], a[href*="detalle"], div[class*="card"] a[href]',
        "filtro_url_inmueble": ["propiedad", "property", "inmueble", "alquiler", "detalle", "id"],
        "patron_paginacion": "&page={page}",
        "selector_siguiente_pagina": ['a[rel="next"]', 'ul.pagination li:last-child a'],
        "reglas_extraccion": REGLAS_GENERICAS
    },
    "century21": {
        "dominio": "https://century21.pe",
        "urls_semilla": [
            ("casa", ["https://century21.pe/v/resultados/tipo_casa/operacion_renta/en-pais_peru/en-estado_lima"]),
            ("departamento", ["https://century21.pe/v/resultados/tipo_departamento/operacion_renta/en-pais_peru/en-estado_lima"]),
            ("habitacion", [
                "https://century21.pe/v/resultados/tipo_habitacion/operacion_renta/en-pais_peru/en-estado_lima",
                "https://century21.pe/v/resultados/tipo_departamento/operacion_renta/en-pais_peru/en-estado_lima/recamaras_1"
            ]),
        ],
        "selector_enlaces_listado": 'a[href*="/propiedad/"], div[class*="card"] a[href]',
        "filtro_url_inmueble": ["/propiedad/"],
        "patron_paginacion": "?pagina={page}",
        "selector_siguiente_pagina": ['a[rel="next"]'],
        "reglas_extraccion": REGLAS_GENERICAS
    },
    "urbania": {
        "dominio": "https://urbania.pe",
        "urls_semilla": [
            ("casa", ["https://urbania.pe/buscar/alquiler-de-casas-en-lima"]),
            ("departamento", ["https://urbania.pe/buscar/alquiler-de-departamentos-en-lima"]),
            ("habitacion", [
                "https://urbania.pe/buscar/alquiler-de-habitaciones-en-lima",
                "https://urbania.pe/buscar/alquiler-de-cuartos-en-lima"
            ]),
        ],
        "selector_enlaces_listado": '[data-to-posting], a[href*="/propiedades/"]',
        "filtro_url_inmueble": ["/propiedades/"],
        "patron_paginacion": "?page={page}",
        "selector_siguiente_pagina": ['a[data-qa="PAGING_NEXT"]', 'a[rel="next"]'],
        "reglas_extraccion": {
            "titulo": ['.title-h1-development', '.title-property', 'h1'],
            "estado_proyecto": ['.status-delivery-and-financing', '.status-delivery'],
            "bloque_precio": ['.price-operation-type', '.unitPrice', '.price-items', '.transaction-price'],
            "ubicacion": ['#ref-map', '.section-location-property', '.title-location'],
            "datos_principales_generales": ['.development-features-grid', '.main-features-grid', 'ul.main-features', '#section-icon-features-property'],
            "otras_caracteristicas": [
                'xpath=//h4[contains(text(), "Otras características")]/following-sibling::div',
                'xpath=//h3[contains(text(), "Otras características")]/following-sibling::div',
                'div[class*="other-features"]'
            ],
            "caracteristicas": ['#reactGeneralFeatures', '.main-features', 'ul.features-list'],
            "comodidades": ['div[class*="devFeaturesNew-module__icons-grid"]', '#reactGeneralFeatures', '.section-features', 'ul.features-list'],
            "descripcion": ['div[class*="description-module__wrapper-description"]', '#longDescription', '.box-description', '.box-descritpion']
        }
    },
    "adondevivir": {
        "dominio": "https://www.adondevivir.com",
        "urls_semilla": [
            ("casa", ["https://www.adondevivir.com/casas-en-alquiler-en-lima.html"]),
            ("departamento", ["https://www.adondevivir.com/departamentos-en-alquiler-en-lima.html"]),
            ("habitacion", [
                "https://www.adondevivir.com/habitaciones-en-alquiler-en-lima.html",
                "https://www.adondevivir.com/cuartos-en-alquiler-en-lima.html",
                "https://www.adondevivir.com/inmuebles-en-alquiler-en-lima-q-habitacion.html"
            ]),
        ],
        "selector_enlaces_listado": '[data-to-posting], a[href*="/propiedades/"]',
        "filtro_url_inmueble": ["/propiedades/"],
        "patron_paginacion": "-pagina-{page}.html",
        "selector_siguiente_pagina": ['a[data-qa="PAGING_NEXT"]', 'a[rel="next"]'],
        "reglas_extraccion": {
            "titulo": ['.title-h1-development', '.title-property', 'h1'],
            "estado_proyecto": ['.status-delivery-and-financing', '.status-delivery'],
            "bloque_precio": ['.price-operation-type', '.unitPrice', '.price-items', '.transaction-price'],
            "ubicacion": ['#ref-map', '.section-location-property', '.title-location'],
            "datos_principales_generales": ['.development-features-grid', '.main-features-grid', 'ul.main-features', '#section-icon-features-property'],
            "otras_caracteristicas": [
                'xpath=//h4[contains(text(), "Otras características")]/following-sibling::div',
                'xpath=//h3[contains(text(), "Otras características")]/following-sibling::div',
                'div[class*="other-features"]'
            ],
            "caracteristicas": ['#reactGeneralFeatures', '.main-features', 'ul.features-list'],
            "comodidades": ['div[class*="devFeaturesNew-module__icons-grid"]', '#reactGeneralFeatures', '.section-features', 'ul.features-list'],
            "descripcion": ['div[class*="description-module__wrapper-description"]', '#longDescription', '.box-description', '.box-descritpion']
        }
    }
}