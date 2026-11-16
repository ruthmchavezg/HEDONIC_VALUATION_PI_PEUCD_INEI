import re
import os
from pathlib import Path
from dotenv import load_dotenv



BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
INTERIM_DIR = BASE_DIR / "data" / "interim"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
LOG_DIR = BASE_DIR / "logs"

for d in [RAW_DIR / "portals", RAW_DIR / "sessions", RAW_DIR / "sessions" / "chrome_cdp_profile", 
          INTERIM_DIR / "portals_clean", INTERIM_DIR / "checkpoints", PROCESSED_DIR, LOG_DIR / "scraping"]:
    d.mkdir(parents=True, exist_ok=True)

BCRP_API_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD/json"
TIPO_CAMBIO_FALLBACK = 3.75

MAX_PAGINAS_DEFAULT = 999
CHECKPOINT_INTERVAL = 10
ROTATE_CONTEXT_EVERY = 50

DISTRITOS_LIMA = [
    "Ancón", "Ate", "Barranco", "Breña", "Carabayllo", "Chaclacayo", "Chorrillos", "Cieneguilla", "Comas", 
    "El Agustino", "Independencia", "Jesús María", "La Molina", "La Victoria", "Cercado de Lima", "Lince", 
    "Los Olivos", "Lurigancho", "Lurín", "Magdalena del Mar", "Miraflores", "Pachacámac", 
    "Pucusana", "Pueblo Libre", "Puente Piedra", "Punta Hermosa", "Punta Negra", "Rímac", "San Bartolo", 
    "San Borja", "San Isidro", "San Juan de Lurigancho", "San Juan de Miraflores", "San Luis", "San Martín de Porres", 
    "San Miguel", "Santa Anita", "Santa María del Mar", "Santa Rosa", "Santiago de Surco", "Surquillo", 
    "Villa El Salvador", "Villa María del Triunfo"
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

# SE AÑADEN LAS REGLAS GENÉRICAS PARA QUE EL PARSER PUEDA IMPORTARLAS
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

# Configurador maestro
PERFILES_PORTALES = {
    "babilonia": {
        "motor_red": "playwright",
        "dominio": "https://babilonia.pe",
        "urls_semilla": [
            ("casa", ["https://babilonia.pe/inmuebles/casas-en-alquiler-en-lima"]),
            ("departamento", ["https://babilonia.pe/inmuebles/departamentos-en-alquiler-en-lima"]),
            ("habitacion", ["https://babilonia.pe/inmuebles/habitaciones-en-alquiler-en-lima", "https://babilonia.pe/inmuebles/propiedades-en-alquiler-en-lima?q=cuarto"]),
        ],
        "filtro_url": ["/inmueble/", "/propiedades/"]
    },
    "properati": {
        "motor_red": "playwright",
        "dominio": "https://www.properati.com.pe",
        "urls_semilla": [
            ("casa", ["https://www.properati.com.pe/s/lima/casa/alquiler"]),
            ("departamento", ["https://www.properati.com.pe/s/lima/departamento/alquiler"]),
            ("habitacion", ["https://www.properati.com.pe/s/lima/habitacion/alquiler", "https://www.properati.com.pe/s/lima/alquiler?q=cuarto"]),
        ],
        "filtro_url": ["/detalle/"]
    },
    "laencontre": {
        "motor_red": "playwright",
        "dominio": "https://www.laencontre.com.pe",
        "urls_semilla": [
            ("casa", ["https://www.laencontre.com.pe/alquiler/casas/lima-departamento/list"]),
            ("departamento", ["https://www.laencontre.com.pe/alquiler/departamentos/lima-departamento/list"]),
            ("habitacion", ["https://www.laencontre.com.pe/alquiler/habitaciones/lima-departamento/list", "https://www.laencontre.com.pe/alquiler/cuartos/lima-departamento/list"]),
        ],
        "filtro_url": ["/inmueble/"]
    },
    "century21": {
        "motor_red": "playwright",
        "dominio": "https://century21.pe",
        "urls_semilla": [
            ("casa", ["https://century21.pe/v/resultados/tipo_casa/operacion_renta/en-pais_peru/en-estado_lima"]),
            ("departamento", ["https://century21.pe/v/resultados/tipo_departamento/operacion_renta/en-pais_peru/en-estado_lima"]),
            ("habitacion", ["https://century21.pe/v/resultados/tipo_departamento/operacion_renta/en-pais_peru/en-estado_lima/recamaras_1"]),
        ],
        "filtro_url": ["/propiedad/"]
    },
    "urbania": {
        "motor_red": "curl_cffi",  # BYPASS CLOUDFLARE
        "dominio": "https://urbania.pe",
        "urls_semilla": [
            ("casa", ["https://urbania.pe/buscar/alquiler-de-casas-en-lima"]),
            ("departamento", ["https://urbania.pe/buscar/alquiler-de-departamentos-en-lima"]),
            ("habitacion", ["https://urbania.pe/buscar/alquiler-de-habitaciones-en-lima", "https://urbania.pe/buscar/alquiler-de-cuartos-en-lima"]),
        ],
        "filtro_url": ["/propiedades/"]
    },
    "adondevivir": {
        "motor_red": "curl_cffi",  # BYPASS CLOUDFLARE
        "dominio": "https://www.adondevivir.com",
        "urls_semilla": [
            ("casa", ["https://www.adondevivir.com/casas-en-alquiler-en-lima.html"]),
            ("departamento", ["https://www.adondevivir.com/departamentos-en-alquiler-en-lima.html"]),
            ("habitacion", ["https://www.adondevivir.com/habitaciones-en-alquiler-en-lima.html", "https://www.adondevivir.com/cuartos-en-alquiler-en-lima.html"]),
        ],
        "filtro_url": ["/propiedades/"]
    },
    "remax": {
        "motor_red": "curl_cffi",  # BYPASS CLOUDFLARE
        "dominio": "https://www.remax.pe",
        "urls_semilla": [
            ("casa", ["https://www.remax.pe/web/search/property?type=alquiler&property_type=casa&department=lima"]),
            ("departamento", ["https://www.remax.pe/web/search/property?type=alquiler&property_type=departamento&department=lima"]),
            ("habitacion", ["https://www.remax.pe/web/search/property?type=alquiler&property_type=habitacion&department=lima"]),
        ],
        "filtro_url": ["propiedad", "inmueble", "alquiler"]
    }
}


load_dotenv()

INTERIM_DIR = BASE_DIR / "data" / "interim"
REPORTS_DIR = BASE_DIR / "reports"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")