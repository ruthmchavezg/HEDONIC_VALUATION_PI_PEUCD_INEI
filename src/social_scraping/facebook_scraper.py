import os
import json
import time
from playwright.sync_api import sync_playwright

COOKIE_PATH = "data/raw/sessions/session_cookies_fb.json"

class FacebookScraper:
    def __init__(self):
        # Asegurarse de que la ruta donde se guardan las cookies exista
        os.makedirs(os.path.dirname(COOKIE_PATH), exist_ok=True)

    def iniciar_sesion_manual(self):
        """Abre el navegador visible para iniciar sesión en Facebook una sola vez y guardar las cookies."""
        print("[*] Abriendo navegador para inicio de sesión manual en Facebook...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.facebook.com/")
            
            print("\n[ATENCIÓN] Inicia sesión en la ventana del navegador.")
            print("Una vez que estés en tu feed principal, presiona ENTER aquí en la terminal...\n")
            input()

            cookies = context.cookies()
            with open(COOKIE_PATH, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            print(f"[✓] Cookies de sesión guardadas en {COOKIE_PATH}")
            browser.close()

    def raspar_pagina_publica(self, url_pagina: str):
        """Raspa una página pública utilizando las cookies de sesión guardadas."""
        if not os.path.exists(COOKIE_PATH):
            print("[!] No se encontraron cookies de sesión. Ejecuta primero la autenticación manual.")
            return []

        print(f"[*] Accediendo a la página de Facebook: {url_pagina}")
        posts = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            with open(COOKIE_PATH, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            context.add_cookies(cookies)

            page = context.new_page()
            try:
                # Usar la versión móvil (m.facebook.com) por tener una estructura HTML más limpia
                url_movil = url_pagina.replace("www.facebook.com", "m.facebook.com")
                page.goto(url_movil, wait_until="domcontentloaded", timeout=40000)
                time.sleep(3)

                articulos = page.locator('article')
                for i in range(min(articulos.count(), 10)):
                    art = articulos.nth(i)
                    texto = art.inner_text() if art.count() > 0 else ""
                    if texto.strip():
                        posts.append({"contenido": texto.strip()})
                
            except Exception as e:
                print(f"[!] Error al raspar Facebook: {e}")
            finally:
                browser.close()

        print(f"[✓] Se extrajeron {len(posts)} publicaciones de Facebook.")
        return posts