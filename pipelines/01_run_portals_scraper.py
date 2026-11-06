import argparse
import hashlib
import json
import logging
from datetime import datetime

from config.settings import (
    PERFILES_PORTALES, ROTATE_CONTEXT_EVERY, REGEX_PATTERNS, LOG_DIR
)
from src.schemas.property_schema import OfertaInmobiliariaINEI
from src.scraping.bcrp_client import obtener_tc_bcrp
from src.scraping.stealth_fetcher import StealthBrowserEngine
from src.scraping.parsers import (
    recolectar_enlaces_portal,
    extraer_texto_completo_pagina, expandir_textos_ocultos,
    extraer_unidades_detalladas_pw, extraer_metadatos_json_oculto,
    extraer_precios_soles_dolares, parsear_atributos_regex, detectar_distrito
)
from src.scraping.storage import (
    cargar_o_guardar_enlaces_cache, limpiar_cache_enlaces,
    obtener_estado_historico_interim, guardar_lote_incremental_silver,
    registrar_historial_scrapeo
)

def configurar_logs():
    fecha_log = datetime.now().strftime("%Y_%m_%d")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "scraping" / f"pipeline_inei_{fecha_log}.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

def generar_id_determinista(nombre_portal: str, enlace: str) -> str:
    enlace_limpio = enlace.split("?")[0].rstrip("/")
    hash_unico = hashlib.md5(enlace_limpio.encode("utf-8")).hexdigest()[:8]
    m_id = REGEX_PATTERNS["id_anuncio"].search(enlace_limpio)
    if m_id:
        return f"{nombre_portal}_{m_id.group(1)}_{hash_unico[:4]}"
    return f"{nombre_portal}_{hash_unico}"

def procesar_portal(nombre_portal: str, max_paginas: int, headless: bool, tc_bcrp: float):
    perfil = PERFILES_PORTALES[nombre_portal]
    reglas = perfil["reglas_extraccion"]
    
    scrape_id = f"{nombre_portal}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    inicio_ts = datetime.now().isoformat(timespec="seconds")
    
    ids_historicos, urls_historicas = obtener_estado_historico_interim()
    
    engine = StealthBrowserEngine(headless=headless)
    engine.start()
    
    buffer_lote = []
    total_nuevos_guardados = 0
    catalogo_enlaces = []
    estado_final = "COMPLETADO"

    try:
        catalogo_enlaces = cargar_o_guardar_enlaces_cache(nombre_portal)
        if not catalogo_enlaces:
            catalogo_enlaces = []
            for tipo_inm, urls_semilla_lista in perfil["urls_semilla"]:
                if isinstance(urls_semilla_lista, str):
                    urls_semilla_lista = [urls_semilla_lista]

                logging.info(f"[{nombre_portal.upper()}] Buscando alquileres de: {tipo_inm}")
                urls_encontradas_tipo = []

                for url_candidata in urls_semilla_lista:
                    urls_encontradas_tipo = recolectar_enlaces_portal(engine, perfil, url_candidata, max_paginas)
                    if urls_encontradas_tipo:
                        break
                    logging.info(f"    [*] Sin resultados en {url_candidata}. Probando búsqueda alternativa (cuartos/general)...")

                for u in urls_encontradas_tipo:
                    catalogo_enlaces.append({"url": u, "tipo_inmueble": tipo_inm})

            if catalogo_enlaces:
                cargar_o_guardar_enlaces_cache(nombre_portal, catalogo_enlaces)

        pendientes = []
        urls_vistas_sesion = set()
        for item in catalogo_enlaces:
            enlace = item["url"]
            id_prov = generar_id_determinista(nombre_portal, enlace)
            if enlace not in urls_historicas and id_prov not in ids_historicos and enlace not in urls_vistas_sesion:
                pendientes.append(item)
                urls_vistas_sesion.add(enlace)

        logging.info(
            f"\n[{nombre_portal.upper()}] Enlaces totales: {len(catalogo_enlaces)} | "
            f"Ya en Base Maestra: {len(catalogo_enlaces) - len(pendientes)} | "
            f"Pendientes por raspar: {len(pendientes)}"
        )

        if not pendientes:
            limpiar_cache_enlaces(nombre_portal)
            estado_final = "SIN_NUEVOS"
            return

        for idx, item_url in enumerate(pendientes, 1):
            enlace = item_url["url"]
            tipo_inmueble = item_url["tipo_inmueble"]
            timestamp_captura = datetime.now().isoformat(timespec="seconds")
            logging.info(f"[{idx}/{len(pendientes)}] Extrayendo ({nombre_portal} - {tipo_inmueble}): {enlace}")

            try:
                if idx % ROTATE_CONTEXT_EVERY == 0:
                    engine.rotar_contexto()

                engine.navegar_seguro(enlace)
                expandir_textos_ocultos(engine.page)
                
                unidades = extraer_unidades_detalladas_pw(engine.page)
                meta_json = extraer_metadatos_json_oculto(engine.page)
                texto_pagina = extraer_texto_completo_pagina(engine.page)
                id_base = generar_id_determinista(nombre_portal, enlace)

                campos_extraidos = {}
                for campo, selectores in reglas.items():
                    campos_extraidos[campo] = extraer_texto_robusto_pw(engine.page, selectores)

                texto_bloque_precio = campos_extraidos.pop("bloque_precio", "No especificado")

                inmueble_raw = {
                    "id_anuncio": id_base,
                    "scrape_id": scrape_id,
                    "fecha_hora_scrapeo": timestamp_captura,
                    "portal": nombre_portal,
                    "modalidad": "alquiler",
                    "tipo_inmueble": tipo_inmueble,
                    "url": enlace,
                    "latitud": meta_json["latitud"],
                    "longitud": meta_json["longitud"],
                    "tipo_cambio_referencial_bcrp": tc_bcrp,
                    "texto_completo_anuncio": texto_pagina[:4000],
                    **campos_extraidos
                }

                if inmueble_raw.get("titulo") == "No especificado" and meta_json["titulo_json"]:
                    inmueble_raw["titulo"] = meta_json["titulo_json"]
                if inmueble_raw.get("descripcion") == "No especificado" and meta_json["descripcion_json"]:
                    inmueble_raw["descripcion"] = meta_json["descripcion_json"]
                if inmueble_raw.get("descripcion") == "No especificado" and texto_pagina:
                    inmueble_raw["descripcion"] = texto_pagina[:1500]

                inmueble_raw["distrito"] = detectar_distrito(
                    inmueble_raw.get("ubicacion", ""), inmueble_raw.get("titulo", ""), texto_pagina
                )

                if not unidades:
                    fila = inmueble_raw.copy()
                    p_soles, p_dolares = extraer_precios_soles_dolares(texto_bloque_precio, meta_json, texto_pagina)
                    fila["precio_soles"] = p_soles
                    fila["precio_dolares"] = p_dolares
                    
                    texto_combinado = f"{fila['titulo']} | {fila['datos_principales_generales']} | {fila['caracteristicas']} | {fila['descripcion']} | {texto_pagina}"
                    fila.update(parsear_atributos_regex(texto_combinado))
                    
                    validado = OfertaInmobiliariaINEI(**fila)
                    buffer_lote.append(validado.model_dump())
                else:
                    for idx_u, u in enumerate(unidades, 1):
                        fila = inmueble_raw.copy()
                        fila["id_anuncio"] = f"{id_base}_u{idx_u}"
                        fila["es_proyecto_multiunidad"] = True
                        p_soles, p_dolares = extraer_precios_soles_dolares(u["precio_unidad"], {}, texto_pagina)
                        fila["precio_soles"] = p_soles
                        fila["precio_dolares"] = p_dolares
                        fila["unidades_detalladas"] = json.dumps(u, ensure_ascii=False)
                        texto_u = f"{u['dormitorios']} | {u['detalles_unidad']} | {fila['estado_proyecto']} | {texto_pagina}"
                        fila.update(parsear_atributos_regex(texto_u))
                        
                        validado = OfertaInmobiliariaINEI(**fila)
                        buffer_lote.append(validado.model_dump())

                if len(buffer_lote) >= 5:
                    guardar_lote_incremental_silver(buffer_lote, nombre_portal, scrape_id)
                    total_nuevos_guardados += len(buffer_lote)
                    buffer_lote.clear()

            except KeyboardInterrupt:
                logging.warning("[!] Interrupción manual detectada. Guardando progreso actual...")
                estado_final = "INTERRUMPIDO_GUARDADO"
                raise
            except Exception as e:
                logging.error(f"  -> Error aislando anuncio {enlace}: {e}")
                continue

        limpiar_cache_enlaces(nombre_portal)

    except KeyboardInterrupt:
        estado_final = "INTERRUMPIDO_GUARDADO"
    finally:
        if buffer_lote:
            guardar_lote_incremental_silver(buffer_lote, nombre_portal, scrape_id)
            total_nuevos_guardados += len(buffer_lote)
            buffer_lote.clear()
            
        engine.close()
        fin_ts = datetime.now().isoformat(timespec="seconds")
        registrar_historial_scrapeo(
            scrape_id, nombre_portal, inicio_ts, fin_ts,
            len(catalogo_enlaces), total_nuevos_guardados, estado_final
        )

if __name__ == "__main__":
    configurar_logs()
    lista_portales = list(PERFILES_PORTALES.keys())
    parser = argparse.ArgumentParser(description="Pipeline Multi-Portal de Alquileres - INEI")
    parser.add_argument("--portal", type=str, default="todos", choices=lista_portales + ["todos"])
    parser.add_argument("--paginas", type=int, default=999)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    tc_hoy = obtener_tc_bcrp()
    portales_objetivo = lista_portales if args.portal == "todos" else [args.portal]

    for p in portales_objetivo:
        procesar_portal(nombre_portal=p, max_paginas=args.paginas, headless=not args.visible, tc_bcrp=tc_hoy)