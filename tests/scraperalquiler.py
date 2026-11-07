from playwright.sync_api import sync_playwright
import pandas as pd
import time
import os
import re
import random

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
def recolectar_enlaces(page, url_base, pagina_inicio=1, paginas_a_recorrer=13):
    enlaces_totales = set()
    
    for i in range(pagina_inicio, pagina_inicio + paginas_a_recorrer):
        print(f"\n[+] Verificando enlaces de la página {i}...")
        
        url_actual = url_base if i == 1 else f"{url_base}?page={i}"
            
        if i > 1:
            tiempo_lectura = random.randint(4500, 7500)
            print(f"  [zZz] Simulando navegación... esperando {round(tiempo_lectura/1000, 1)}s")
            page.wait_for_timeout(tiempo_lectura)
            
        page.goto(url_actual, wait_until="domcontentloaded")
        
        try:
            page.wait_for_selector('[data-to-posting]', timeout=60000)
        except Exception:
            print("  [!] Verificación Cloudflare requerida en Edge. Esperando 20s...")
            page.wait_for_timeout(20000)
        
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3);")
        page.wait_for_timeout(1000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        page.wait_for_timeout(1500)
        
        tarjetas = page.locator('[data-to-posting]')
        if tarjetas.count() == 0:
            print("[-] No se detectaron más anuncios en esta página. Finalizando recolección.")
            break
            
        for j in range(tarjetas.count()):
            ruta = tarjetas.nth(j).get_attribute('data-to-posting')
            if ruta:
                ruta_limpia = ruta.split('?')[0]
                enlaces_totales.add(f"https://urbania.pe{ruta_limpia}")
                
    return list(enlaces_totales)

# ==========================================
# 4. RECUPERACIÓN Y PROCESAMIENTO PENDIENTE
# ==========================================
def ejecutar_scraper():
    URL_BASE = "https://urbania.pe/buscar/alquiler-de-casas-en-lima"
    PAGINA_INICIO = 1 
    CANTIDAD_PAGINAS = 13
    archivo_backup = "backup_casas_urbania.csv"
    
    datos_brutos = []
    urls_ya_procesadas = set()
    
    # Lectura del respaldo para no repetir URLs
    if os.path.exists(archivo_backup):
        print(f"\n[+] Cargando respaldo previo desde: {archivo_backup}")
        try:
            df_previo = pd.read_csv(archivo_backup)
            datos_brutos = df_previo.to_dict('records')
            urls_ya_procesadas = set(df_previo['url'].dropna().tolist())
            print(f"[*] Registros recuperados en memoria: {len(datos_brutos)}")
        except Exception as e:
            print(f"[-] Advertencia al leer backup: {e}. Iniciando con lista vacía.")
    
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
        
        enlaces_totales = recolectar_enlaces(page, URL_BASE, pagina_inicio=PAGINA_INICIO, paginas_a_recorrer=CANTIDAD_PAGINAS)
        
        # Filtro de exclusión
        enlaces_pendientes = [url for url in enlaces_totales if url not in urls_ya_procesadas]
        print(f"\n==========================================")
        print(f"Total en listado web: {len(enlaces_totales)}")
        print(f"Ya procesadas (en backup): {len(urls_ya_procesadas)}")
        print(f"Propiedades restantes por scrapear: {len(enlaces_pendientes)}")
        print(f"==========================================\n")
        
        for index, enlace in enumerate(enlaces_pendientes, 1):
            print(f"[{index}/{len(enlaces_pendientes)}] Procesando casa: {enlace}")
            try:
                page.wait_for_timeout(random.randint(1500, 3000))
                page.goto(enlace, wait_until="domcontentloaded")
                page.wait_for_timeout(random.randint(1800, 2600)) 
                
                # Clics e iteración en pestañas
                pestanas_dinamicas = extraer_caracteristicas_dinamicas(page)
                expandir_textos_ocultos(page)
                
                inmueble = {'url': enlace}
                
                # Imagen principal
                try:
                    img_url = page.locator('meta[property="og:image"]').get_attribute('content', timeout=2000)
                    inmueble['imagen_principal'] = img_url if img_url else "No disponible"
                except Exception:
                    inmueble['imagen_principal'] = "No disponible"
                
                # Reglas fijas
                for campo, selectores in REGLAS_EXTRACCION.items():
                    inmueble[campo] = extraer_texto_robusto_pw(page, selectores)
                
                # Columnas independientes por categoría
                for columna, valor in pestanas_dinamicas.items():
                    inmueble[columna] = valor
                
                datos_brutos.append(inmueble)
                
                # Guardado de emergencia incremental
                if len(datos_brutos) % 25 == 0:
                    pd.DataFrame(datos_brutos).to_csv(archivo_backup, index=False, encoding='utf-8-sig')
                    print(f"  [!] Respaldo actualizado. Total acumulado: {len(datos_brutos)}")
                
            except Exception as e:
                print(f"  -> Error omitiendo propiedad: {e}")
                continue
                
        browser.close()

    print("\n[+] Consolidando dataset final unificado...")
    df = pd.DataFrame(datos_brutos)
    
    nombre_archivo = "dataset_hedonico_urbania_casas.csv"
    df.to_csv(nombre_archivo, index=False, encoding='utf-8-sig')
    print(f"\n¡Proceso finalizado! Archivo completo guardado en: {nombre_archivo}")
    print(f"Total registros finales: {len(df)}")

if __name__ == "__main__":
    ejecutar_scraper()