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
            
            # 1. SCROLL DINÁMICO Y ESPERA EXPLÍCITA
            try:
                # Bajamos en 5 tramos suaves (20%, 40%, 60%, 80%, 100%) simulando la rueda del mouse
                for i in range(1, 6):
                    engine.page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * ({i}/5));")
                    engine.page.wait_for_timeout(800)
                
                # Le ordenamos a Playwright que ESPERE HASTA 15 SEGUNDOS a que el botón "Siguiente" sea visible.
                # Si aparece al segundo 2, avanza inmediatamente sin perder tiempo.
                if pagina < max_paginas:
                    btn_sig_wait = engine.page.get_by_text("Siguiente", exact=True).last
                    btn_sig_wait.wait_for(state="visible", timeout=15000)
            except Exception:
                # Si pasan los 15 segs y no aparece, ignoramos el error porque podríamos estar en la última página
                pass
                
            soup = engine.obtener_soup()
            enlaces_pagina = 0
            enlaces_NUEVOS_en_pagina = 0
            
            tarjetas = soup.find_all(class_=re.compile("item-card"))
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
            
            # 2. PARADA INTELIGENTE FLEXIBLE
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
                paginas_vacias = 0  # Reinicia si encuentra al menos 1 anuncio nuevo
                
            # 3. CLIC EN SIGUIENTE
            if pagina < max_paginas:
                try:
                    btn_sig = engine.page.get_by_text("Siguiente", exact=True).last
                    if btn_sig.count() > 0 and btn_sig.is_visible():
                        if btn_sig.get_attribute("disabled") is not None or "disabled" in btn_sig.get_attribute("class"):
                            print("  [-] Botón 'Siguiente' deshabilitado. No hay más páginas.")
                            break
                            
                        btn_sig.click(force=True, timeout=5000)
                        
                        # Subimos el scroll para que React cargue la nueva página desde arriba
                        engine.page.evaluate("window.scrollTo(0, 0);")
                        
                        # Esperamos a que el navegador procese los nuevos datos
                        engine.page.wait_for_timeout(3500) 
                    else:
                        print("  [-] No se detectó botón 'Siguiente' visible en pantalla. Fin del recorrido.")
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
        
        json_ld_raw = ""
        scripts = soup.find_all("script", type="application/ld+json")
        for s in scripts:
            if "RealEstateListing" in (s.string or "") or "GeoCoordinates" in (s.string or ""):
                json_ld_raw = s.string

        h1_titulo = soup.find("h1", class_=re.compile("title-listing"))
        titulo = h1_titulo.get_text(strip=True) if h1_titulo else (soup.title.string if soup.title else "")
        
        div_direccion = soup.find(class_=re.compile("address|heading-address"))
        direccion = div_direccion.get_text(separator=", ", strip=True) if div_direccion else ""

        div_precios = soup.find(class_=re.compile("price|section-price"))
        precios_brutos = div_precios.get_text(separator=" ", strip=True) if div_precios else ""

        bloque_advance_info = " | ".join([s.get_text(strip=True) for s in soup.select('.advance-info span, .features li')])
        
        comodidades = []
        for li in soup.select('.comforts-box-item span'):
            txt = li.get_text(strip=True)
            if txt and "Ver todas" not in txt:
                comodidades.append(txt)
                
        detalles_extra = []
        for li in soup.select('.card-info ul li'):
            detalles_extra.append(li.get_text(separator=": ", strip=True))

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
            "json_ld": json_ld_raw
        }

def obtener_parser(portal: str) -> BaseParser:
    if portal == "babilonia": return BabiloniaParser()
    return BaseParser()