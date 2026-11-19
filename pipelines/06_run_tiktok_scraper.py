import argparse
import logging
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

from config.settings import DISTRITOS_LIMA
from src.social_scraping.tiktok_parser import TiktokParser
from src.social_scraping.tiktok_storage import obtener_urls_procesadas_tiktok, guardar_lote_tiktok

def configurar_logs():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SESSION_DIR = Path(__file__).parent.parent / "data" / "tiktok_session"

def interceptar_recursos_pesados(route):
    # Bloqueamos imágenes, videos (media) y fuentes para que cargue a la velocidad de la luz
    if route.request.resource_type in ["image", "media", "font"]:
        route.abort()
    else:
        route.continue_()

def hacer_login_manual():
    print("\n=======================================================")
    print("  MODO LOGIN MANUAL DE TIKTOK INICIADO  ")
    print("=======================================================")
    print("1. Se abrirá una ventana de Chrome.")
    print("2. Inicia sesión en tu cuenta de TikTok y resuelve cualquier CAPTCHA.")
    print("3. Cuando veas el feed principal, vuelve aquí y presiona ENTER.")
    
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            channel="chrome", 
            headless=False, 
            viewport={"width": 1280, "height": 800},
            args=['--disable-blink-features=AutomationControlled']
        )
        page = browser.new_page()
        page.goto("https://www.tiktok.com/login")
        
        input("\n[Pausa] PRESIONA ENTER AQUÍ CUANDO HAYAS TERMINADO DE LOGUEARTE EN EL NAVEGADOR...")
        
        # Blindaje contra cierre manual de la ventana
        try:
            browser.close()
        except Exception:
            pass
            
        print("[✓] Sesión guardada con éxito en la carpeta data/tiktok_session/")


def ejecutar_scraping():
    scrape_id = f"tiktok_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    parser = TiktokParser()
    urls_ya_procesadas = obtener_urls_procesadas_tiktok()
    datos_brutos_buffer = []
    
    terminos_busqueda = ["casa", "departamento", "habitacion", "cuarto"]
    # TAMAÑO DEL BLOQUE DE GUARDADO
    LOTE_GUARDADO = 25 

    print("\n=======================================================")
    print("  INICIANDO SCRAPING MASIVO EN TIKTOK  ")
    print("=======================================================")
    print("Presiona [Ctrl + C] en cualquier momento para detener y guardar lo avanzado.\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            channel="chrome",
            headless=False, 
            viewport={"width": 1280, "height": 800},
            args=['--disable-blink-features=AutomationControlled'] 
        )
        
        page = context.new_page()
        # --- MODO TURBO ACTIVADO (Bloquea videos pesados para scroll rápido) ---
        page.route("**/*", interceptar_recursos_pesados)

        try:
            for distrito in DISTRITOS_LIMA:
                for termino in terminos_busqueda:
                    tipo_inmueble = "habitacion" if termino == "cuarto" else termino
                    query = f"alquiler de {termino} en {distrito} lima"
                    
                    # 1. Explorar el feed de búsqueda de TikTok
                    nuevos_urls = parser.recolectar_enlaces_busqueda(page, query, urls_ya_procesadas)
                    
                    # 2. Entrar a extraer video por video
                    for idx, url in enumerate(nuevos_urls, 1):
                        try:
                            datos = parser.extraer_video(page, url)
                            datos["url"] = url
                            datos["tipo_inmueble"] = tipo_inmueble
                            datos["distrito"] = distrito
                            datos["portal"] = "tiktok"
                            datos["scrape_id"] = scrape_id
                            datos["timestamp"] = datetime.now().isoformat(timespec="seconds")
                            
                            datos_brutos_buffer.append(datos)
                            urls_ya_procesadas.add(url)
                            logging.info(f"  [{idx}/{len(nuevos_urls)}] {distrito} - {tipo_inmueble} extraído.")
                            
                            # --- NUEVA LÓGICA DE GUARDADO EN BLOQUE ---
                            if len(datos_brutos_buffer) >= LOTE_GUARDADO:
                                guardar_lote_tiktok(datos_brutos_buffer)
                                logging.info(f"[*] Lote de {len(datos_brutos_buffer)} videos guardado en disco de forma segura.")
                                datos_brutos_buffer.clear() # Vaciamos memoria
                            
                        except Exception as e:
                            logging.error(f"Error procesando {url}: {e}")
                            
        # === ESCUDO PROTECTOR (GRACEFUL EXIT) ===
        except KeyboardInterrupt:
            print("\n[!!!] INTERRUPCIÓN MANUAL DETECTADA (Ctrl+C). Deteniendo scraper de forma segura...")
        finally:
            if datos_brutos_buffer:
                print(f"\n[*] Guardando los últimos {len(datos_brutos_buffer)} videos en la Capa Bronce (data/raw/social)...")
                guardar_lote_tiktok(datos_brutos_buffer)
            else:
                print(f"\n[-] Proceso finalizado. Todo está guardado.")
                
            try:
                context.close()
            except:
                pass

if __name__ == "__main__":
    configurar_logs()
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", action="store_true", help="Abre el navegador para loguearte manualmente 1 sola vez.")
    args = parser.parse_args()
    
    if args.login:
        hacer_login_manual()
    else:
        ejecutar_scraping()