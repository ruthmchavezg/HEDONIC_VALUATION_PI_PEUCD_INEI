import argparse
import logging
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

from config.settings import DISTRITOS_LIMA, RAW_DIR
from src.social_scraping.facebook_parser import FacebookParser
from src.social_scraping.facebook_storage import obtener_urls_procesadas_facebook, guardar_lote_facebook

def configurar_logs():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SESSION_DIR = RAW_DIR / "sessions" / "facebook_session"

def interceptar_recursos_pesados(route):
    if route.request.resource_type in ["image", "media", "font"]:
        route.abort()
    else:
        route.continue_()

def tiene_sesion_activa(context, page) -> bool:
    """Verifica cookies en cualquier subdominio de facebook.com (www o web)."""
    cookies = context.cookies()
    tiene_cookie_usuario = any(
        c["name"] == "c_user" and "facebook.com" in c.get("domain", "")
        for c in cookies
    )
    url_actual = page.url.lower()
    en_pantalla_login = (
        "login" in url_actual
        or "checkpoint" in url_actual
        or page.locator('input[name="email"]').count() > 0
    )
    return tiene_cookie_usuario and not en_pantalla_login

def asegurar_sesion_facebook(context, page):
    """Comprueba si hay sesión activa; si no, pide iniciar sesión manualmente."""
    logging.info("Verificando sesión activa de Facebook...")
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    if tiene_sesion_activa(context, page):
        logging.info("[✓] Sesión activa detectada. Continuando con el scraping...")
        return

    print("\n" + "=" * 60)
    print("  NO SE DETECTÓ UNA SESIÓN ACTIVA DE FACEBOOK")
    print("=" * 60)
    print("1. Inicia sesión manualmente en la ventana de Chrome abierta.")
    print("2. Completa cualquier verificación (2FA o captcha) si aparece.")
    print("3. Cuando cargue tu inicio de Facebook, vuelve aquí y presiona [ENTER].\n")

    while True:
        input(">>> Presiona [ENTER] cuando hayas iniciado sesión... ")
        page.wait_for_timeout(1500)
        if tiene_sesion_activa(context, page):
            logging.info(f"[✓] Sesión iniciada y guardada en: {SESSION_DIR}")
            break
        print("[!] Aún no se detecta una sesión activa. Verifica el navegador e inténtalo de nuevo.")

def ejecutar_scraping():
    scrape_id = f"fb_marketplace_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    parser = FacebookParser()
    urls_ya_procesadas = obtener_urls_procesadas_facebook()
    datos_brutos_buffer = []
    
    terminos_busqueda = ["casa", "departamento", "habitacion", "cuarto"]
    LOTE_GUARDADO = 25

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    print("\n=======================================================")
    print("  INICIANDO SCRAPING MASIVO EN FACEBOOK MARKETPLACE  ")
    print("=======================================================")
    print("Presiona [Ctrl + C] en cualquier momento para detener y guardar lo avanzado.\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=['--disable-notifications', '--disable-blink-features=AutomationControlled']
        )
        login_page = context.pages[0] if context.pages else context.new_page()

        try:
            # 1. Verificar o solicitar inicio de sesión
            asegurar_sesion_facebook(context, login_page)

            # 2. Abrir pestaña limpia para Marketplace y cerrar la del muro
            page = context.new_page()
            page.route("**/*", interceptar_recursos_pesados)
            login_page.close()

            logging.info(f"[*] Iniciando recorrido por {len(DISTRITOS_LIMA)} distritos en Marketplace...")

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
                            
                            if len(datos_brutos_buffer) >= LOTE_GUARDADO:
                                guardar_lote_facebook(datos_brutos_buffer)
                                logging.info(f"[*] Lote de {len(datos_brutos_buffer)} anuncios guardado en disco de forma segura.")
                                datos_brutos_buffer.clear()
                                
                        except Exception as e:
                            logging.error(f"Error procesando {url}: {e}")
                            
        except KeyboardInterrupt:
            print("\n[!!!] INTERRUPCIÓN MANUAL DETECTADA (Ctrl+C). Deteniendo scraper de forma segura...")
        finally:
            if datos_brutos_buffer:
                print(f"\n[*] Guardando los últimos {len(datos_brutos_buffer)} anuncios en la Capa Bronce...")
                guardar_lote_facebook(datos_brutos_buffer)
            else:
                print("\n[-] Proceso finalizado. Todo está guardado.")
                
            try:
                context.close()
            except Exception:
                pass

if __name__ == "__main__":
    configurar_logs()
    ejecutar_scraping()