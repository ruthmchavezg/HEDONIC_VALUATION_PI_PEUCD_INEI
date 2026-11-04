# [COMENTARIO] IMPORTACIÓN DE LIBRERÍAS
# Lo que hace: Importa módulos estándar de Python para procesamiento de texto (re), estructuras de datos (json), registro de eventos (logging) y manejo de rutas web (urllib.parse), además de las expresiones regulares globales del proyecto.
# Para qué sirve: Proporciona las herramientas fundamentales para analizar el código fuente, limpiar caracteres y leer los metadatos ocultos sin depender de librerías externas de terceros.
# Metodología: Arquitectura guiada por configuración (Configuration-Driven) y uso de Biblioteca Estándar para asegurar bajo acoplamiento y alta eficiencia de ejecución[cite: 13, 14].
import re
import json
import logging
from urllib.parse import urljoin
from config.settings import REGEX_PATTERNS

# [COMENTARIO] FUNCIÓN: extraer_texto_robusto_pw
# Lo que hace: Inyecta y ejecuta una función en JavaScript directamente en el navegador (evaluación de página) para recorrer todos los nodos "hijos" de un elemento HTML, extrayendo únicamente el texto puro y filtrando botones inútiles.
# Para qué sirve: Permite capturar las descripciones y características del inmueble ignorando etiquetas ocultas o basura visual del diseño, garantizando un texto limpio para el análisis NLP[cite: 14].
# Metodología: Recorrido Recursivo del DOM (Recursive DOM Traversal) y Sanitización en el lado del cliente (Client-side Data Cleansing).
def extraer_texto_robusto_pw(page, selectores: list) -> str:
    """Tu extractor recursivo de nodos DOM que limpia texto e ignora botones de interfaz."""
    for selector in selectores:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                textos_crudos = locator.evaluate("""
                    (element) => {
                        function getTexts(el) {
                            let texts = [];
                            for (let node of el.childNodes) {
                                if (node.nodeType === 3) { 
                                    texts.push(node.textContent);
                                } else if (node.nodeType === 1) { 
                                    texts = texts.concat(getTexts(node));
                                }
                            }
                            return texts;
                        }
                        return getTexts(element);
                    }
                """)
                if textos_crudos:
                    textos_limpios = [re.sub(r'\s+', ' ', t).strip() for t in textos_crudos if t.strip()]
                    ignorar = {'Leer descripción completa -', 'Ver más', 'Leer más', 'Ver descripción completa'}
                    textos_filtrados = [t for t in textos_limpios if t not in ignorar]
                    if textos_filtrados:
                        return " | ".join(textos_filtrados)
        except Exception:
            continue
    return "No especificado"

# [COMENTARIO] FUNCIÓN: expandir_textos_ocultos
# Lo que hace: Busca botones específicos en la pantalla ("Ver más", "Leer descripción completa"), hace scroll hasta ellos y los cliquea.
# Para qué sirve: Despliega el texto completo de las descripciones que los portales suelen ocultar para ahorrar espacio visual, asegurando que no se pierda información valiosa.
# Metodología: Interacción automatizada de Interfaz de Usuario (UI Automation) y Emulación Humana (simulando clics y tiempos de espera).
def expandir_textos_ocultos(page):
    """Expande botones de 'Ver más' o 'Leer más' tanto en Babilonia como en Urbania."""
    try:
        botones = page.locator('text="Ver más", text="Leer más", text="Leer descripción completa", text="Ver descripción completa"')
        for i in range(botones.count()):
            boton = botones.nth(i)
            if boton.is_visible():
                boton.scroll_into_view_if_needed()
                boton.click(timeout=1500)
                page.wait_for_timeout(500)
    except Exception:
        pass

# [COMENTARIO] FUNCIÓN: extraer_unidades_detalladas_pw
# Lo que hace: Detecta si el anuncio es un proyecto con varias unidades (ej. edificio en venta), hace clic en cada pestaña (1 dorm, 2 dorm, etc.) y extrae el precio y características de cada sub-departamento.
# Para qué sirve: Evita que un anuncio agrupe múltiples precios y áreas en una sola fila, desglosando cada unidad de forma independiente.
# Metodología: Estructuración Tabular Atómica (1 fila = 1 inmueble tasable). Garantiza la integridad de la matriz econométrica para no sesgar el modelo hedónico con valores mezclados[cite: 14].
def extraer_unidades_detalladas_pw(page) -> list:
    """Extrae sub-unidades cuando el anuncio corresponde a un proyecto inmobiliario."""
    unidades_extraidas = []
    pestanas = page.locator('button[class*="unit-selection-module__rooms-button"], [class*="project-units"] button')
    if pestanas.count() == 0:
        return []

    for i in range(pestanas.count()):
        try:
            pestana = pestanas.nth(i)
            nombre_pestana = pestana.inner_text()
            pestana.scroll_into_view_if_needed()
            pestana.click()
            page.wait_for_timeout(1200)
            
            tarjetas = page.locator('div[class*="unit-selection-module__cardContainer"], [class*="unit-card"]')
            for j in range(tarjetas.count()):
                tarjeta = tarjetas.nth(j)
                tipo = tarjeta.locator('.unitPropertyType').inner_text() if tarjeta.locator('.unitPropertyType').count() > 0 else ""
                precio = tarjeta.locator('.unitPrice').inner_text() if tarjeta.locator('.unitPrice').count() > 0 else ""
                if precio:
                    caracteristicas = tarjeta.locator('div[class*="unitFeatures"]').inner_text() if tarjeta.locator('div[class*="unitFeatures"]').count() > 0 else ""
                    features_limpio = re.sub(r'\s+', ' ', caracteristicas).strip().replace('\n', ' | ')
                    unidades_extraidas.append({
                        "dormitorios": nombre_pestana.strip(),
                        "tipo_unidad": tipo.strip(),
                        "precio_unidad": precio.strip(),
                        "detalles_unidad": features_limpio
                    })
        except Exception:
            continue
    return unidades_extraidas

# [COMENTARIO] FUNCIÓN: extraer_metadatos_json_oculto
# Lo que hace: Lee el código fuente de la página buscando etiquetas script 'application/ld+json' y coordenadas incrustadas, extrayendo datos estructurados directamente del código en lugar de la vista.
# Para qué sirve: Obtiene latitud y longitud exactas (indispensables para OpenStreetMap) y el precio en formato numérico puro, saltándose cualquier cambio cosmético en la web.
# Metodología: Extracción de Estado Interno (Hidden JSON / Server-Side Rendering Hydration) e Intercepción de Datos Estructurados para mayor resiliencia ante rediseños del portal[cite: 14].
def extraer_metadatos_json_oculto(page) -> dict:
    """
    Extrae datos estructurados ocultos (JSON-LD y objetos JS) de Babilonia y Urbania:
    Coordenadas GPS (latitud, longitud), precio limpio, moneda y descripción.
    """
    meta = {"latitud": None, "longitud": None, "precio_json": None, "moneda_json": None, "descripcion_json": None, "titulo_json": None}
    try:
        html = page.content()
        
        # 1. Buscar bloques <script type="application/ld+json">
        scripts = page.locator('script[type="application/ld+json"]')
        for i in range(scripts.count()):
            try:
                raw_json = scripts.nth(i).inner_text()
                data = json.loads(raw_json)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if not meta["titulo_json"] and item.get("name"):
                        meta["titulo_json"] = str(item.get("name"))
                    if not meta["descripcion_json"] and item.get("description"):
                        meta["descripcion_json"] = str(item.get("description"))
                    if "geo" in item and isinstance(item["geo"], dict):
                        lat = item["geo"].get("latitude")
                        lng = item["geo"].get("longitude")
                        if lat and lng:
                            meta["latitud"] = float(lat)
                            meta["longitud"] = float(lng)
                    if "offers" in item:
                        offers = item["offers"]
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict):
                            p = offers.get("price") or offers.get("lowPrice")
                            c = offers.get("priceCurrency")
                            if p:
                                meta["precio_json"] = float(p)
                            if c in ["USD", "PEN"]:
                                meta["moneda_json"] = c
            except Exception:
                continue

        # 2. Respaldo Regex sobre HTML crudo para coordenadas GPS en Lima Metropolitana
        if not meta["latitud"]:
            m_coord = re.search(r'"lat(?:itude)?"\s*:\s*(-1[123]\.\d+)\s*,\s*"(?:lng|lon|longitude)"\s*:\s*(-7[67]\.\d+)', html)
            if m_coord:
                meta["latitud"] = float(m_coord.group(1))
                meta["longitud"] = float(m_coord.group(2))
            else:
                m_map = re.search(r'center=(-1[123]\.\d+)(?:%2C|,)(-7[67]\.\d+)', html)
                if m_map:
                    meta["latitud"] = float(m_map.group(1))
                    meta["longitud"] = float(m_map.group(2))
    except Exception:
        pass
    return meta

# [COMENTARIO] FUNCIÓN: limpiar_precio_moneda
# Lo que hace: Analiza un texto de precio (ej. "S/ 150,000" o "USD 50.000") o el JSON oculto, extrae la moneda detectada y devuelve el valor matemático validado.
# Para qué sirve: Filtra registros basura (precios menores a 1000) y separa la moneda del número, preparándolos para la conversión automática al tipo de cambio del BCRP.
# Metodología: Limpieza de Datos (Data Cleansing) y Estandarización de divisas.
def limpiar_precio_moneda(texto_precio: str, meta_json: dict) -> tuple:
    """Obtiene moneda ('USD' o 'PEN') y monto numérico validado."""
    if meta_json.get("precio_json") and meta_json["precio_json"] > 1000:
        return meta_json.get("moneda_json") or "USD", float(meta_json["precio_json"])

    if not texto_precio or texto_precio == "No especificado":
        return None, None

    bloque = texto_precio.split("·")[0].split("|")[0].upper()
    moneda = "USD" if ("USD" in bloque or "US$" in bloque or "$" in bloque) else "PEN"
    numeros = re.findall(r"\d+(?:[.,]\d{3})*(?:[.,]\d+)?", bloque)
    if not numeros:
        return None, None

    monto_str = re.sub(r"[^\d]", "", numeros[0])
    try:
        monto = float(monto_str)
        return (moneda, monto) if monto > 1000 else (None, None)
    except ValueError:
        return None, None

# [COMENTARIO] FUNCIÓN: parsear_atributos_regex
# Lo que hace: Ejecuta los patrones Regex (área, baños, dormitorios, antigüedad) definidos globalmente sobre un bloque de texto consolidado.
# Para qué sirve: Transforma el texto crudo en columnas numéricas perfectas para alimentar la ecuación hedónica sin generar errores de tipo en los algoritmos de Machine Learning.
# Metodología: Extracción de Información Estructurada (Pattern Matching / Regex Parsing) a partir de lenguaje natural no estructurado[cite: 14].
def parsear_atributos_regex(texto_combinado: str) -> dict:
    """Extrae las variables estructurales numéricas mediante las Regex del proyecto."""
    t = (texto_combinado or "").lower()
    m_tot = REGEX_PATTERNS["area_total"].search(t)
    m_con = REGEX_PATTERNS["area_construida"].search(t)
    m_dor = REGEX_PATTERNS["dormitorios"].search(t)
    m_ban = REGEX_PATTERNS["banos"].search(t)
    m_est = REGEX_PATTERNS["estacionamientos"].search(t)
    m_ant = REGEX_PATTERNS["antiguedad"].search(t)

    antiguedad = int(m_ant.group(1)) if m_ant else (0 if ("estreno" in t or "en construcción" in t) else None)

    return {
        "area_total_m2": float(m_tot.group(1).replace(",", ".")) if m_tot else None,
        "area_construida_m2": float(m_con.group(1).replace(",", ".")) if m_con else None,
        "dormitorios_num": int(m_dor.group(1)) if m_dor else None,
        "banos_num": int(m_ban.group(1)) if m_ban else None,
        "estacionamientos_num": int(m_est.group(1)) if m_est else None,
        "antiguedad_anos": antiguedad,
    }

# [COMENTARIO] FUNCIÓN: recolectar_enlaces_portal
# Lo que hace: Navega a la URL de listado principal (ej. Casas en Lima), hace un scroll progresivo para cargar todos los elementos dinámicos, captura las URLs de las tarjetas, y luego detecta el botón de "Siguiente" para avanzar a la próxima página y repetir el ciclo.
# Para qué sirve: Genera el catálogo completo de anuncios disponibles en el portal para posteriormente recorrerlos uno por uno y aplicar el filtro incremental de duplicados.
# Metodología: Rastreo Web Secuencial (Web Crawling) con simulación de comportamiento humano (Jitter Gaussiano) para evadir bloqueos de IP y forzar el renderizado de carga diferida (Lazy Loading)[cite: 14].
def recolectar_enlaces_portal(engine, perfil_portal: dict, url_semilla: str, max_paginas: int) -> list:
    """Recolecta enlaces de propiedades haciendo scroll hasta el fondo y manejando paginación."""
    enlaces_totales = set()
    url_actual = url_semilla
    dominio = perfil_portal["dominio"]
    selector_cards = perfil_portal["selector_enlaces_listado"]
    filtro = perfil_portal["filtro_url_inmueble"]

    for pagina_actual in range(1, max_paginas + 1):
        logging.info(f"[+] [{dominio}] Recolectando enlaces - Página {pagina_actual}/{max_paginas}: {url_actual}")
        engine.navegar_seguro(url_actual)

        # Scroll progresivo hasta el fondo para activar carga diferida (Lazy Loading) y paginación
        engine.page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5);")
        engine.page.wait_for_timeout(1200)
        engine.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        engine.page.wait_for_timeout(2000)

        nodos = engine.page.locator(selector_cards)
        for i in range(nodos.count()):
            nodo = nodos.nth(i)
            ruta = nodo.get_attribute("data-to-posting") or nodo.get_attribute("href")
            if ruta and filtro in ruta:
                ruta_limpia = ruta.split("?")[0]
                url_completa = urljoin(dominio, ruta_limpia)
                enlaces_totales.add(url_completa)

        logging.info(f"    -> Acumulados hasta ahora: {len(enlaces_totales)} enlaces únicos.")
        if pagina_actual == max_paginas:
            break

        # Intentar avanzar a la siguiente página
        avanzado = False
        for sel_next in perfil_portal["selector_siguiente_pagina"]:
            boton_sig = engine.page.locator(sel_next).first
            if boton_sig.count() > 0 and boton_sig.is_visible():
                href_sig = boton_sig.get_attribute("href")
                if href_sig and not href_sig.startswith("javascript"):
                    url_actual = urljoin(dominio, href_sig)
                    avanzado = True
                    break
                else:
                    # En SPAs como Babilonia donde el botón actualiza la URL por JS
                    boton_sig.scroll_into_view_if_needed()
                    boton_sig.click()
                    engine.page.wait_for_timeout(3000)
                    url_actual = engine.page.url
                    avanzado = True
                    break

        if not avanzado:
            # Respaldo por parámetro de página estándar
            sep = "&" if "?" in url_semilla else "?"
            url_actual = f"{url_semilla}{sep}page={pagina_actual + 1}"

    return list(enlaces_totales)