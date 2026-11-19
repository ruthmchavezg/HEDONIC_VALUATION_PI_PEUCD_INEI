import re
import json
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from config.settings import DISTRITOS_LIMA

class BaseParser:
    def recolectar_enlaces(self, engine, url_semilla: str, perfil: dict, urls_procesadas: set = None) -> list:
        pass

    def extraer_anuncio(self, engine, url: str) -> dict:
        pass 

class BabiloniaParser(BaseParser):
    
    def recolectar_enlaces(self, engine, url_semilla: str, perfil: dict, urls_procesadas: set = None) -> list:
        if urls_procesadas is None:
            urls_procesadas = set()
            
        enlaces_totales = set()
        
        separador = "&" if "?" in url_semilla else "?"
        url_lista = f"{url_semilla}{separador}vista=lista"
        
        print(f"  -> Abriendo catálogo Babilonia: {url_lista}")
        engine.navegar(url_lista)
        
        if not hasattr(engine, "page"):
            return list(enlaces_totales)
            
        try:
            # Aseguramos la vista de lista (crucial para que el botón Siguiente aparezca abajo)
            engine.page.wait_for_load_state("networkidle", timeout=8000)
            btn_lista = engine.page.locator('#mapa-to-list, text="Ver listado"').first
            if btn_lista.count() > 0 and btn_lista.is_visible():
                btn_lista.click(timeout=3000)
                engine.page.wait_for_timeout(2000)
        except:
            pass

        max_paginas = 100
        paginas_vacias = 0

        for pagina in range(1, max_paginas + 1):
            print(f"  -> Extrayendo página {pagina}...")
            
            # 1. SCROLL DINÁMICO
            try:
                for i in range(1, 6):
                    engine.page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * ({i}/5));")
                    engine.page.wait_for_timeout(800)
            except Exception:
                pass
                
            soup = engine.obtener_soup()
            enlaces_pagina = 0
            enlaces_NUEVOS_en_pagina = 0
            
            tarjetas = soup.find_all(class_=re.compile("item-card|posting-card"))
            for tarjeta in tarjetas:
                a_tag = tarjeta.find("a", href=True)
                if a_tag:
                    href = urljoin(perfil["dominio"], a_tag["href"].split("?")[0])
                    if "/inmueble/" in href.lower() and not any(exc in href.lower() for exc in ["local", "oficina", "terreno", "cochera", "proyecto", "edificio", "hotel"]):
                        if href not in enlaces_totales:
                            enlaces_totales.add(href)
                            enlaces_pagina += 1
                            if href not in urls_procesadas:
                                enlaces_NUEVOS_en_pagina += 1
            
            print(f"    [+] {enlaces_pagina} anuncios en esta pág. ({enlaces_NUEVOS_en_pagina} nunca antes vistos). Acumulado: {len(enlaces_totales)}")
            
            # 2. PARADA INTELIGENTE
            if enlaces_pagina > 0 and enlaces_NUEVOS_en_pagina == 0 and len(urls_procesadas) > 0:
                paginas_vacias += 1
                if paginas_vacias >= 2:
                    print("  [!] 2 páginas seguidas con anuncios ya conocidos.")
                    print("  [!] Abortando paginación para ahorrar tiempo.")
                    break
            elif enlaces_pagina == 0:
                paginas_vacias += 1
                if paginas_vacias >= 2:
                    print("  [-] Fin del catálogo alcanzado (2 páginas sin tarjetas).")
                    break
            else:
                paginas_vacias = 0 
                
            # 3. CLIC EN SIGUIENTE (Bypass con JavaScript Puro)
            if pagina < max_paginas:
                try:
                    # Scroll al fondo para despertar a React
                    engine.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    engine.page.wait_for_timeout(2000)

                    # Inyectamos JS directamente en el navegador para que él mismo busque y presione el botón visible
                    resultado_clic = engine.page.evaluate("""
                        () => {
                            // Agarramos todos los posibles botones "Siguiente"
                            let botones = document.querySelectorAll('button#listing-search-btn-next, button[data-val="next"], button[aria-label="siguiente" i]');
                            
                            for(let btn of botones) {
                                // offsetParent !== null es la forma definitiva de saber si un elemento es VISIBLE en pantalla
                                if(btn.offsetParent !== null) {
                                    if(btn.disabled) {
                                        return 'deshabilitado';
                                    }
                                    btn.click();
                                    return 'exito';
                                }
                            }
                            return 'no_encontrado';
                        }
                    """)

                    if resultado_clic == 'deshabilitado':
                        print("  [-] Botón 'Siguiente' deshabilitado. No hay más páginas.")
                        break
                    elif resultado_clic == 'exito':
                        # Subimos el scroll y esperamos que cargue la nueva página
                        engine.page.evaluate("window.scrollTo(0, 0);")
                        engine.page.wait_for_timeout(3500) 
                    else:
                        print("  [-] Fin del catálogo (Botón Siguiente no encontrado en el DOM).")
                        break

                except Exception as e:
                    print(f"  [-] Error al intentar hacer clic en 'Siguiente': {e}")
                    break
                    
        return list(enlaces_totales)

    def extraer_anuncio(self, engine, url: str) -> dict:
        engine.navegar(url)
        
        if hasattr(engine, "page"):
            try:
                engine.page.evaluate("""
                    document.querySelectorAll('div, section').forEach(el => {
                        if(el.innerText && el.innerText.toLowerCase().includes('política de cookies')) { el.remove(); }
                    });
                """)
                for selector_btn in ['text="Leer más"', 'text="Ver más"', '.show-more-btn']:
                    btn = engine.page.locator(selector_btn).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click(timeout=1000)
                        engine.page.wait_for_timeout(500)
            except Exception:
                pass

        soup = engine.obtener_soup()
        
        # 1. Metadato oculto JSON-LD y extracción limpia de lat/lon
        latitud = None
        longitud = None
        scripts = soup.find_all("script", type="application/ld+json")
        for s in scripts:
            texto_script = s.string or ""
            if "RealEstateListing" in texto_script or "GeoCoordinates" in texto_script:
                # Usamos Regex para atrapar los números directamente y evitar caídas por JSON malformados
                lat_match = re.search(r'"latitude"\s*:\s*(-?\d+\.\d+)', texto_script)
                lon_match = re.search(r'"longitude"\s*:\s*(-?\d+\.\d+)', texto_script)
                if lat_match:
                    latitud = float(lat_match.group(1))
                if lon_match:
                    longitud = float(lon_match.group(1))

        # 2. Encabezados
        h1_titulo = soup.find("h1", class_=re.compile("title-listing"))
        titulo = h1_titulo.get_text(strip=True) if h1_titulo else (soup.title.string if soup.title else "")
        
        div_direccion = soup.find(class_=re.compile("address|heading-address"))
        direccion = div_direccion.get_text(separator=", ", strip=True) if div_direccion else ""

        # 3. Precios brutos
        div_precios = soup.find(class_=re.compile("price|section-price"))
        precios_brutos = div_precios.get_text(separator=" ", strip=True) if div_precios else ""

        # 4. Bloques de detalles
        bloque_advance_info = " | ".join([s.get_text(strip=True) for s in soup.select('.advance-info span, .features li')])
        
        comodidades = []
        for li in soup.select('.comforts-box-item span'):
            txt = li.get_text(strip=True)
            if txt and "Ver todas" not in txt:
                comodidades.append(txt)
                
        detalles_extra = []
        for li in soup.select('.card-info ul li'):
            detalles_extra.append(li.get_text(separator=": ", strip=True))

        # 5. Descripción
        desc_contenedor = soup.select_one('.descripcion, article')
        descripcion = desc_contenedor.get_text(separator=" ", strip=True) if desc_contenedor else ""

        match_id = re.search(r'-(\d+)$', url)
        id_interno = match_id.group(1) if match_id else ""

        return {
            "id_interno": id_interno,
            "titulo": titulo,
            "direccion": direccion,
            "precios_crudos": precios_brutos,
            "info": bloque_advance_info,
            "comodidades": ", ".join(comodidades),
            "detalles_extra": " | ".join(detalles_extra),
            "descripcion": descripcion,
            "latitud": latitud,
            "longitud": longitud
        }

def obtener_parser(portal: str) -> BaseParser:
    if portal == "babilonia": return BabiloniaParser()
    return BaseParser()