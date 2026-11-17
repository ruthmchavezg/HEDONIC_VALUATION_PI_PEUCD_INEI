# [COMENTARIO] IMPORTACIÓN DE LIBRERÍAS Y MÓDULOS DEL PROYECTO
# Lo que hace: Importa librerías estándar (argparse, json, os, datetime), herramientas de validación (Pydantic) y los módulos personalizados de configuración, extracción, limpieza y almacenamiento.
# Para qué sirve: Reúne todas las piezas del ecosistema (configuraciones, modelos de validación y funciones de red/almacenamiento) para que el orquestador principal pueda ejecutar el pipeline de principio a fin.
# Metodología: Arquitectura Modular y Desacoplamiento (Separation of Concerns), manteniendo la lógica de control separada de los detalles de extracción y almacenamiento[cite: 13].
import argparse
import json
import logging
import math
import os
from datetime import datetime
from pydantic import ValidationError

from config.settings import (
    PERFILES_PORTALES, CHECKPOINT_INTERVAL,
    ROTATE_CONTEXT_EVERY, REGEX_PATTERNS, LOG_DIR, PROCESSED_DIR
)
from src.schemas.schemas import OfertaInmobiliariaINEI
from src.scraping.bcrp_client import obtener_tc_bcrp
from src.scraping.stealth_fetcher import StealthBrowserEngine
from src.scraping.parsers import (
    recolectar_enlaces_portal, extraer_texto_robusto_pw,
    expandir_textos_ocultos, extraer_unidades_detalladas_pw,
    extraer_metadatos_json_oculto, limpiar_precio_moneda, parsear_atributos_regex
)
from src.scraping.storage import (
    cargar_o_guardar_enlaces_cache, cargar_checkpoint_previo,
    guardar_checkpoint_emergencia, exportar_dataset_final_gold
)

# [COMENTARIO] FUNCIÓN: configurar_logs
# Lo que hace: Configura el sistema de registro (logging) para que imprima mensajes con formato (fecha, nivel, mensaje) tanto en la consola de comandos como en un archivo de texto dentro de la carpeta logs/.
# Para qué sirve: Permite monitorear en tiempo real el comportamiento del bot y guarda un historial permanente para poder auditar errores o revisar el rendimiento de extracciones pasadas sin perder detalles.
# Metodología: Trazabilidad de Eventos (Event Logging) y Auditoría Continua.
def configurar_logs():
    fecha_log = datetime.now().strftime("%Y_%m_%d")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / f"pipeline_inei_{fecha_log}.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

# [COMENTARIO] FUNCIÓN: obtener_ids_historicos_existentes
# Lo que hace: Lee la base de datos maestra (en formato Parquet o CSV) que contiene todos los inmuebles extraídos en días o semanas anteriores y extrae un conjunto (set) único con los IDs de esos anuncios.
# Para qué sirve: Crea una lista de "elementos ya conocidos" para evitar que el scraper vuelva a procesar y guardar anuncios antiguos, ahorrando tiempo y reduciendo el riesgo de bloqueo por sobrecarga de peticiones.
# Metodología: Extracción Incremental (Delta Scraping) y Principio de Idempotencia[cite: 13, 14].
def obtener_ids_historicos_existentes() -> set:
    """
    Carga los IDs ya procesados en la base maestra histórica del INEI
    para garantizar idempotencia y evitar re-scraping de anuncios antiguos.
    """
    master_parquet = PROCESSED_DIR / "base_maestra_inmobiliaria_inei.parquet"
    master_csv = PROCESSED_DIR / "base_maestra_inmobiliaria_inei.csv"
    
    ids_historicos = set()
    if master_parquet.exists():
        import pandas as pd
        df_hist = pd.read_parquet(master_parquet, columns=["id_anuncio"])
        ids_historicos = set(df_hist["id_anuncio"].dropna().unique())
    elif master_csv.exists():
        import pandas as pd
        df_hist = pd.read_csv(master_csv, usecols=["id_anuncio"])
        ids_historicos = set(df_hist["id_anuncio"].dropna().unique())
        
    logging.info(f"[+] IDs históricos cargados en memoria para filtro incremental: {len(ids_historicos)} anuncios previos.")
    return ids_historicos

# [COMENTARIO] FUNCIÓN: procesar_portal (Orquestador Principal)
# Lo que hace: Es la función núcleo. Carga el perfil del portal elegido, inicializa las bases históricas y de checkpoints, y levanta el navegador Stealth para comenzar la extracción en fases.
# Para qué sirve: Dirige todo el ciclo de vida del scraping para un portal específico (como Babilonia o Urbania), controlando cuándo navegar, cuándo filtrar y cuándo guardar la información.
# Metodología: Arquitectura Guiada por Configuración (Configuration-Driven Architecture) y Patrón Orquestador[cite: 13].
def procesar_portal(nombre_portal: str, max_paginas: int, headless: bool, tc_bcrp: float):
    perfil = PERFILES_PORTALES[nombre_portal]
    reglas = perfil["reglas_extraccion"]
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")

    filas_validadas, urls_ya_procesadas = cargar_checkpoint_previo(nombre_portal, fecha_hoy)
    ids_historicos = obtener_ids_historicos_existentes()
    
    engine = StealthBrowserEngine(headless=headless)
    engine.start()

    try:
        # FASE 1: Cosechar URLs de forma masiva (con detección dinámica de páginas)
        # [COMENTARIO] FASE 1: RECOLECCIÓN MASIVA DE ENLACES
        # Lo que hace: Revisa si hay un caché de enlaces para hoy; si no lo hay, navega por las páginas del listado de la categoría (casa, departamento, terreno) para recopilar todas las URLs de los inmuebles.
        # Para qué sirve: Define el universo total de propiedades disponibles en el portal web en ese instante antes de entrar al detalle de cada una, protegiendo el avance con un archivo de caché.
        # Metodología: Rastreo Secuencial (Web Crawling) y Almacenamiento en Caché (Caching State).
        catalogo_enlaces = cargar_o_guardar_enlaces_cache(nombre_portal, fecha_hoy)
        if not catalogo_enlaces:
            catalogo_enlaces = []
            for tipo_inm, url_semilla in perfil["urls_semilla"]:
                logging.info(f"[{nombre_portal.upper()}] Iniciando recolección masiva para categoría: {tipo_inm}")
                urls_tipo = recolectar_enlaces_portal(engine, perfil, url_semilla, max_paginas)
                for u in urls_tipo:
                    catalogo_enlaces.append({"url": u, "tipo_inmueble": tipo_inm})
            cargar_o_guardar_enlaces_cache(nombre_portal, fecha_hoy, catalogo_enlaces)

        # FASE 1.5: Filtro Delta (Descartar lo que ya está en el histórico o en el checkpoint de hoy)
        # [COMENTARIO] FASE 1.5: FILTRO INCREMENTAL (DELTA)
        # Lo que hace: Compara los IDs de los enlaces recién recolectados con los IDs del historial (ids_historicos) y del checkpoint diario (urls_ya_procesadas). Solo conserva los enlaces verdaderamente nuevos.
        # Para qué sirve: Evita procesar y gastar recursos en anuncios que ya existen en la base de datos, acelerando exponencialmente la ejecución en los scrapeos recurrentes (lunes y jueves).
        # Metodología: Deduplicación en Memoria y Carga Incremental (Delta Load).
        pendientes = []
        for item in catalogo_enlaces:
            enlace = item["url"]
            # Extraer ID provisional para validar si ya fue procesado antes
            m_id = REGEX_PATTERNS["id_anuncio"].search(enlace)
            id_prov = f"{nombre_portal}_{m_id.group(1)}" if m_id else f"{nombre_portal}_{ abs(hash(enlace)) % 100000000 }"
            
            if enlace not in urls_ya_procesadas and id_prov not in ids_historicos:
                pendientes.append(item)

        logging.info(f"\n[{nombre_portal.upper()}] Resumen Cosecha | Total catálogo web: {len(catalogo_enlaces)} | Ya existentes en histórico: {len(catalogo_enlaces) - len(pendientes)} | Nuevos a raspar hoy: {len(pendientes)}")

        if not pendientes:
            logging.info(f"[✓] No hay anuncios nuevos en {nombre_portal}. La base maestra ya se encuentra 100% actualizada.")
            return

        # FASE 2: Extracción profunda exclusivamente de los nuevos registros
        # [COMENTARIO] FASE 2: EXTRACCIÓN PROFUNDA Y ROTACIÓN PREVENTIVA
        # Lo que hace: Itera sobre los enlaces nuevos, rotando la huella digital y el proxy cada cierto número de peticiones (ROTATE_CONTEXT_EVERY), visita la página y extrae el texto, JSON oculto y sub-unidades.
        # Para qué sirve: Es el motor pesado que recopila toda la información detallada de cada anuncio nuevo eludiendo las defensas de seguridad del servidor (Cloudflare) gracias a la rotación.
        # Metodología: Extracción Híbrida (DOM + SSR JSON) y Rotación de Identidad Preventiva (Identity Rotation)[cite: 13, 14].
        for idx, item_url in enumerate(pendientes, 1):
            enlace = item_url["url"]
            tipo_inmueble = item_url["tipo_inmueble"]
            logging.info(f"[{idx}/{len(pendientes)}] Extrayendo detalle nuevo ({nombre_portal}): {enlace}")

            try:
                # Rotación preventiva de contexto para evitar bloqueos por sesión prolongada
                if idx % ROTATE_CONTEXT_EVERY == 0:
                    engine.rotar_contexto()

                engine.navegar_seguro(enlace)
                expandir_textos_ocultos(engine.page)
                unidades = extraer_unidades_detalladas_pw(engine.page)
                meta_json = extraer_metadatos_json_oculto(engine.page)

                m_id = REGEX_PATTERNS["id_anuncio"].search(enlace)
                id_base = f"{nombre_portal}_{m_id.group(1)}" if m_id else f"{nombre_portal}_{ abs(hash(enlace)) % 100000000 }"

                inmueble_raw = {
                    "id_anuncio": id_base,
                    "fecha_captura": fecha_hoy,
                    "portal": nombre_portal,
                    "tipo_inmueble": tipo_inmueble,
                    "url": enlace,
                    "latitud": meta_json["latitud"],
                    "longitud": meta_json["longitud"],
                    "tipo_cambio_bcrp": tc_bcrp,
                }

                for campo, selectores in reglas.items():
                    inmueble_raw[campo] = extraer_texto_robusto_pw(engine.page, selectores)

                if inmueble_raw["titulo"] == "No especificado" and meta_json["titulo_json"]:
                    inmueble_raw["titulo"] = meta_json["titulo_json"]
                if inmueble_raw["descripcion"] == "No especificado" and meta_json["descripcion_json"]:
                    inmueble_raw["descripcion"] = meta_json["descripcion_json"]

                partes_ubic = [x.strip() for x in inmueble_raw["ubicacion"].split(",") if x.strip()]
                inmueble_raw["distrito"] = partes_ubic[-2] if len(partes_ubic) >= 2 else (partes_ubic[0] if partes_ubic else None)

                # Estructuración y validación Fail-Fast con Pydantic
                # [COMENTARIO] ESTRUCTURACIÓN Y VALIDACIÓN (FAIL-FAST)
                # Lo que hace: Consolida los datos crudos extraídos, limpia el precio según el BCRP y pasa el diccionario por el esquema de Pydantic (OfertaInmobiliariaINEI) para validar que los tipos y valores sean correctos.
                # Para qué sirve: Filtra inmediatamente cualquier dato corrupto, malformado o fuera de los límites espaciales de Lima, asegurando que la base de datos mantenga una calidad impecable.
                # Metodología: Validación de Esquemas Restrictivos (Fail-Fast Validation) y Desglose Atómico (1 Fila = 1 Inmueble)[cite: 13, 14].
                if not unidades:
                    fila = inmueble_raw.copy()
                    mon, monto = limpiar_precio_moneda(fila["precio_general"], meta_json)
                    fila["moneda_original"] = mon or "PEN"
                    fila["precio_original"] = monto
                    texto_completo = f"{fila['titulo']} | {fila['datos_principales_generales']} | {fila['caracteristicas']} | {fila['descripcion']}"
                    fila.update(parsear_atributos_regex(texto_completo))

                    validado = OfertaInmobiliariaINEI(**fila)
                    filas_validadas.append(validado.model_dump())
                else:
                    for idx_u, u in enumerate(unidades, 1):
                        fila = inmueble_raw.copy()
                        fila["id_anuncio"] = f"{id_base}_u{idx_u}"
                        fila["es_proyecto_multiunidad"] = True
                        mon, monto = limpiar_precio_moneda(u["precio_unidad"], {})
                        fila["moneda_original"] = mon or "PEN"
                        fila["precio_original"] = monto
                        fila["unidades_detalladas"] = json.dumps(u, ensure_ascii=False)
                        texto_u = f"{u['dormitorios']} | {u['detalles_unidad']} | {fila['estado_proyecto']}"
                        fila.update(parsear_atributos_regex(texto_u))

                        validado = OfertaInmobiliariaINEI(**fila)
                        filas_validadas.append(validado.model_dump())

                # [COMENTARIO] GUARDADO INTERMEDIO (CHECKPOINT)
                # Lo que hace: Cada cierto número de anuncios (CHECKPOINT_INTERVAL), llama a la función para guardar el progreso actual en un archivo CSV temporal.
                # Para qué sirve: Previene la pérdida total de los datos procesados en caso de que el script sufra una detención abrupta (corte de luz, crash del SO).
                # Metodología: Puntos de control incrementales (Incremental Checkpointing).
                if idx % CHECKPOINT_INTERVAL == 0:
                    guardar_checkpoint_emergencia(filas_validadas, nombre_portal, fecha_hoy)

            except ValidationError as ve:
                logging.warning(f"  [Filtro Fail-Fast] Anuncio descartado por datos incompletos: {ve.errors()[0]['msg']}")
            except Exception as e:
                logging.error(f"  -> Error procesando {enlace}: {e}")
                continue

    finally:
        engine.close()

    # FASE 3: Exportación Gold consolidada
    # [COMENTARIO] EXPORTACIÓN FINAL (CAPA GOLD)
    # Lo que hace: Toma todos los registros validados de la sesión, los une al archivo histórico y guarda el resultado definitivo en CSV y Parquet.
    # Para qué sirve: Consolida la información extraída y la deja lista para ser consumida directamente por los scripts de análisis y modelamiento econométrico del INEI.
    # Metodología: Arquitectura Medallion (Exportación a Capa Gold / Processed Data)[cite: 13, 14].
    exportar_dataset_final_gold(filas_validadas, nombre_portal, fecha_hoy)

# [COMENTARIO] BLOQUE DE EJECUCIÓN PRINCIPAL (CLI)
# Lo que hace: Define los comandos y parámetros que el script acepta desde la terminal de consola (portal a raspar, límite de páginas, visibilidad del navegador).
# Para qué sirve: Permite al usuario controlar el comportamiento del scraper de forma flexible sin necesidad de modificar el código fuente interno.
# Metodología: Diseño de Interfaz de Línea de Comandos (CLI) y Parametrización de Entradas.
if __name__ == "__main__":
    configurar_logs()
    parser = argparse.ArgumentParser(description="Pipeline Modular de Web Scraping Inmobiliario - INEI")
    parser.add_argument("--portal", type=str, default="babilonia", choices=["babilonia", "urbania", "todos"],
                        help="Portal a raspar: 'babilonia', 'urbania' o 'todos'")
    parser.add_argument("--paginas", type=int, default=999,
                        help="Límite máximo de páginas (por defecto 999 para extraer el 100% automático)")
    parser.add_argument("--visible", action="store_true",
                        help="Abre el navegador visible para supervisión")
    args = parser.parse_args()

    # [COMENTARIO] INICIO Y BUCLE DE PORTALES
    # Lo que hace: Solicita el tipo de cambio oficial al BCRP y luego ejecuta la función procesar_portal() para cada portal solicitado por el usuario.
    # Para qué sirve: Desencadena todo el flujo de trabajo orquestado, asegurando que las variables económicas macroeconómicas estén actualizadas antes de iniciar el scraping.
    # Metodología: Integración de Datos Externos (API externa) y Ejecución Secuencial.
    tc_hoy = obtener_tc_bcrp()
    portales_objetivo = list(PERFILES_PORTALES.keys()) if args.portal == "todos" else [args.portal]

    for p in portales_objetivo:
        procesar_portal(nombre_portal=p, max_paginas=args.paginas, headless=not args.visible, tc_bcrp=tc_hoy)