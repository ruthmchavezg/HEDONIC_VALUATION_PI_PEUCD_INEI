import pandas as pd
import logging
from config.settings import RAW_DIR

def obtener_urls_procesadas_bronce(portal: str) -> set:
    # Nuevo formato de nombre: bronce_alquileres_babilonia.csv
    archivo_bronce = RAW_DIR / "portals" / f"bronce_alquileres_{portal}.csv"
    if archivo_bronce.exists():
        try:
            df = pd.read_csv(archivo_bronce, usecols=["url"], low_memory=False)
            urls = set(df["url"].dropna().astype(str).unique())
            logging.info(f"[*] Memoria Bronce ({portal}): {len(urls)} enlaces ya procesados.")
            return urls
        except Exception as e:
            logging.warning(f"[!] Error leyendo historial bronce de {portal}: {e}")
    return set()

def guardar_lote_bronce(nuevos_registros: list, portal: str):
    if not nuevos_registros:
        return

    # Nuevo formato de nombre: alquileres_babilonia.csv
    archivo_bronce = RAW_DIR / "portals" / f"bronce_alquileres_{portal}.csv"
    df_lote = pd.DataFrame(nuevos_registros)

    # Orden estricto de columnas solicitado
    orden_columnas = [
        "timestamp", "scrape_id", "portal", "url", "id_interno",
        "tipo_inmueble", "titulo", "direccion", "precios_crudos",
        "info", "comodidades", "detalles_extra", "descripcion", "latitud", "longitud"
    ]

    if archivo_bronce.exists():
        df_hist = pd.read_csv(archivo_bronce, low_memory=False)
        df_final = pd.concat([df_hist, df_lote], ignore_index=True)
    else:
        df_final = df_lote

    # Deduplicación absoluta por URL (última extracción manda)
    df_final.drop_duplicates(subset=["url"], keep="last", inplace=True)
    
    # Filtrar y aplicar el orden estricto (ignora llaves extrañas si existieran)
    columnas_finales = [col for col in orden_columnas if col in df_final.columns]
    df_final = df_final[columnas_finales]

    df_final.to_csv(archivo_bronce, index=False, encoding="utf-8-sig")
    logging.info(f"[✓] Guardado en Bronce exitoso. Total en {portal}: {len(df_final)} registros.")