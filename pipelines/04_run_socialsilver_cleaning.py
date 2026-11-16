import time
import logging
import pandas as pd
from datetime import datetime
from config.settings import RAW_DIR, INTERIM_DIR, DISTRITOS_LIMA
from src.cleaning.social_llm_extractor import SocialBatchLLMExtractor, reparar_mojibake, homologar_tipo_general
import unicodedata

# 58 columnas exactas
COLUMNAS_SILVER_58 = [
    "timestamp", "scrape_id", "portal", "url", "id_contenido", "fecha_publicación",
    "modalidad", "direccion", "distrito", "latitud", "longitud",
    "precio_usd", "precio_pen", "mantenimiento_usd", "mantenimiento_pen",
    "servicios_basicos_usd", "servicios_basicos_pen", "tipo_alquiler",
    "tipo_inmueble", "tipo_inmueble_homologado",
    "area_total_m2", "area_construida_m2", "area_techada_m2",
    "dormitorios_num", "banos_num", "estacionamientos_num",
    "anio_construccion", "pisos_edificio", "piso_inmueble",
    "amoblado", "linea_blanca", "agua_caliente", "walk_in_closet", "ascensor",
    "piscina", "gimnasio", "lavanderia", "cuarto_servicio", "seguridad",
    "alarma", "pet_friendly", "vista_mar", "vista_ciudad", "vista_calle",
    "vista_golf", "coworking", "zona_parrilla", "jardin", "terraza",
    "internet", "aire_acondicionado", "cerca_transporte", "cerca_comercio",
    "cerca_colegio", "cerca_parque", "cerca_universidad", "de_estreno", "remodelado"
]

COLUMNAS_ENTRADA_BRONCE = ["timestamp", "scrape_id", "portal", "url", "id_contenido", "tipo_inmueble", "distrito", "fecha_publicacion", "descripcion"]
COLUMNAS_DESCARTADOS = ["timestamp_descarte", "motivo_descarte", "timestamp", "scrape_id", "portal", "url", "id_contenido", "fecha_publicacion", "distrito_bronce", "tipo_inmueble_bronce", "descripcion"]

RUTA_SILVER = INTERIM_DIR / "social_clean" / "alquileres_social_silver.csv"
RUTA_DESCARTADOS = INTERIM_DIR / "social_clean" / "alquileres_social_descartados.csv"
BATCH_SIZE = 20

def configurar_logs():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def normalizar_str(texto: str) -> str:
    if not texto: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto).lower()) if unicodedata.category(c) != 'Mn').strip()

def validar_distrito_oficial(distrito_detectado):
    mapa_lima = {normalizar_str(d): d for d in DISTRITOS_LIMA}
    if not distrito_detectado: return None
    norm = normalizar_str(distrito_detectado)
    if norm in mapa_lima: return mapa_lima[norm]
    for k, v in mapa_lima.items():
        if k in norm: return v
    return None

def cargar_urls_procesadas() -> set:
    urls = set()
    for ruta in [RUTA_SILVER, RUTA_DESCARTADOS]:
        if ruta.exists():
            try:
                df = pd.read_csv(ruta, usecols=["url"], low_memory=False)
                urls.update(df["url"].dropna().astype(str).unique())
            except Exception: pass
    return urls

def guardar_csv_incremental(buffer: list, ruta_archivo, orden_columnas: list):
    if not buffer: return
    ruta_archivo.parent.mkdir(parents=True, exist_ok=True)
    
    df_lote = pd.DataFrame(buffer)
    # Solución al FutureWarning: Elimina columnas 100% nulas antes de concatenar
    df_lote = df_lote.dropna(axis=1, how='all')
    
    if ruta_archivo.exists():
        df_hist = pd.read_csv(ruta_archivo, low_memory=False)
        df_final = pd.concat([df_hist, df_lote], ignore_index=True)
    else:
        df_final = df_lote
        
    df_final.drop_duplicates(subset=["url"], keep="last", inplace=True)
    for col in orden_columnas:
        if col not in df_final.columns: df_final[col] = ""
    df_final = df_final[orden_columnas]
    df_final.to_csv(ruta_archivo, index=False, encoding="utf-8-sig")

def crear_registro_descarte(row, motivo: str) -> dict:
    return {
        "timestamp_descarte": datetime.now().isoformat(timespec="seconds"),
        "motivo_descarte": motivo,
        "timestamp": row.get("timestamp", ""),
        "scrape_id": row.get("scrape_id", ""),
        "portal": row.get("portal", ""),
        "url": str(row.get("url", "")),
        "id_contenido": row.get("id_contenido", ""),
        "fecha_publicacion": row.get("fecha_publicacion", ""),
        "distrito_bronce": row.get("distrito", ""),
        "tipo_inmueble_bronce": row.get("tipo_inmueble", ""),
        "descripcion": reparar_mojibake(str(row.get("descripcion", "")))
    }

def ejecutar_limpieza_social():
    archivos_raw = [RAW_DIR / "social" / "alquileres_facebook.csv", RAW_DIR / "social" / "alquileres_tiktok.csv"]
    dfs = [pd.read_csv(archivo, usecols=lambda c: c in COLUMNAS_ENTRADA_BRONCE, low_memory=False) for archivo in archivos_raw if archivo.exists()]

    if not dfs:
        logging.warning("No se encontraron archivos en data/raw/social/")
        return

    df_bronce = pd.concat(dfs, ignore_index=True)
    
    # 1. Cargar las URLs listas como un SET (Búsqueda ultrarrápida O(1))
    urls_listas = cargar_urls_procesadas() 
    
    # 2. FILTRADO EXPRÉS: Solo nos quedamos con lo que NO está en el set de procesados antes de limpiar duplicados globales
    df_pendientes = df_bronce[~df_bronce["url"].astype(str).isin(urls_listas)].copy()
    
    # 3. Limpieza de memoria (quitamos duplicados solo a lo que realmente vamos a procesar)
    df_pendientes.drop_duplicates(subset=["url"], keep="last", inplace=True)
    df_pendientes.reset_index(drop=True, inplace=True)

    logging.info(f"Pendientes por procesar: {len(df_pendientes)}")
    if df_pendientes.empty:
        logging.info("Nada nuevo por procesar.")
        return

    extractor = SocialBatchLLMExtractor()
    buffer_silver, buffer_descartados = [], []

    try:
        for inicio in range(0, len(df_pendientes), BATCH_SIZE):
            chunk = df_pendientes.iloc[inicio:inicio + BATCH_SIZE]
            lote_para_ia, filas_chunk = [], {}

            for idx_local, row in chunk.iterrows():
                desc_limpia = reparar_mojibake(str(row.get("descripcion", "")))
                if len(desc_limpia) < 15:
                    buffer_descartados.append(crear_registro_descarte(row, "1. Descripción vacía o muy corta"))
                else:
                    anio_pub = int(str(row.get("fecha_publicacion", ""))[:4]) if str(row.get("fecha_publicacion", ""))[:4].isdigit() else datetime.now().year
                    lote_para_ia.append({"idx": idx_local, "anio_pub": anio_pub, "texto": desc_limpia})
                    filas_chunk[idx_local] = row

            if not lote_para_ia: continue

            logging.info(f"Enviando lote a Gemini (Anuncios {inicio + 1} a {min(inicio + BATCH_SIZE, len(df_pendientes))})...")
            resultados_ia = extractor.procesar_lote(lote_para_ia)

            for idx_local, row in filas_chunk.items():
                res = resultados_ia.get(idx_local)
                if not res: continue

                if res.modalidad not in ["alquiler", "alquiler/venta"]:
                    buffer_descartados.append(crear_registro_descarte(row, "2. Exclusivamente venta o no alquiler"))
                    continue

                if not res.precio_pen and not res.precio_usd:
                    buffer_descartados.append(crear_registro_descarte(row, "3. Sin precio en soles ni en dólares"))
                    continue

                if not res.direccion and not res.distrito:
                    buffer_descartados.append(crear_registro_descarte(row, "4. Sin dirección ni distrito en descripción"))
                    continue

                # Validación de distrito y geolocalización extraída directamente de Gemini
                distrito_oficial = validar_distrito_oficial(res.distrito)
                if not distrito_oficial:
                    buffer_descartados.append(crear_registro_descarte(row, f"5. Fuera de Lima ({res.distrito})"))
                    continue

                tipo_general = homologar_tipo_general(res.tipo_inmueble_homologado)

                buffer_silver.append({
                    "timestamp": row.get("timestamp", ""),
                    "scrape_id": row.get("scrape_id", ""),
                    "portal": row.get("portal", ""),
                    "url": str(row.get("url", "")),
                    "id_contenido": row.get("id_contenido", ""),
                    "fecha_publicación": row.get("fecha_publicacion", ""),
                    "modalidad": res.modalidad,
                    "direccion": res.direccion or "",
                    "distrito": distrito_oficial,
                    "latitud": res.latitud if res.latitud else "",
                    "longitud": res.longitud if res.longitud else "",
                    "precio_usd": res.precio_usd, "precio_pen": res.precio_pen,
                    "mantenimiento_usd": res.mantenimiento_usd, "mantenimiento_pen": res.mantenimiento_pen,
                    "servicios_basicos_usd": res.servicios_basicos_usd, "servicios_basicos_pen": res.servicios_basicos_pen,
                    "tipo_alquiler": res.tipo_alquiler,
                    "tipo_inmueble": tipo_general, "tipo_inmueble_homologado": res.tipo_inmueble_homologado,
                    "area_total_m2": res.area_total_m2, "area_construida_m2": res.area_construida_m2, "area_techada_m2": res.area_techada_m2,
                    "dormitorios_num": res.dormitorios_num, "banos_num": res.banos_num, "estacionamientos_num": res.estacionamientos_num,
                    "anio_construccion": res.anio_construccion, "pisos_edificio": res.pisos_edificio, "piso_inmueble": res.piso_inmueble,
                    "amoblado": res.amoblado, "linea_blanca": res.linea_blanca, "agua_caliente": res.agua_caliente,
                    "walk_in_closet": res.walk_in_closet, "ascensor": res.ascensor, "piscina": res.piscina,
                    "gimnasio": res.gimnasio, "lavanderia": res.lavanderia, "cuarto_servicio": res.cuarto_servicio,
                    "seguridad": res.seguridad, "alarma": res.alarma, "pet_friendly": res.pet_friendly,
                    "vista_mar": res.vista_mar, "vista_ciudad": res.vista_ciudad, "vista_calle": res.vista_calle,
                    "vista_golf": res.vista_golf, "coworking": res.coworking, "zona_parrilla": res.zona_parrilla,
                    "jardin": res.jardin, "terraza": res.terraza, "internet": res.internet,
                    "aire_acondicionado": res.aire_acondicionado, "cerca_transporte": res.cerca_transporte,
                    "cerca_comercio": res.cerca_comercio, "cerca_colegio": res.cerca_colegio,
                    "cerca_parque": res.cerca_parque, "cerca_universidad": res.cerca_universidad,
                    "de_estreno": res.de_estreno, "remodelado": res.remodelado
                })

            guardar_csv_incremental(buffer_silver, RUTA_SILVER, COLUMNAS_SILVER_58)
            guardar_csv_incremental(buffer_descartados, RUTA_DESCARTADOS, COLUMNAS_DESCARTADOS)
            buffer_silver.clear()
            buffer_descartados.clear()
            time.sleep(4.2)

    except KeyboardInterrupt:
        print("\n[!!!] Interrupción. Guardando último lote...")
    finally:
        guardar_csv_incremental(buffer_silver, RUTA_SILVER, COLUMNAS_SILVER_58)
        guardar_csv_incremental(buffer_descartados, RUTA_DESCARTADOS, COLUMNAS_DESCARTADOS)

if __name__ == "__main__":
    configurar_logs()
    ejecutar_limpieza_social()