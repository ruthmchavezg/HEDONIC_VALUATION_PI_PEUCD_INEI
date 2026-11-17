import re
from pathlib import Path

# [COMENTARIO] IMPORTACIÓN DE LIBRERÍAS
# - Lo que hace: Importa 're' para expresiones regulares y 'Path' para manipulación dinámica de rutas del sistema operativo.
# - Para qué sirve: Prepara las herramientas nativas de Python necesarias para limpiar textos y gestionar archivos.
# - Metodología: Uso estricto de librerías estándar nativas para evitar exceso de dependencias externas y asegurar la portabilidad del código entre los diferentes miembros del equipo.

# Rutas de la Arquitectura Medallion (Bronze, Silver, Gold)
# [COMENTARIO] DEFINICIÓN DE RUTAS BASE
# - Lo que hace: Establece las rutas absolutas donde se guardarán los HTML crudos, respaldos temporales, tablas finales y bitácoras (logs).
# - Para qué sirve: Centraliza el almacenamiento para que el orquestador sepa exactamente dónde guardar o leer la información extraída.
# - Metodología: Arquitectura Medallion (Data Lake). Permite desacoplar el almacenamiento en capas para fines de auditoría del INEI: datos crudos inmutables (Bronze), datos limpios (Silver) y base analítica estructurada para los modelos (Gold)[cite: 12].
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
INTERIM_DIR = BASE_DIR / "data" / "interim"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
LOG_DIR = BASE_DIR / "logs"

# [COMENTARIO] CREACIÓN AUTOMÁTICA DE DIRECTORIOS
# - Lo que hace: Itera sobre las rutas definidas y crea las carpetas físicamente si no existen en la computadora.
# - Para qué sirve: Evita que el script colapse con errores de "File Not Found" al ejecutarse por primera vez en un entorno nuevo.
# - Metodología: Programación Defensiva (exist_ok=True) para garantizar un despliegue seguro y autónomo del pipeline de datos[cite: 12].
for d in [RAW_DIR, INTERIM_DIR, PROCESSED_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# API Oficial del Banco Central de Reserva del Perú (BCRP)
# [COMENTARIO] CONTROL CAMBIARIO (BCRP)
# - Lo que hace: Define la URL de la API oficial del BCRP y establece un valor de rescate (fallback) en caso de caída del servidor.
# - Para qué sirve: Permite transformar dinámicamente precios ofertados en dólares a soles peruanos según la cotización exacta del día de la captura.
# - Metodología: Integración de variables macroeconómicas de fuentes oficiales (benchmark) para controlar la heterogeneidad monetaria del mercado inmobiliario limeño antes del modelamiento[cite: 14].
BCRP_API_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD/json"
TIPO_CAMBIO_FALLBACK = 3.75

# Parámetros de Resiliencia, Control de Velocidad y Proxies Libres
# [COMENTARIO] PARÁMETROS DE RESILIENCIA Y EVASIÓN ANTIBLOQUEO
# - Lo que hace: Configura las variables para la recolección masiva (999 páginas), puntos de guardado cada 20 registros, rotación de identidad cada 60 y el activador de proxies libres.
# - Para qué sirve: Protege la dirección IP del servidor contra baneos de portales como Urbania/Babilonia y asegura que ante un corte de red no se pierdan los datos ya raspados.
# - Metodología: Control de Concurrencia y Resiliencia (Rate Limiting). Aplica el principio de idempotencia mediante "checkpoints" y evasión activa mediante rotación preventiva de huella digital y red[cite: 11, 14].
MAX_PAGINAS_DEFAULT = 999        # 999 = extrae el 100% de páginas disponibles automáticamente
CHECKPOINT_INTERVAL = 20         # Guardar respaldo de emergencia cada 20 inmuebles
ROTATE_CONTEXT_EVERY = 60        # Renovar huella de navegador y proxy cada 60 anuncios
USE_FREE_PROXIES = True          # True = descarga y rota proxies libres automáticamente
PROXY_SERVER = None              # Opcional: proxy privado fijo si algún día lo usas

# [COMENTARIO] LISTA DE USER-AGENTS
# - Lo que hace: Almacena cadenas de texto que simulan ser navegadores Chrome reales y recientes en sistemas Windows/Mac.
# - Para qué sirve: Engaña a los firewalls (como Cloudflare) haciéndoles creer que la conexión proviene de un humano normal y no de un script automatizado (Playwright).
# - Metodología: Suplantación de identidad (Spoofing) y ofuscación en la capa de navegación HTTP[cite: 11, 14].
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

# Expresiones Regulares (Regex) universales para variables hedónicas del INEI
# [COMENTARIO] PATRONES DE EXTRACCIÓN ESTRUCTURAL (REGEX)
# - Lo que hace: Compila reglas matemáticas de búsqueda de texto (Regex) que ignoran mayúsculas/minúsculas.
# - Para qué sirve: Aísla y extrae únicamente los valores numéricos limpios (metros cuadrados, números de habitaciones, baños, etc.) que están enterrados dentro de descripciones textuales desordenadas.
# - Metodología: Procesamiento de Lenguaje Natural (NLP) y normalización tipológica. Transforma texto crudo no estructurado en las variables estructurales discretas que exige la matriz (X) del modelo de regresión hedónica[cite: 11, 14].
REGEX_PATTERNS = {
    "id_anuncio": re.compile(r"(?:-|_id_|/)(\d{5,12})(?:\.html|/|$)"),
    "area_total": re.compile(
    r"(\d+(?:[.,]\d+)?)\s*m(?:2|²)\s*(?:totales|total|de\s+terreno|terreno)\b",
    re.IGNORECASE
),
    "area_construida": re.compile(
    r"(\d+(?:[.,]\d+)?)\s*m(?:2|²)\s*(?:construidos|techados|cubiertos|construida)\b",
    re.IGNORECASE
),
    "dormitorios": re.compile(r"(\d+)\s*(?:dorm|hab|cuarto)", re.IGNORECASE),
    "banos": re.compile(r"(\d+)\s*(?:baño|bano)", re.IGNORECASE),
    "estacionamientos": re.compile(r"(\d+)\s*(?:estac|cochera|garaje)", re.IGNORECASE),
    "antiguedad": re.compile(r"(\d+)\s*años?\s*(?:de\s*antigüedad)?", re.IGNORECASE),
}

# ==============================================================================
# PERFILES DE PORTALES: Un solo motor universal para múltiples sitios web
# ==============================================================================
# [COMENTARIO] DICCIONARIO UNIVERSAL DE CONFIGURACIÓN DE PORTALES
# - Lo que hace: Estructura un diccionario anidado que contiene las URLs objetivo y los selectores CSS/XPath específicos para cada plataforma inmobiliaria (Babilonia y Urbania).
# - Para qué sirve: Le dicta al orquestador principal (main.py) exactamente dónde hacer clic y de qué etiquetas HTML raspar los datos sin necesidad de programar un bot diferente por cada portal.
# - Metodología: Patrón de Diseño Guiado por Configuración (Configuration-Driven Architecture). Desacopla la lógica algorítmica de extracción de las reglas visuales estáticas, lo que otorga selectores semánticos robustos ante rediseños web (evitando el colapso del scraper)[cite: 14].
PERFILES_PORTALES = {
    "babilonia": {
        # [COMENTARIO] PARÁMETROS DE NAVEGACIÓN Y PAGINACIÓN (BABILONIA)
        # - Lo que hace: Mapea las rutas base de búsqueda de inmuebles y define las clases de los botones para cambiar de página.
        # - Para qué sirve: Orienta al bot por las secciones de casas, departamentos y terrenos, e identifica visualmente cómo avanzar a la siguiente pestaña de resultados.
        # - Metodología: Rastreo automatizado escalable (Web Crawling) mediante reconocimiento de patrones de paginación asíncrona.
        "dominio": "https://babilonia.pe",
        "urls_semilla": [
            ("casa", "https://babilonia.pe/inmuebles/casas-en-venta-en-lima"),
            ("departamento", "https://babilonia.pe/inmuebles/departamentos-en-venta-en-lima"),
            ("terreno", "https://babilonia.pe/inmuebles/terrenos-en-venta-en-lima"),
        ],
        "selector_enlaces_listado": 'a[href*="/inmueble/"], a[href*="/propiedades/"], div[class*="card"] a[href]',
        "filtro_url_inmueble": "/inmueble/",
        "selector_siguiente_pagina": [
            'a[rel="next"]',
            'button[aria-label*="Next"]',
            'button[aria-label*="Siguiente"]',
            'li.pagination-next a',
            'a:has-text("Siguiente")'
        ],
        # [COMENTARIO] REGLAS DE EXTRACCIÓN SEMÁNTICA (BABILONIA)
        # - Lo que hace: Almacena listas de posibles selectores CSS priorizados para capturar cada atributo clave del inmueble en el detalle de la página.
        # - Para qué sirve: Provee un mecanismo de respaldo (fallback); si el portal cambia el nombre de la clase '.price' a '.data-qa-price', el bot intentará automáticamente con la siguiente regla sin detenerse.
        # - Metodología: Extracción de datos resiliente tipo "Fail-over" basado en jerarquía de selectores DOM[cite: 14].
        "reglas_extraccion": {
            "titulo": ['h1', '[class*="title-property"]', '[class*="header-title"]'],
            "estado_proyecto": ['[class*="project-status"]', '[class*="badge"]', '[class*="tag"]'],
            "precio_general": ['[class*="price"]', '[data-qa*="price"]', 'h2:has-text("$")', 'h2:has-text("S/")'],
            "ubicacion": ['[class*="address"]', '[class*="location"]', 'h2[class*="subtitle"]', '#map-section'],
            "datos_principales_generales": ['[class*="features"]', '[class*="details-grid"]', 'ul[class*="characteristics"]'],
            "otras_caracteristicas": ['[class*="amenities"]', '[class*="facilities"]', '[class*="other-features"]'],
            "caracteristicas": ['[class*="general-features"]', '[class*="property-details"]', 'section[class*="features"]'],
            "comodidades": ['[class*="comforts"]', '[class*="amenities-list"]', '[class*="icons-grid"]'],
            "descripcion": ['[class*="description"]', '#description', 'article', 'div[class*="read-more"]']
        }
    },
    "urbania": {
        # [COMENTARIO] CONFIGURACIÓN REPLICABLE (URBANIA)
        # - Lo que hace: Mantiene la misma estructura algorítmica del diccionario "babilonia", pero adaptando los selectores (incluyendo XPaths) a la infraestructura visual particular del grupo Navent/Urbania.
        # - Para qué sirve: Facilita que el mismo orquestador procese indistintamente portales con diseños internos totalmente distintos, integrando todo en una base maestra única.
        # - Metodología: Pipeline desacoplado con estandarización de contratos de datos.
        "dominio": "https://urbania.pe",
        "urls_semilla": [
            ("casa", "https://urbania.pe/buscar/venta-de-casas-en-lima"),
            ("departamento", "https://urbania.pe/buscar/venta-de-departamentos-en-lima"),
            ("terreno", "https://urbania.pe/buscar/venta-de-terrenos-en-lima"),
        ],
        "selector_enlaces_listado": '[data-to-posting], a[href*="/propiedades/"]',
        "filtro_url_inmueble": "/propiedades/",
        "selector_siguiente_pagina": ['a[data-qa="PAGING_NEXT"]'],
        "reglas_extraccion": {
            "titulo": ['.title-h1-development', '.title-property', 'h1'],
            "estado_proyecto": ['.status-delivery-and-financing', '.status-delivery'],
            "precio_general": ['.price-operation-type', '.unitPrice', '.price-items', '.transaction-price'],
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