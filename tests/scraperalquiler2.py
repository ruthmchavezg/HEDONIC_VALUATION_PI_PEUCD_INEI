from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import pandas as pd
import time
import re
import random

# ==========================================
# 1. REGLAS DE EXTRACCIÓN (ESTRUCTURA PURA)
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
# 2. FUNCIONES AUXILIARES DE EXTRACCIÓN Y CLICS
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
                    textos_filtrados = [t for t in textos_limpios if t not in ['Leer descripción completa -', 'Leer descripción completa', 'Ver más', 'Ver menos']]
                    if textos_filtrados:
                        return " | ".join(textos_filtrados)
        except Exception:
            continue
    return "No especificado"

def extraer_unidades_detalladas_pw(page):
    unidades_extraidas = []
    pestanas = page.locator('button[class*="unit-selection-module__rooms-button"]')
    
    if pestanas.count() == 0:
        return []

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
                    
                    unidades_extraidas.append({
                        "dormitorios": nombre_pestana,
                        "tipo_unidad": tipo,
                        "precio_unidad": precio,
                        "detalles_unidad": features_limpio
                    })
        except Exception:
            continue
            
    return unidades_extraidas

def expandir_textos_ocultos(page):
    selectores_botones = [
        'button[class*="viewmoreButton"]',          
        'button[class*="view-more-dev-feature"]',   
        'text="Leer descripción completa"',
        'text="Leer descripción completa -"', 
        'text="Ver más"'
    ]
    
    for selector in selectores_botones:
        try:
            botones = page.locator(selector)
            for i in range(botones.count()):
                boton = botones.nth(i)
                if boton.is_visible():
                    boton.scroll_into_view_if_needed()
                    boton.click(timeout=1500)
                    page.wait_for_timeout(600)
        except Exception:
            continue

def extraer_caracteristicas_dinamicas(page):
    datos_extraidos = {}
    try:
        botones = page.locator('button[class*="generalFeaturesProperty-module__button-general-features"]')
        total_botones = botones.count()
        if total_botones == 0:
            return datos_extraidos
        
        for i in range(total_botones):
            boton = botones.nth(i)
            span_titulo = boton.locator('span[class*="text-title"]')
            nombre_crudo = span_titulo.inner_text().strip() if span_titulo.count() > 0 else boton.inner_text().strip()
            
            nombre_columna = nombre_crudo.lower().replace(" ", "_")
            nombre_columna = (nombre_columna.replace("á", "a")
                                           .replace("é", "e")
                                           .replace("í", "i")
                                           .replace("ó", "o")
                                           .replace("ú", "u"))
            
            boton.scroll_into_view_if_needed()
            boton.click(timeout=2000)
            page.wait_for_timeout(800) 
            
            items = page.locator('span[class*="generalFeaturesProperty-module__description-text"]')
            textos_pestana = []
            for j in range(items.count()):
                item = items.nth(j)
                if item.is_visible():
                    val = item.inner_text().strip()
                    if val and val not in textos_pestana:
                        textos_pestana.append(val)
            
            if textos_pestana:
                datos_extraidos[nombre_columna] = " | ".join(textos_pestana)
                
        return datos_extraidos
    except Exception:
        return datos_extraidos

# ==========================================
# 3. NAVEGACIÓN Y PAGINACIÓN
# ==========================================
def recolectar_enlaces(page, url_base, pagina_inicio=1, paginas_a_recorrer=127):
    enlaces_totales = set()
    
    for i in range(pagina_inicio, pagina_inicio + paginas_a_recorrer):
        print(f"\n[+] Recolectando enlaces de la página {i}...")
        
        url_actual = url_base if i == 1 else f"{url_base}?page={i}"
            
        if i > 1:
            tiempo_lectura = random.randint(5000, 8000)
            print(f"  [zZz] Simulando navegación... esperando {round(tiempo_lectura/1000, 1)}s")
            page.wait_for_timeout(tiempo_lectura)
            
        page.goto(url_actual, wait_until="domcontentloaded")
        
        try:
            page.wait_for_selector('[data-to-posting]', timeout=60000)
        except Exception:
            print("  [!] Verificación Cloudflare requerida en Edge. Esperando 20s...")
            page.wait_for_timeout(20000)
        
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3);")
        page.wait_for_timeout(1200)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        page.wait_for_timeout(2000)
        
        tarjetas = page.locator('[data-to-posting]')
        if tarjetas.count() == 0:
            print("[-] No se detectaron más anuncios en esta página. Finalizando recolección de enlaces.")
            break
            
        for j in range(tarjetas.count()):
            ruta = tarjetas.nth(j).get_attribute('data-to-posting')
            if ruta:
                ruta_limpia = ruta.split('?')[0]
                enlaces_totales.add(f"https://urbania.pe{ruta_limpia}")
                
    return list(enlaces_totales)

# ==========================================
# 4. PROCESAMIENTO PRINCIPAL DESDE CERO
# ==========================================
def ejecutar_scraper():
    URL_BASE = "https://urbania.pe/buscar/alquiler-de-departamentos-en-lima"
    PAGINA_INICIO = 1 
    CANTIDAD_PAGINAS = 127
    
    datos_brutos = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="msedge", 
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        lista_urls = recolectar_enlaces(page, URL_BASE, pagina_inicio=PAGINA_INICIO, paginas_a_recorrer=CANTIDAD_PAGINAS)
        print(f"\n¡Total de propiedades únicas encontradas: {len(lista_urls)}!")
        
        for index, enlace in enumerate(lista_urls, 1):
            print(f"[{index}/{len(lista_urls)}] Procesando: {enlace}")
            try:
                page.wait_for_timeout(random.randint(1500, 3000))
                page.goto(enlace, wait_until="domcontentloaded")
                page.wait_for_timeout(random.randint(1800, 2600)) 
                
                # 1. Clics en pestañas dinámicas (Generales, Servicios, Ambientes, Exteriores)
                pestanas_dinamicas = extraer_caracteristicas_dinamicas(page)
                
                # 2. Clics en botones de expansión ("Leer descripción", "Ver más")
                expandir_textos_ocultos(page)
                
                # 3. Clics en dormitorios de Proyectos ("1 dorm", "2 dorms", etc.)
                unidades = extraer_unidades_detalladas_pw(page)
                
                inmueble = {'url': enlace}
                
                # 4. Captura de imagen principal
                try:
                    img_url = page.locator('meta[property="og:image"]').get_attribute('content', timeout=2000)
                    inmueble['imagen_principal'] = img_url if img_url else "No disponible"
                except Exception:
                    inmueble['imagen_principal'] = "No disponible"
                
                # 5. Extracción de textos estándar
                for campo, selectores in REGLAS_EXTRACCION.items():
                    inmueble[campo] = extraer_texto_robusto_pw(page, selectores)
                
                inmueble['unidades_detalladas'] = unidades
                
                # 6. Desempaquetado de columnas limpias independientes
                for columna, valor in pestanas_dinamicas.items():
                    inmueble[columna] = valor
                
                datos_brutos.append(inmueble)
                
                if index % 50 == 0:
                    pd.DataFrame(datos_brutos).to_csv("backup_emergencia_urbania.csv", index=False, encoding='utf-8-sig')
                    print(f"  [!] Respaldo actualizado: {index} propiedades a salvo.")

                if index % 400 == 0:
                    tiempo_descanso = random.randint(120000, 180000)
                    minutos_reales = round(tiempo_descanso / 60000, 1)
                    print(f"\n[zzz] Enfriando conexión. Esperando {minutos_reales} minutos...")
                    page.wait_for_timeout(tiempo_descanso)
                    print("[+] Reanudando proceso...\n")
                
            except Exception as e:
                print(f"  -> Error saltando propiedad: {e}")
                continue
                
        browser.close()

    print("\n[+] Consolidando dataset final...")
    filas_dataset = []
    for prop in datos_brutos:
        fila = prop.copy()
        fila['unidades_detalladas'] = str(prop.get('unidades_detalladas', []))
        filas_dataset.append(fila)

    df = pd.DataFrame(filas_dataset)
    
    nombre_archivo = "dataset_hedonico_urbania_departamentos.csv"
    df.to_csv(nombre_archivo, index=False, encoding='utf-8-sig')
    print(f"\n¡Extracción finalizada exitosamente! Archivo generado: {nombre_archivo}")
    print(f"Total de registros consolidados: {len(df)}")

if __name__ == "__main__":
    ejecutar_scraper()