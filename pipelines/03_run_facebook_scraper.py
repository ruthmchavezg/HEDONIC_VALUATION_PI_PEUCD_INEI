import argparse
import logging
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

from config.settings import DISTRITOS_LIMA
from src.social_scraping.facebook_parser import FacebookParser
from src.social_scraping.facebook_storage import obtener_urls_procesadas_facebook, guardar_lote_facebook

def configurar_logs():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SESSION_DIR = Path(__file__).parent.parent / "data" / "facebook_session"

def interceptar_recursos_pesados(route):
    if route.request.resource_type in ["image", "media", "font"]:
        route.abort()
    else:
        route.continue_()

def ejecutar_scraping():
    scrape_id = f"fb_marketplace_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    parser = FacebookParser()
    urls_ya_procesadas = obtener_urls_procesadas_facebook()
    datos_brutos_buffer = []
    
    terminos_busqueda = ["casa", "departamento", "habitacion", "cuarto"]
    # TAMAÑO DEL BLOQUE DE GUARDADO
    LOTE_GUARDADO = 25 

    print("\n=======================================================")
    print("  INICIANDO SCRAPING MASIVO EN FACEBOOK MARKETPLACE  ")
    print("=======================================================")
    print("Presiona [Ctrl + C] en cualquier momento para detener y guardar lo avanzado.\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            channel="chrome",
            headless=False, 
            viewport={"width": 1280, "height": 800},
            args=['--disable-notifications', '--disable-blink-features=AutomationControlled'] 
        )
        page = context.new_page()
        page.route("**/*", interceptar_recursos_pesados)

        try:
            for distrito in DISTRITOS_LIMA:
                for termino in terminos_busqueda:
                    tipo_inmueble = "habitacion" if termino == "cuarto" else termino
                    
                    query = f"alquiler {termino} {distrito}"
                    nuevos_urls = parser.recolectar_enlaces_busqueda(page, query, urls_ya_procesadas)
                    
                    for idx, url in enumerate(nuevos_urls, 1):
                        try:
                            datos = parser.extraer_publicacion(page, url)
                            
                            datos["url"] = url
                            datos["tipo_inmueble"] = tipo_inmueble
                            datos["distrito"] = distrito
                            datos["portal"] = "facebook_marketplace"
                            datos["scrape_id"] = scrape_id
                            datos["timestamp"] = datetime.now().isoformat(timespec="seconds")
                            
                            datos_brutos_buffer.append(datos)
                            urls_ya_procesadas.add(url)
                            logging.info(f"  [{idx}/{len(nuevos_urls)}] {distrito} - {tipo_inmueble} extraído.")
                            
                            # --- NUEVA LÓGICA DE GUARDADO EN BLOQUE ---
                            if len(datos_brutos_buffer) >= LOTE_GUARDADO:
                                guardar_lote_facebook(datos_brutos_buffer)
                                logging.info(f"[*] Lote de {len(datos_brutos_buffer)} anuncios guardado en disco de forma segura.")
                                datos_brutos_buffer.clear() # Vaciamos el buffer para no duplicar datos ni llenar RAM
                                
                        except Exception as e:
                            logging.error(f"Error procesando {url}: {e}")
                            
        except KeyboardInterrupt:
            print("\n[!!!] INTERRUPCIÓN MANUAL DETECTADA (Ctrl+C). Deteniendo scraper de forma segura...")
        finally:
            # --- GUARDADO DEL REMANENTE FINAL ---
            if datos_brutos_buffer:
                print(f"\n[*] Guardando los últimos {len(datos_brutos_buffer)} anuncios en la Capa Bronce...")
                guardar_lote_facebook(datos_brutos_buffer)
            else:
                print(f"\n[-] Proceso finalizado. Todo está guardado.")
                
            try:
                context.close()
            except:
                pass

if __name__ == "__main__":
    configurar_logs()
    ejecutar_scraping()