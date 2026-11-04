import time
import random
import re
import json
import logging
from playwright.sync_api import sync_playwright

class TikTokScraper:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.posts_capturados = []
        # Set para garantizar que no guardamos el mismo ID de video dos veces
        self.ids_vistos = set()

    def _procesar_lista_videos(self, lista_items: list, origen: str):
        """Procesa una lista de diccionarios JSON extrayendo los metadatos clave."""
        for item in lista_items:
            video_id = item.get("id") or item.get("video", {}).get("id")
            
            if video_id and video_id not in self.ids_vistos:
                self.ids_vistos.add(video_id)
                autor = item.get("author", {})
                nombre_autor = autor.get("uniqueId") or autor.get("nickname", "Desconocido")
                desc = item.get("desc", "")
                stats = item.get("stats", {})
                
                self.posts_capturados.append({
                    "id_video": str(video_id),
                    "autor": nombre_autor,
                    "descripcion": desc.strip(),
                    "reproducciones": int(stats.get("playCount", 0)),
                    "likes": int(stats.get("diggCount", 0)),
                    "compartidos": int(stats.get("shareCount", 0)),
                    "metodo_extraccion": origen
                })

    def interceptar_api_tiktok(self, response):
        """MALLA 1: Captura paquetes JSON de video interceptando la red XHR."""
        try:
            if response.status == 200 and "application/json" in response.headers.get("content-type", ""):
                url = response.url.lower()
                if re.search(r'api/challenge|api/search|api/item|api/post', url):
                    data = response.json()
                    items = data.get("itemList") or data.get("items") or data.get("data", {}).get("items", [])
                    if items:
                        self._procesar_lista_videos(items, "Red (JSON)")
        except Exception:
            pass

    def extraer_estado_interno_html(self, page):
        """MALLA 2: Lee el JSON masivo inyectado directamente en el HTML inicial (SSR)."""
        try:
            html = page.content()
            match = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', html, re.DOTALL)
            
            if match:
                datos_crudos = match.group(1)
                data = json.loads(datos_crudos)
                scope = data.get("__DEFAULT_SCOPE__", {})
                
                # Ubicaciones comunes de los datos iniciales
                challenge_info = scope.get("webapp.challenge-index", {})
                items = challenge_info.get("itemList", [])
                
                if items:
                    self._procesar_lista_videos(items, "Estado HTML")
        except Exception as e:
            logging.debug(f"Fallo al extraer estado HTML interno: {e}")

    def extraer_del_dom_visual(self, page):
        """MALLA 3: Respaldo de Fuerza Bruta. Lee URLs directo de la pantalla."""
        try:
            enlaces = page.locator('a[href*="/video/"]')
            for i in range(enlaces.count()):
                href = enlaces.nth(i).get_attribute("href")
                if href:
                    match = re.search(r'/video/(\d+)', href)
                    if match:
                        video_id = match.group(1)
                        if video_id not in self.ids_vistos:
                            self.ids_vistos.add(video_id)
                            autor_match = re.search(r'@([^/]+)', href)
                            autor = autor_match.group(1) if autor_match else "Desconocido"
                            
                            self.posts_capturados.append({
                                "id_video": video_id,
                                "autor": autor,
                                "descripcion": "Capturado visualmente",
                                "reproducciones": 0,
                                "likes": 0,
                                "compartidos": 0,
                                "metodo_extraccion": "Fuerza Bruta Visual"
                            })
        except Exception:
            pass

    def raspar_hashtag(self, hashtag: str, max_scrolls: int = 5):
        """Orquesta la navegación, el scroll y activa las tres mallas de recolección."""
        url = f"https://www.tiktok.com/tag/{hashtag}"
        print(f"\n[*] Iniciando scraping Híbrido en TikTok para el hashtag: #{hashtag}")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-notifications"
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="es-PE",
                timezone_id="America/Lima"
            )
            
            # Bloqueo de videos para optimizar red, pero permitiendo imágenes
            context.route("**/*.mp4", lambda route: route.abort())

            page = context.new_page()
            page.on("response", self.interceptar_api_tiktok)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                
                print("  [!] Esperando 8 segundos para que resuelvas el CAPTCHA manual si aparece...")
                time.sleep(8)

                self.extraer_estado_interno_html(page)

                for i in range(max_scrolls):
                    print(f"  -> Scroll {i+1}/{max_scrolls} (Capturados: {len(self.posts_capturados)})...")
                    page.evaluate("window.scrollBy(0, window.innerHeight * 0.8);")
                    time.sleep(random.uniform(2.0, 3.0))
                    
                    # Llamada a la malla de seguridad visual
                    self.extraer_del_dom_visual(page)

            except Exception as e:
                print(f"[!] Error durante la navegación en TikTok: {e}")
            finally:
                browser.close()

        print(f"[✓] Extracción finalizada. Se capturaron {len(self.posts_capturados)} registros únicos para #{hashtag}.")
        return self.posts_capturados