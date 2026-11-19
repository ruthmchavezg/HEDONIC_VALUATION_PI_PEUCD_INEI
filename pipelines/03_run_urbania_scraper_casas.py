from playwright.sync_api import sync_playwright
#from playwright_stealth import Stealth
import pandas as pd
import time
import re
import random
import os
import cv2
import pytesseract
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from pathlib import Path

# ==========================================
# CONFIGURACIÓN DE OCR Y GEOCODIFICACIÓN
# ==========================================
RUTA_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(RUTA_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = RUTA_TESSERACT

geolocator = Nominatim(user_agent="urbania_hedonic_scraper_casas", timeout=10)
geocode_safe = RateLimiter(geolocator.geocode, min_delay_seconds=1.2)

# ==========================================
# 1. REGLAS DE EXTRACCIÓN (ESTRUCTURA CASAS)
# ==========================================
REGLAS_EXTRACCION = {
    'titulo': [
        'h1.title-h1-development',
        'h2.title-type-sup-property', 
        '.title-property', 
        'h1'
    ],
    'estado_proyecto': [
        '.status-delivery-and-financing', 
        '.status-delivery',
        'span.label'
    ],
    'precio_general': [
        '.list-prices',             
        '.block-price-container',   
        '.price-value',             
        '.price-container-property', 
        '.price-items-container', 
        '.price-operation-type'
    ],
    'ubicacion': [
        'h4#ref-map', 
        'div[class*="section-location-property"] h4',
        '.section-location-property', 
        '.title-location'
    ],
    'datos_principales_generales': [
        'div[class*="development-features-grid"]', 
        'ul[class*="section-icon-features-property"]',
        '.main-features-grid', 
        'ul.main-features'
    ],
    'comodidades_proyecto': [ 
        'div[class*="devFeaturesNew-module__icon-label"]', 
        'div[class*="devFeaturesNew-module__icons-grid"]'
    ],
    'otras_caracteristicas_proyecto': [ 
        'div[class*="devFeaturesNew-module__item-grid"]',
        'xpath=//h4[contains(text(), "Otras características")]/following-sibling::div',
        'xpath=//h3[contains(text(), "Otras características")]/following-sibling::div'
    ],
    'descripcion': [
        'div[class*="description-module__wrapper-description"]', 
        '#longDescription', 
        '.box-description'
    ],
    'datos_anunciante': [
        'ul[class*="publisherCodes-module__publisher-codes-list"]', 
        'li[class*="publisherCodes-module__publisher-codes-item"]',
        '.publisher-info'
    ]
}

# ==========================================
# 2. FUNCIONES DE GEO-DETECCIÓN Y OCR
# ==========================================
def resolver_por_ocr(page):
    img_temp = "temp_mapa_ocr_casas.png"
    try:
        selectores_mapa = ['.section-location-property', '#ref-map', 'div[class*="map-container"]', 'iframe[src*="google"]']
        mapa_el = None
        for sel in selectores_mapa:
            loc = page.locator(sel).first
            if loc.count() > 0:
                mapa_el = loc
                break
                
        if not mapa_el: return None
            
        mapa_el.scroll_into_view_if_needed()
        page.wait_for_timeout(1500)
        mapa_el.screenshot(path=img_temp)
        
        img = cv2.imread(img_temp)
        gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        umbral = cv2.threshold(gris, 160, 255, cv2.THRESH_BINARY)[1]
        texto = pytesseract.image_to_string(umbral, config='--psm 6')
        
        if os.path.exists(img_temp): os.remove(img_temp)
            
        lineas = [re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s\.]', '', l).strip() for l in texto.split('\n')]
        vias = []
        for l in lineas:
            if len(l) > 4 and re.search(r'\b(Av|Avenida|Calle|Jr|Jiron|Jirón|Pje|Pasaje|Prol|Ca\.)\b', l, re.IGNORECASE):
                if l not in vias: vias.append(l)
                    
        if len(vias) >= 2:
            query_cruce = f"{vias[0]} y {vias[1]}, Lima, Perú"
            loc = geocode_safe(query_cruce)
            if loc: return f"{loc.latitude},{loc.longitude}"
        elif len(vias) == 1:
            query_via = f"{vias[0]}, Lima, Perú"
            loc = geocode_safe(query_via)
            if loc: return f"{loc.latitude},{loc.longitude}"
                
    except Exception:
        if os.path.exists(img_temp):
            try: os.remove(img_temp)
            except: pass
    return None

def resolver_por_geopy_direccion(direccion_texto):
    if not direccion_texto or "No especific" in str(direccion_texto): 
        return None
    try:
        limpio = str(direccion_texto).split('|')[0]
        # ELIMINA LOS METROS CUADRADOS que confunden al satélite
        limpio = re.sub(r'\d+\s*m²?.*', '', limpio, flags=re.IGNORECASE)
        # Limpia los símbolos de moneda y espacios dobles
        limpio = re.sub(r'\b(S/|\$|USD)\b', '', limpio).strip()
        limpio = re.sub(r'\s+', ' ', limpio).strip()
        
        if len(limpio) < 4:
            return None
            
        query = f"{limpio}, Lima, Perú"
        loc = geocode_safe(query)
        if loc: 
            return f"{loc.latitude},{loc.longitude}"
    except Exception: 
        pass
    return None

def extraer_coordenadas_completo(page, direccion_texto):
    try:
        # 1. EL CLICK QUIRÚRGICO AL MAPA ESTÁTICO
        mapa_estatico = page.locator('#static-map, .article-map, #ref-map').first
        if mapa_estatico.count() > 0:
            mapa_estatico.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            try:
                mapa_estatico.click(force=True)
                page.wait_for_timeout(2500) 
            except Exception:
                pass

        # 2. Cacería en Iframes inyectados
        iframes = page.locator('iframe')
        for i in range(iframes.count()):
            src = iframes.nth(i).get_attribute('src') or ""
            match_pb = re.search(r'!3d(-1[1-3]\.\d{4,15})!4d(-7[6-8]\.\d{4,15})', src)
            if match_pb: return f"{match_pb.group(1)},{match_pb.group(2)}"
            match_iframe = re.search(r'(?:q|ll|center|sll)=(-1[1-3]\.\d{4,15})[,\s%]+(-7[6-8]\.\d{4,15})', src)
            if match_iframe: return f"{match_iframe.group(1)},{match_iframe.group(2)}"

        # 3. Caza en atributos ocultos del DOM
        coords_dom = page.evaluate(r"""() => {
            let el = document.querySelector('[data-lat][data-lng], [data-latitude][data-longitude]');
            if (el) {
                let lat = el.getAttribute('data-lat') || el.getAttribute('data-latitude');
                let lng = el.getAttribute('data-lng') || el.getAttribute('data-longitude');
                if (lat && lng && lat.startsWith('-1')) return `${lat},${lng}`;
            }
            return null;
        }""")
        if coords_dom: return coords_dom

        # 4. Enlaces escondidos hacia Google Maps
        enlaces_mapa = page.locator('a[href*="google.com/maps"], a[href*="maps.google"]')
        for i in range(enlaces_mapa.count()):
            href = enlaces_mapa.nth(i).get_attribute('href') or ""
            match_pb_href = re.search(r'!3d(-1[1-3]\.\d{4,15})!4d(-7[6-8]\.\d{4,15})', href)
            if match_pb_href: return f"{match_pb_href.group(1)},{match_pb_href.group(2)}"
            match_href = re.search(r'(-1[1-3]\.\d{4,15})[,\s]+(-7[6-8]\.\d{4,15})', href)
            if match_href: return f"{match_href.group(1)},{match_href.group(2)}"

        # 5. Fallback a Regex puro en el HTML
        html = page.content()
        match_lat = re.search(r'(-1[1-3]\.\d{4,15})[^\d\.\-]{1,60}?(-7[6-8]\.\d{4,15})', html)
        if match_lat: return f"{match_lat.group(1)},{match_lat.group(2)}"

        # 6. Fallback OCR
        coords_ocr = resolver_por_ocr(page)
        if coords_ocr: return coords_ocr

        # 7. Fallback Geopy
        coords_geopy = resolver_por_geopy_direccion(direccion_texto)
        if coords_geopy: return coords_geopy

    except Exception: 
        pass
    return "No especificado"

# ==========================================
# 3. FUNCIONES AUXILIARES DE TEXTOS Y CLICS
# ==========================================
def extraer_texto_robusto_pw(page, selectores):
    for selector in selectores:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                textos_crudos = locator.evaluate("""
                    (element) => {
                        function getTexts(el) {
                            let texts = [];
                            for (let node of el.childNodes) {
                                if (node.nodeType === 3) { texts.push(node.textContent); } 
                                else if (node.nodeType === 1) { texts = texts.concat(getTexts(node)); }
                            }
                            return texts;
                        }
                        return getTexts(element);
                    }
                """)
                if textos_crudos:
                    textos_limpios = [re.sub(r'\s+', ' ', t).strip() for t in textos_crudos if t.strip()]
                    textos_filtrados = [t for t in textos_limpios if t not in ['Leer descripción completa -', 'Leer descripción completa', 'Ver más', 'Ver menos']]
                    if textos_filtrados: return " | ".join(textos_filtrados)
        except Exception: continue
    return "No especificado"

def extraer_unidades_detalladas_pw(page):
    unidades_extraidas = []
    pestanas = page.locator('button[class*="unit-selection-module__rooms-button"]')
    if pestanas.count() == 0: return []
    for i in range(pestanas.count()):
        try:
            pestana = pestanas.nth(i)
            nombre_pestana = pestana.inner_text().strip()
            pestana.scroll_into_view_if_needed()
            pestana.click(timeout=2000)
            page.wait_for_timeout(1500) 
            tarjetas = page.locator('div[class*="unit-selection-module__cardContainer"]')
            for j in range(tarjetas.count()):
                tarjeta = tarjetas.nth(j)
                tipo = tarjeta.locator('.unitPropertyType').inner_text().strip() if tarjeta.locator('.unitPropertyType').count() > 0 else ""
                precio = tarjeta.locator('.unitPrice').inner_text().strip() if tarjeta.locator('.unitPrice').count() > 0 else ""
                if precio: 
                    caracteristicas = tarjeta.locator('div[class*="unitFeatures"]').inner_text() if tarjeta.locator('div[class*="unitFeatures"]').count() > 0 else ""
                    features_limpio = re.sub(r'\s+', ' ', caracteristicas).strip().replace('\n', ' | ')
                    unidades_extraidas.append({"dormitorios": nombre_pestana, "tipo_unidad": tipo, "precio_unidad": precio, "detalles_unidad": features_limpio})
        except Exception: continue
    return unidades_extraidas

def expandir_textos_ocultos(page):
    selectores_botones = ['button[class*="viewmoreButton"]', 'button[class*="view-more-dev-feature"]', 'text="Leer descripción completa"', 'text="Leer descripción completa -"', 'text="Ver más"']
    for selector in selectores_botones:
        try:
            botones = page.locator(selector)
            for i in range(botones.count()):
                boton = botones.nth(i)
                if boton.is_visible():
                    boton.scroll_into_view_if_needed()
                    boton.click(timeout=1500)
                    page.wait_for_timeout(600)
        except Exception: continue

def extraer_caracteristicas_dinamicas(page):
    datos_extraidos = {}
    try:
        botones = page.locator('button[class*="generalFeaturesProperty-module__button-general-features"]')
        if botones.count() == 0: return datos_extraidos
        for i in range(botones.count()):
            boton = botones.nth(i)
            span_titulo = boton.locator('span[class*="text-title"]')
            nombre_crudo = span_titulo.inner_text().strip() if span_titulo.count() > 0 else boton.inner_text().strip()
            nombre_columna = nombre_crudo.lower().replace(" ", "_").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
            
            boton.scroll_into_view_if_needed()
            boton.click(timeout=2000)
            page.wait_for_timeout(800) 
            
            items = page.locator('span[class*="generalFeaturesProperty-module__description-text"]')
            textos_pestana = []
            for j in range(items.count()):
                item = items.nth(j)
                if item.is_visible():
                    val = item.inner_text().strip()
                    if val and val not in textos_pestana: textos_pestana.append(val)
            if textos_pestana: datos_extraidos[nombre_columna] = " | ".join(textos_pestana)
    except Exception: pass
    return datos_extraidos

def recolectar_enlaces(page, url_base, pagina_inicio=1, paginas_a_recorrer=13):
    enlaces_totales = set()
    for i in range(pagina_inicio, pagina_inicio + paginas_a_recorrer):
        print(f"\n[+] Recolectando enlaces de la página {i}...")
        url_actual = url_base if i == 1 else f"{url_base}?page={i}"
        if i > 1:
            page.wait_for_timeout(random.randint(5000, 8000))
        page.goto(url_actual, wait_until="domcontentloaded")
        
        try: page.wait_for_selector('[data-to-posting]', timeout=60000)
        except Exception: 
            print("  [!] Cloudflare posible. Esperando 20s...")
            page.wait_for_timeout(20000)
        
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3);")
        page.wait_for_timeout(1200)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        page.wait_for_timeout(2000)
        
        tarjetas = page.locator('[data-to-posting]')
        if tarjetas.count() == 0: break
        for j in range(tarjetas.count()):
            ruta = tarjetas.nth(j).get_attribute('data-to-posting')
            if ruta: enlaces_totales.add(f"https://urbania.pe{ruta.split('?')[0]}")
    return list(enlaces_totales)

# ==========================================
# 4. PROCESAMIENTO PRINCIPAL (CASAS)
# ==========================================
def ejecutar_scraper():
    URL_BASE = "https://urbania.pe/buscar/alquiler-de-casas-en-lima"
    PAGINA_INICIO = 1 
    CANTIDAD_PAGINAS = 13 
    
    # --- 1. CONFIGURACIÓN DE RUTAS DE GUARDADO ---
    directorio_destino = Path("data/raw/portals")
    directorio_destino.mkdir(parents=True, exist_ok=True)
    
    archivo_backup = directorio_destino / "backup_casas_urbania.csv"
    archivo_final = directorio_destino / "bronce_alquileres_urbania_casas.csv"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="msedge", args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={'width': 1366, 'height': 768}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        lista_urls = recolectar_enlaces(page, URL_BASE, pagina_inicio=PAGINA_INICIO, paginas_a_recorrer=CANTIDAD_PAGINAS)
        print(f"\n¡Total de casas únicas encontradas en la web: {len(lista_urls)}!")
        
        # --- SISTEMA DE REANUDACIÓN INTELIGENTE ---
        datos_brutos = []
        if os.path.exists(archivo_backup):
            print(f"\n[+] ¡Respaldo detectado! Cargando {archivo_backup} a la memoria...")
            df_previo = pd.read_csv(archivo_backup)
            if 'url' in df_previo.columns:
                datos_brutos = df_previo.to_dict('records')
                urls_listas = set(df_previo['url'].tolist())
                # Filtrado ultrarrápido
                lista_urls = [u for u in lista_urls if u not in urls_listas]
                print(f"[*] Se restaron {len(urls_listas)} casas que ya están a salvo.")
                print(f"[*] ¡Arrancando directamente con las {len(lista_urls)} casas que faltan!\n")
        
        for index, enlace in enumerate(lista_urls, 1):
            print(f"[{index}/{len(lista_urls)}] Procesando casa: {enlace}")
            try:
                page.wait_for_timeout(random.randint(1500, 3000))
                page.goto(enlace, wait_until="domcontentloaded", timeout=45000) 
                page.wait_for_timeout(random.randint(1800, 2600)) 
                
                datos_estandar = {}
                for campo, selectores in REGLAS_EXTRACCION.items():
                    datos_estandar[campo] = extraer_texto_robusto_pw(page, selectores)
                
                pestanas_dinamicas = extraer_caracteristicas_dinamicas(page)
                expandir_textos_ocultos(page)
                unidades = extraer_unidades_detalladas_pw(page)
                
                # ¡Extracción de Coordenadas integrada!
                coords_str = extraer_coordenadas_completo(page, datos_estandar.get('ubicacion', ''))
                
                inmueble = {'url': enlace}
                try:
                    img_url = page.locator('meta[property="og:image"]').get_attribute('content', timeout=2000)
                    inmueble['imagen_principal'] = img_url if img_url else "No disponible"
                except Exception:
                    inmueble['imagen_principal'] = "No disponible"
                
                inmueble.update(datos_estandar)
                inmueble['unidades_detalladas'] = unidades
                for columna, valor in pestanas_dinamicas.items(): inmueble[columna] = valor
                inmueble['coordenadas'] = coords_str
                
                datos_brutos.append(inmueble)
                
                # Respaldo cada 25 casas (Garantizando Coordenadas al final)
                if len(datos_brutos) % 25 == 0:
                    df_backup = pd.DataFrame(datos_brutos)
                    if 'coordenadas' in df_backup.columns:
                        df_backup = df_backup[[c for c in df_backup.columns if c != 'coordenadas'] + ['coordenadas']]
                    df_backup.to_csv(archivo_backup, index=False, encoding='utf-8-sig')
                    print(f"  [!] Respaldo actualizado: {len(datos_brutos)} casas a salvo.")

                # Enfriamiento cada 200 nuevos raspados (es una muestra menor)
                if index % 200 == 0:
                    tiempo_descanso = random.randint(120000, 180000)
                    print(f"\n[zzz] Enfriando conexión por {round(tiempo_descanso/60000, 1)} minutos...")
                    page.wait_for_timeout(tiempo_descanso)
                
            except Exception as e:
                print(f"  -> Error o Timeout saltando casa: {e}")
                continue
                
        browser.close()

    print("\n[+] Consolidando dataset final de Casas...")
    filas_dataset = []
    for prop in datos_brutos:
        fila = prop.copy()
        fila['unidades_detalladas'] = str(prop.get('unidades_detalladas', []))
        filas_dataset.append(fila)

    df = pd.DataFrame(filas_dataset)
    # Forzar coordenadas al final en el dataset maestro
    if 'coordenadas' in df.columns:
        df = df[[c for c in df.columns if c != 'coordenadas'] + ['coordenadas']]
    
    # --- 2. EXPORTACIÓN A LA NUEVA RUTA ---
    df.to_csv(archivo_final, index=False, encoding='utf-8-sig')
    print(f"\n¡Extracción finalizada exitosamente! Archivo generado: {archivo_final}")
    print(f"Total de casas analizadas: {len(df)}")

if __name__ == "__main__":
    ejecutar_scraper()