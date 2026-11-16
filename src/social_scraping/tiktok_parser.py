import re
from urllib.parse import quote
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

class TiktokParser:
    def recolectar_enlaces_busqueda(self, page, query: str, urls_procesadas: set) -> list:
        enlaces_totales = set()
        url_busqueda = f"https://www.tiktok.com/search/video?q={quote(query)}"
        
        print(f"  -> Buscando en TikTok: '{query}'")
        page.goto(url_busqueda)
        
        try:
            page.wait_for_selector('div[data-e2e="search_video-item"]', timeout=8000)
            print("  -> Explorando (Se abortará automáticamente si no hay videos nuevos)...")
            
            altura_anterior = 0
            intentos_sin_crecer = 0
            intentos_sin_nuevos = 0 # 🚀 Nuevo contador para la Parada Inteligente
            
            for i in range(1, 41):
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                items = soup.find_all('div', attrs={"data-e2e": "search_video-item"})
                
                nuevos_en_pantalla = 0
                for item in items:
                    a_tag = item.find("a", href=True)
                    if a_tag and "/video/" in a_tag["href"]:
                        href = a_tag["href"]
                        if href.startswith("/"):
                            href = f"https://www.tiktok.com{href}"
                            
                        if href not in enlaces_totales and href not in urls_procesadas:
                            enlaces_totales.add(href)
                            nuevos_en_pantalla += 1
                
                # 🚀 LÓGICA DE PARADA INTELIGENTE
                if nuevos_en_pantalla == 0 and len(urls_procesadas) > 0:
                    intentos_sin_nuevos += 1
                    if intentos_sin_nuevos >= 3:
                        print("    [!] 3 scrolls seguidos con puros videos ya conocidos. Abortando búsqueda.")
                        break
                else:
                    intentos_sin_nuevos = 0 # Reiniciamos si encuentra al menos 1 video fresco
                
                # Clic en Cargar Más (si existe)
                try:
                    btn_cargar = page.locator('button:has-text("Cargar más"), button:has-text("Load more")').first
                    if btn_cargar.count() > 0 and btn_cargar.is_visible():
                        btn_cargar.click(timeout=1000)
                except:
                    pass
                
                # Scroll más rápido
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                page.wait_for_timeout(1800) # Tiempo reducido de 3000 a 1800ms
                
                # DETECTOR DE FONDO
                altura_actual = page.evaluate("document.body.scrollHeight")
                if altura_actual == altura_anterior:
                    intentos_sin_crecer += 1
                    if intentos_sin_crecer >= 2:
                        print("    [-] Fin de los resultados de TikTok alcanzado.")
                        break
                else:
                    intentos_sin_crecer = 0
                    altura_anterior = altura_actual
                
        except Exception as e:
            print(f"  [!] La grilla tardó en cargar o no hay resultados para este distrito.")

        print(f"    [+] {len(enlaces_totales)} videos NUEVOS listos para extraer.")
        return list(enlaces_totales)

    def extraer_video(self, page, url: str) -> dict:
        page.goto(url)
        
        try:
            # Reducimos un poco el tiempo de espera visual
            page.wait_for_selector('[data-e2e="browse-video-desc"]', timeout=4000)
        except:
            pass
            
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        # 1. AUTOR (Extraído directamente de la URL)
        match_autor = re.search(r'tiktok\.com/@([^/]+)/video', url)
        autor = match_autor.group(1) if match_autor else ""
            
        # 2. DESCRIPCIÓN
        desc_tag = soup.find(attrs={"data-e2e": "browse-video-desc"})
        descripcion = desc_tag.get_text(separator=" ", strip=True) if desc_tag else ""
        if not descripcion:
            match = re.search(r'"desc":"([^"]+)"', html)
            if match:
                try:
                    descripcion = match.group(1).encode().decode('unicode_escape')
                except:
                    descripcion = match.group(1)

        # 2. DESCRIPCIÓN
        desc_tag = soup.find(attrs={"data-e2e": "browse-video-desc"})
        descripcion = desc_tag.get_text(separator=" ", strip=True) if desc_tag else ""
        if not descripcion:
            match = re.search(r'"desc":"([^"]+)"', html)
            if match:
                try:
                    descripcion = match.group(1).encode().decode('unicode_escape')
                except:
                    descripcion = match.group(1)

                    

        # 3. EXTRAER TEXTO REAL DEL VIDEO (Stickers, auto-captions y palabras clave)
        subtitulos_texto = ""
        textos_ocultos = re.findall(r'"text":"([^"]+)"', html)
        
        # Filtramos palabras clave del rubro inmobiliario
        palabras_clave = [t for t in textos_ocultos if any(k in t.lower() for k in ['s/', 'dolares', 'soles', 'm2', 'piso', 'cuarto', 'baño', 'mensual', 'alquiler', 'precio'])]
        
        if palabras_clave:
            # Unimos las palabras clave encontradas sin duplicados
            subtitulos_texto = " [TEXTO EN VIDEO]: " + " | ".join(sorted(set(palabras_clave)))
        
        # Unimos la descripción original con el texto rescatado del video
        descripcion_final = descripcion + subtitulos_texto


                
        # Alternativa más rápida con Regex directo sobre el HTML crudo
        # Busca cualquier texto que TikTok haya etiquetado como "palabra sugerida" o "texto de voz"
        if not subtitulos_texto:
            textos_ocultos = re.findall(r'"text":"([^"]+)"', html)
            # Filtramos palabras clave del rubro inmobiliario que puedan estar en stickers del video
            palabras_clave = [t for t in textos_ocultos if any(k in t.lower() for k in ['s/', 'dolares', 'soles', 'm2', 'piso', 'cuarto', 'baño', 'mensual', 'alquiler'])]
            if palabras_clave:
                subtitulos_texto = " [TEXTO EN VIDEO]: " + " | ".join(set(palabras_clave))
        
        # Unimos la descripción original con lo que hayamos rescatado del video
        descripcion_final = descripcion + subtitulos_texto
                    
        # 3. MÉTRICAS
        def obtener_metrica(patron):
            m = re.search(patron, html)
            return m.group(1) if m else "0"

        reproducciones = obtener_metrica(r'"playCount":(\d+)')
        likes = obtener_metrica(r'"diggCount":(\d+)')
        compartidos = obtener_metrica(r'"shareCount":(\d+)')

        # 4. FECHA DE PUBLICACIÓN
        fecha_pub = ""
        m_time = re.search(r'"createTime":"?(\d{10})"?', html)
        if m_time:
            timestamp = int(m_time.group(1))
            fecha_pub = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
        else:
            info_div = soup.find('div', class_=re.compile(r'DivInfoContainer|browser-nickname'))
            if info_div:
                for span in info_div.find_all('span'):
                    txt = span.get_text(strip=True)
                    if "-" in txt or "hace" in txt.lower() or "días" in txt.lower():
                        fecha_pub = self._normalizar_fecha(txt)
                        break

        # 5. ID DEL CONTENIDO
        match_id = re.search(r'/video/(\d+)', url)
        id_contenido = match_id.group(1) if match_id else ""

        # Retornamos el diccionario conservando el nombre original de la columna "descripcion"
        return {
            "id_contenido": id_contenido,
            "autor": autor,
            "fecha_publicacion": fecha_pub,
            "descripcion": descripcion_final,
            "reproducciones": reproducciones,
            "likes": likes,
            "compartidos": compartidos
        }

    def _normalizar_fecha(self, texto: str) -> str:
        if not texto: return ""
        texto = texto.lower().strip()
        now = datetime.now()
        try:
            if "hace" in texto and any(x in texto for x in ["h", "m", "hora", "minuto"]):
                return now.strftime("%Y-%m-%d")
            elif "hace" in texto and any(x in texto for x in ["día", "dias", "dia"]):
                dias = int(re.search(r'\d+', texto).group())
                return (now - timedelta(days=dias)).strftime("%Y-%m-%d")
            elif "hace" in texto and "semana" in texto:
                semanas = int(re.search(r'\d+', texto).group())
                return (now - timedelta(weeks=semanas)).strftime("%Y-%m-%d")
            elif re.match(r'^\d{1,2}-\d{1,2}$', texto): 
                return f"{now.year}-{texto}"
            elif re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', texto):
                return texto
        except:
            pass
        return texto