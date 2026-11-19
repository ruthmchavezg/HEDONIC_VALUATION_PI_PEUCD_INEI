import argparse
import logging
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

from config.settings import DISTRITOS_LIMA, RAW_DIR
from src.social_scraping.tiktok_parser import TiktokParser
from src.social_scraping.tiktok_storage import obtener_urls_procesadas_tiktok, guardar_lote_tiktok

def configurar_logs():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Se guarda dentro de data/raw/sessions/tiktok_session
SESSION_DIR = RAW_DIR / "sessions" / "tiktok_session"

def interceptar_recursos_pesados(route):
    # Bloqueamos imágenes, videos (media) y fuentes para que cargue a máxima velocidad
    if route.request.resource_type in ["image", "media", "font"]:
        route.abort()
    else:
        route.continue_()

def tiene_sesion_activa(context, page) -> bool:
    """Verifica si existe una sesión válida de TikTok mediante cookies de autenticación."""
    cookies = context.cookies()
    cookies_sesion = {"sessionid", "sessionid_ss", "sid_tt", "uid_tt"}
    tiene_cookie_usuario = any(
        c["name"] in cookies_sesion and "tiktok.com" in c.get("domain", "")
        for c in cookies
    )
    url_actual = page.url.lower()
    en_pantalla_login = "/login" in url_actual
    return tiene_cookie_usuario and not en_pantalla_login

def asegurar_sesion_tiktok(context, page, forzar_login: bool = False):
    """Comprueba si hay sesión activa; si no, abre el login manual y guarda la sesión."""
    logging.info("Verificando sesión activa de TikTok...")
    url_inicial = "https://www.tiktok.com/login" if forzar_login else "https://www.tiktok.com/"
    page.goto(url_inicial, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2500)

    if not forzar_login and tiene_sesion_activa(context, page):
        logging.info("[✓] Sesión activa de TikTok detectada. Continuando con el scraping...")
        return

    if not forzar_login and "/login" not in page.url.lower():
        page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=30000)

    print("\n" + "=" * 60)
    print("  NO SE DETECTÓ UNA SESIÓN ACTIVA DE TIKTOK")
    print("=" * 60)
    print("1. Inicia sesión manualmente en la ventana de Chrome abierta.")
    print("2. Resuelve cualquier CAPTCHA o verificación si aparece.")
    print("3. Cuando veas tu feed principal, vuelve aquí y presiona [ENTER].\n")

    while True:
        input(">>> Presiona [ENTER] cuando hayas iniciado sesión... ")
        page.wait_for_timeout(1500)
        if tiene_sesion_activa(context, page):
            logging.info(f"[✓] Sesión iniciada y guardada en: {SESSION_DIR}")
            break
        print("[!] Aún no se detecta una sesión activa. Verifica el navegador e inténtalo de nuevo.")

def hacer_login_manual():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=['--disable-blink-features=AutomationControlled']
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            asegurar_sesion_tiktok(context, page, forzar_login=True)
        finally:
            try:
                context.close()
            except Exception:
                pass

def ejecutar_scraping():
    scrape_id = f"tiktok_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    parser = TiktokParser()
    urls_ya_procesadas = obtener_urls_procesadas_tiktok()
    datos_brutos_buffer = []
    
    terminos_busqueda = ["casa", "departamento", "habitacion", "cuarto"]
    LOTE_GUARDADO = 25

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    print("\n=======================================================")
    print("  INICIANDO SCRAPING MASIVO EN TIKTOK  ")
    print("=======================================================")
    print("Presiona [Ctrl + C] en cualquier momento para detener y guardar lo avanzado.\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=['--disable-blink-features=AutomationControlled']
        )
        login_page = context.pages[0] if context.pages else context.new_page()

        try:
            # 1. Verificar o solicitar inicio de sesión (con imágenes/CAPTCHAs habilitados)
            asegurar_sesion_tiktok(context, login_page)

            # 2. Abrir pestaña limpia con modo turbo para el scraping y cerrar la del feed
            page = context.new_page()
            page.route("**/*", interceptar_recursos_pesados)
            login_page.close()

            logging.info(f"[*] Iniciando recorrido por {len(DISTRITOS_LIMA)} distritos en TikTok...")

            for distrito in DISTRITOS_LIMA:
                for termino in terminos_busqueda:
                    tipo_inmueble = "habitacion" if termino == "cuarto" else termino
                    query = f"alquiler de {termino} en {distrito} lima"
                    
                    # Explorar el feed de búsqueda de TikTok
                    nuevos_urls = parser.recolectar_enlaces_busqueda(page, query, urls_ya_procesadas)
                    
                    # Entrar a extraer video por video
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
                            
                            if len(datos_brutos_buffer) >= LOTE_GUARDADO:
                                guardar_lote_tiktok(datos_brutos_buffer)
                                logging.info(f"[*] Lote de {len(datos_brutos_buffer)} videos guardado en disco de forma segura.")
                                datos_brutos_buffer.clear()
                            
                        except Exception as e:
                            logging.error(f"Error procesando {url}: {e}")
                            
        except KeyboardInterrupt:
            print("\n[!!!] INTERRUPCIÓN MANUAL DETECTADA (Ctrl+C). Deteniendo scraper de forma segura...")
        finally:
            if datos_brutos_buffer:
                print(f"\n[*] Guardando los últimos {len(datos_brutos_buffer)} videos en la Capa Bronce (data/raw/social)...")
                guardar_lote_tiktok(datos_brutos_buffer)
            else:
                print("\n[-] Proceso finalizado. Todo está guardado.")
                
            try:
                context.close()
            except Exception:
                pass

if __name__ == "__main__":
    configurar_logs()
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--login", action="store_true", help="Fuerza la apertura del navegador para iniciar sesión manualmente.")
    args = arg_parser.parse_args()
    
    if args.login:
        hacer_login_manual()
    else:
        ejecutar_scraping()