import re
import json
import logging
from urllib.parse import urljoin, urlparse
from config.settings import REGEX_PATTERNS, DISTRITOS_LIMA

def extraer_texto_robusto_pw(page, selectores: list) -> str:
    for selector in selectores:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                texto = locator.inner_text(timeout=900)
                if texto and texto.strip():
                    limpio = re.sub(r'\s+', ' ', texto).strip()
                    if len(limpio) > 2:
                        return limpio
        except Exception:
            continue
    return "No especificado"

def extraer_texto_completo_pagina(page) -> str:
    try:
        texto = page.evaluate("""
            () => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, nav, footer, noscript, svg').forEach(e => e.remove());
                return clone.innerText || '';
            }
        """)
        return re.sub(r'\s+', ' ', texto).strip()
    except Exception:
        return ""

def expandir_textos_ocultos(page):
    try:
        botones = page.locator('text="Ver más", text="Leer más", text="Leer descripción completa"')
        if botones.count() > 0 and botones.first.is_visible(timeout=400):
            botones.first.click(timeout=600)
    except Exception:
        pass

def extraer_unidades_detalladas_pw(page) -> list:
    unidades_extraidas = []
    try:
        pestanas = page.locator('button[class*="unit-selection-module__rooms-button"], [class*="project-units"] button')
        if pestanas.count() == 0:
            return []

        for i in range(pestanas.count()):
            try:
                pestana = pestanas.nth(i)
                nombre_pestana = pestana.inner_text(timeout=600)
                pestana.click(timeout=800)
                page.wait_for_timeout(400)
                
                tarjetas = page.locator('div[class*="unit-selection-module__cardContainer"], [class*="unit-card"]')
                for j in range(tarjetas.count()):
                    tarjeta = tarjetas.nth(j)
                    tipo = tarjeta.locator('.unitPropertyType').inner_text(timeout=400) if tarjeta.locator('.unitPropertyType').count() > 0 else ""
                    precio = tarjeta.locator('.unitPrice').inner_text(timeout=400) if tarjeta.locator('.unitPrice').count() > 0 else ""
                    if precio:
                        caracteristicas = tarjeta.locator('div[class*="unitFeatures"]').inner_text(timeout=400) if tarjeta.locator('div[class*="unitFeatures"]').count() > 0 else ""
                        features_limpio = re.sub(r'\s+', ' ', caracteristicas).strip()
                        unidades_extraidas.append({
                            "dormitorios": nombre_pestana.strip(),
                            "tipo_unidad": tipo.strip(),
                            "precio_unidad": precio.strip(),
                            "detalles_unidad": features_limpio
                        })
            except Exception:
                continue
    except Exception:
        pass
    return unidades_extraidas

def extraer_metadatos_json_oculto(page) -> dict:
    meta = {"latitud": None, "longitud": None, "precio_json": None, "moneda_json": None, "descripcion_json": None, "titulo_json": None}
    try:
        html = page.content()
        scripts = page.locator('script[type="application/ld+json"]')
        for i in range(scripts.count()):
            try:
                raw_json = scripts.nth(i).inner_text(timeout=600)
                data = json.loads(raw_json)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if "@graph" in item and isinstance(item["@graph"], list):
                        items.extend(item["@graph"])
                    if not meta["titulo_json"] and item.get("name"):
                        meta["titulo_json"] = str(item.get("name"))
                    if not meta["descripcion_json"] and item.get("description"):
                        meta["descripcion_json"] = str(item.get("description"))
                    if "geo" in item and isinstance(item["geo"], dict):
                        lat = item["geo"].get("latitude")
                        lng = item["geo"].get("longitude")
                        if lat and lng:
                            meta["latitud"] = float(lat)
                            meta["longitud"] = float(lng)
                    if "offers" in item:
                        offers = item["offers"]
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict):
                            p = offers.get("price") or offers.get("lowPrice")
                            c = offers.get("priceCurrency")
                            if p:
                                meta["precio_json"] = float(str(p).replace(",", ""))
                            if c in ["USD", "PEN"]:
                                meta["moneda_json"] = c
            except Exception:
                continue

        if not meta["latitud"]:
            patrones_coord = [
                r'"lat(?:itude)?"\s*:\s*(-1[123]\.\d+)\s*,\s*"(?:lng|lon|longitude)"\s*:\s*(-7[67]\.\d+)',
                r'center=(-1[123]\.\d+)(?:%2C|,)(-7[67]\.\d+)',
                r'\[(-1[123]\.\d{4,}),\s*(-7[67]\.\d{4,})\]',
                r'lat=(-1[123]\.\d+)&(?:amp;)?lng=(-7[67]\.\d+)'
            ]
            for pat in patrones_coord:
                m_coord = re.search(pat, html)
                if m_coord:
                    meta["latitud"] = float(m_coord.group(1))
                    meta["longitud"] = float(m_coord.group(2))
                    break
    except Exception:
        pass
    return meta

def _limpiar_numero_monetario(cadena: str) -> float | None:
    if not cadena:
        return None
    limpio = cadena.strip()
    if re.search(r"[.,]\d{2}$", limpio):
        limpio = limpio[:-3]
    solo_digitos = re.sub(r"[^\d]", "", limpio)
    try:
        val = float(solo_digitos)
        return val if val >= 100 else None
    except ValueError:
        return None

def extraer_precios_soles_dolares(texto_precio: str, meta_json: dict, texto_completo: str = "") -> tuple[float | None, float | None]:
    precio_soles = None
    precio_dolares = None

    fuente_prioritaria = f"{texto_precio or ''} | {texto_completo[:1200]}"

    m_pen = re.search(r"(?:S/|S/\.|PEN)\s*(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|\d{3,6})", fuente_prioritaria, re.IGNORECASE)
    if m_pen:
        precio_soles = _limpiar_numero_monetario(m_pen.group(1))

    m_usd = re.search(r"(?:US\$|USD|\$)\s*(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|\d{3,6})", fuente_prioritaria, re.IGNORECASE)
    if m_usd:
        precio_dolares = _limpiar_numero_monetario(m_usd.group(1))

    if meta_json.get("precio_json") and meta_json["precio_json"] >= 100:
        mon_json = meta_json.get("moneda_json")
        if mon_json == "PEN" and precio_soles is None:
            precio_soles = float(meta_json["precio_json"])
        elif mon_json == "USD" and precio_dolares is None:
            precio_dolares = float(meta_json["precio_json"])

    return precio_soles, precio_dolares

def detectar_distrito(ubicacion_str: str, titulo_str: str, texto_completo: str) -> str | None:
    combinado = f"{ubicacion_str} | {titulo_str} | {texto_completo[:800]}".lower()
    for d in DISTRITOS_LIMA:
        if re.search(rf"\b{re.escape(d.lower())}\b", combinado):
            return "Santiago de Surco" if d == "Surco" else ("Magdalena del Mar" if d == "Magdalena" else d)
    partes = [x.strip() for x in (ubicacion_str or "").split(",") if x.strip() and x.strip() != "No especificado"]
    return partes[-2] if len(partes) >= 2 else (partes[0] if partes else None)

def parsear_atributos_regex(texto_combinado: str) -> dict:
    t = (texto_combinado or "").lower()
    m_tot = REGEX_PATTERNS["area_total"].search(t)
    m_con = REGEX_PATTERNS["area_construida"].search(t)
    m_dor = REGEX_PATTERNS["dormitorios"].search(t)
    m_ban = REGEX_PATTERNS["banos"].search(t)
    m_est = REGEX_PATTERNS["estacionamientos"].search(t)
    m_ant = REGEX_PATTERNS["antiguedad"].search(t)
    m_man = REGEX_PATTERNS["mantenimiento"].search(t)

    antiguedad = int(m_ant.group(1)) if m_ant else (0 if ("estreno" in t or "en construcción" in t) else None)
    area_tot = float(m_tot.group(1).replace(",", ".")) if m_tot else None
    area_con = float(m_con.group(1).replace(",", ".")) if m_con else area_tot
    mant = float(re.sub(r"[^\d]", "", m_man.group(1))) if m_man else None

    return {
        "area_total_m2": area_tot,
        "area_construida_m2": area_con,
        "dormitorios_num": int(m_dor.group(1)) if m_dor else None,
        "banos_num": int(m_ban.group(1)) if m_ban else None,
        "estacionamientos_num": int(m_est.group(1)) if m_est else None,
        "antiguedad_anos": antiguedad,
        "mantenimiento_soles": mant,
    }

def _es_url_inmueble_valida(url_completa: str, dominio: str, filtros: list) -> bool:
    if not url_completa.startswith(dominio):
        return False
    parsed = urlparse(url_completa)
    path = parsed.path.lower()
    exclusiones = [
        "/login", "/registro", "/contacto", "/blog", "/noticias",
        "/agentes", "/resultados/", "/buscar/", "/alquiler/casas",
        "/alquiler/departamentos", "/alquiler/habitaciones", "/inmuebles/"
    ]
    if path in ["/", ""] or any(x in path for x in exclusiones):
        return False
    if any(f.lower() in url_completa.lower() for f in filtros):
        if re.search(r"\d{4,}", url_completa) or len(path.strip("/").split("/")) >= 2:
            return True
    return False

def recolectar_enlaces_portal(engine, perfil_portal: dict, url_semilla: str, max_paginas: int) -> list:
    enlaces_ordenados = []
    enlaces_vistos = set()
    url_actual = url_semilla
    dominio = perfil_portal["dominio"]
    selector_cards = perfil_portal["selector_enlaces_listado"]
    filtros = perfil_portal["filtro_url_inmueble"]

    for pagina_actual in range(1, max_paginas + 1):
        logging.info(f"[+] [{dominio}] Página {pagina_actual}/{max_paginas}: {url_actual}")
        try:
            engine.navegar_seguro(url_actual)
        except Exception as e:
            logging.warning(f"[!] Error cargando listado {url_actual}: {e}")
            break

        try:
            rutas_crudas = []
            # Extracción ultrarrápida por BeautifulSoup si se usó curl_cffi (Adiós Cloudflare)
            if getattr(engine, "_usando_cffi", False):
                soup = engine.soup()
                elementos = soup.select(selector_cards) if selector_cards else soup.select('a[href]')
                for el in elementos:
                    r = el.get("data-to-posting") or el.get("href")
                    if r:
                        rutas_crudas.append(r)
                # Respaldo Regex en HTML crudo si soup no halló suficientes
                if len(rutas_crudas) < 3:
                    html_raw = engine.content()
                    for f in filtros:
                        hallados = re.findall(rf'["\']((?:https?://{re.escape(urlparse(dominio).netloc)})?/[a-zA-Z0-9_/-]*{re.escape(f.strip("/"))}[a-zA-Z0-9_/-]+(?:\.html)?)["\']', html_raw)
                        rutas_crudas.extend(hallados)
            else:
                # Extracción interactiva estándar mediante Playwright
                try:
                    engine.page.wait_for_selector(selector_cards, timeout=3000)
                except Exception:
                    engine.page.wait_for_timeout(1000)

                rutas_crudas = engine.page.evaluate("""
                    (selector) => {
                        let els = [];
                        try {
                            els = Array.from(document.querySelectorAll(selector));
                        } catch (e) {
                            els = [];
                        }
                        const todas = els.length > 0 ? els : Array.from(document.querySelectorAll('a[href], [data-to-posting]'));
                        return todas.map(el => el.getAttribute('data-to-posting') || el.getAttribute('href')).filter(Boolean);
                    }
                """, selector_cards)

            nuevos_en_pagina = 0
            for ruta in rutas_crudas:
                ruta_abs = urljoin(dominio, ruta.split("?")[0].strip())
                if _es_url_inmueble_valida(ruta_abs, dominio, filtros):
                    if ruta_abs not in enlaces_vistos:
                        enlaces_vistos.add(ruta_abs)
                        enlaces_ordenados.append(ruta_abs)
                        nuevos_en_pagina += 1

            logging.info(f"    -> +{nuevos_en_pagina} enlaces en esta página | Total acumulados: {len(enlaces_ordenados)}")
            if nuevos_en_pagina == 0 and pagina_actual > 1:
                break
        except Exception as e:
            logging.warning(f"    [!] Error extrayendo enlaces: {e}")

        if pagina_actual >= max_paginas:
            break

        # Paginación
        avanzado = False
        if not getattr(engine, "_usando_cffi", False):
            for sel_next in perfil_portal["selector_siguiente_pagina"]:
                try:
                    boton_sig = engine.page.locator(sel_next).first
                    if boton_sig.count() > 0 and boton_sig.is_visible(timeout=500):
                        href_sig = boton_sig.get_attribute("href", timeout=500)
                        if href_sig and not href_sig.startswith("javascript") and href_sig != "#":
                            url_actual = urljoin(dominio, href_sig)
                            avanzado = True
                            break
                except Exception:
                    continue

        if not avanzado:
            patron = perfil_portal.get("patron_paginacion", "?page={page}")
            if patron == "-pagina-{page}.html" and url_semilla.endswith(".html"):
                url_actual = url_semilla.replace(".html", f"-pagina-{pagina_actual + 1}.html")
            elif patron.startswith("/"):
                url_actual = url_semilla.rstrip("/") + patron.format(page=pagina_actual + 1)
            elif patron.startswith("&"):
                url_actual = f"{url_semilla}{patron.format(page=pagina_actual + 1)}"
            else:
                sep = "&" if "?" in url_semilla else "?"
                url_actual = f"{url_semilla}{sep}page={pagina_actual + 1}"

    return enlaces_ordenados