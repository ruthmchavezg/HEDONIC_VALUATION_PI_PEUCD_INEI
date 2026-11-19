import pandas as pd
import logging
from config.settings import RAW_DIR

def obtener_urls_procesadas_tiktok() -> set:
    archivo_bronce = RAW_DIR / "social" / "bronce_alquileres_tiktok.csv"
    if archivo_bronce.exists():
        try:
            df = pd.read_csv(archivo_bronce, usecols=["url"], low_memory=False)
            urls = set(df["url"].dropna().astype(str).unique())
            logging.info(f"[*] Memoria TikTok: {len(urls)} videos ya procesados.")
            return urls
        except Exception as e:
            logging.warning(f"[!] Error leyendo historial de TikTok: {e}")
    return set()

def guardar_lote_tiktok(nuevos_registros: list):
    if not nuevos_registros:
        return

    archivo_bronce = RAW_DIR / "social" / "bronce_alquileres_tiktok.csv"
    archivo_bronce.parent.mkdir(parents=True, exist_ok=True)
    
    df_lote = pd.DataFrame(nuevos_registros)

    # Lista actualizada sin el primer_comentario
    orden_columnas = [
        "timestamp", "scrape_id", "portal", "url", "id_contenido", 
        "tipo_inmueble", "distrito", "autor", "fecha_publicacion", 
        "descripcion", "reproducciones", "likes", "compartidos"
    ]

    if archivo_bronce.exists():
        df_hist = pd.read_csv(archivo_bronce, low_memory=False)
        df_final = pd.concat([df_hist, df_lote], ignore_index=True)
    else:
        df_final = df_lote

    df_final.drop_duplicates(subset=["url"], keep="last", inplace=True)
    
    for col in orden_columnas:
        if col not in df_final.columns:
            df_final[col] = ""
            
    df_final = df_final[orden_columnas]
    df_final.to_csv(archivo_bronce, index=False, encoding="utf-8-sig")
    logging.info(f"[✓] Guardado en Bronce exitoso. Total en TikTok: {len(df_final)} videos.")