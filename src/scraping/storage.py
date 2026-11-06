import json
import logging
import pandas as pd
from config.settings import RAW_DIR, INTERIM_DIR

def cargar_o_guardar_enlaces_cache(portal: str, nuevos_enlaces: list = None) -> list:
    archivo = RAW_DIR / "portals" / f"cache_urls_{portal}.json"
    if nuevos_enlaces is not None:
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(nuevos_enlaces, f, ensure_ascii=False, indent=2)
        return nuevos_enlaces
    if archivo.exists():
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def limpiar_cache_enlaces(portal: str):
    archivo = RAW_DIR / "portals" / f"cache_urls_{portal}.json"
    if archivo.exists():
        archivo.unlink()

def obtener_estado_historico_interim() -> tuple[set, set]:
    master_csv = INTERIM_DIR / "base_maestra_inmobiliaria_inei.csv"
    master_parquet = INTERIM_DIR / "base_maestra_inmobiliaria_inei.parquet"
    
    ids_existentes = set()
    urls_existentes = set()

    try:
        if master_parquet.exists():
            df = pd.read_parquet(master_parquet, columns=["id_anuncio", "url"])
            ids_existentes = set(df["id_anuncio"].dropna().astype(str).unique())
            urls_existentes = set(df["url"].dropna().astype(str).unique())
        elif master_csv.exists():
            df = pd.read_csv(master_csv, usecols=["id_anuncio", "url"])
            ids_existentes = set(df["id_anuncio"].dropna().astype(str).unique())
            urls_existentes = set(df["url"].dropna().astype(str).unique())
    except Exception as e:
        logging.warning(f"[!] Aviso al leer histórico en Interim: {e}")

    logging.info(f"[+] Estado Histórico Silver cargado: {len(ids_existentes)} inmuebles únicos ya registrados.")
    return ids_existentes, urls_existentes

def _concatenar_seguro(df_existente: pd.DataFrame, df_nuevo: pd.DataFrame) -> pd.DataFrame:
    if df_existente.empty:
        return df_nuevo.copy()
    if df_nuevo.empty:
        return df_existente.copy()
    registros_combinados = df_existente.to_dict(orient="records") + df_nuevo.to_dict(orient="records")
    return pd.DataFrame(registros_combinados)

def guardar_lote_incremental_silver(nuevos_registros: list, portal: str, scrape_id: str):
    if not nuevos_registros:
        return

    raw_json = RAW_DIR / "portals" / f"snapshot_{portal}_{scrape_id}.json"
    datos_previos_json = []
    if raw_json.exists():
        try:
            with open(raw_json, "r", encoding="utf-8") as f:
                datos_previos_json = json.load(f)
        except Exception:
            datos_previos_json = []
    datos_previos_json.extend(nuevos_registros)
    with open(raw_json, "w", encoding="utf-8") as f:
        json.dump(datos_previos_json, f, ensure_ascii=False, indent=2)

    df_lote = pd.DataFrame(nuevos_registros)

    csv_portal = INTERIM_DIR / "portals_clean" / f"base_{portal}.csv"
    if csv_portal.exists():
        df_p = pd.read_csv(csv_portal)
        df_p = _concatenar_seguro(df_p, df_lote)
        df_p.drop_duplicates(subset=["id_anuncio"], keep="last", inplace=True)
    else:
        df_p = df_lote
    df_p.to_csv(csv_portal, index=False, encoding="utf-8-sig")

    master_csv = INTERIM_DIR / "base_maestra_inmobiliaria_inei.csv"
    master_parquet = INTERIM_DIR / "base_maestra_inmobiliaria_inei.parquet"

    if master_csv.exists():
        df_m = pd.read_csv(master_csv)
        df_total = _concatenar_seguro(df_m, df_lote)
        df_total.drop_duplicates(subset=["id_anuncio"], keep="last", inplace=True)
    else:
        df_total = df_lote

    df_total.to_csv(master_csv, index=False, encoding="utf-8-sig")
    try:
        df_total.to_parquet(master_parquet, index=False)
    except Exception:
        pass

    logging.info(f"  [✓] Guardado incremental Silver ({portal}): +{len(df_lote)} anuncios | Total Base Maestra: {len(df_total)}")

def registrar_historial_scrapeo(
    scrape_id: str,
    portal: str,
    fecha_hora_inicio: str,
    fecha_hora_fin: str,
    total_catalogo: int,
    nuevos_extraidos: int,
    estado: str
):
    archivo_historial = INTERIM_DIR / "historial_scrapeo.csv"
    nuevo_registro = pd.DataFrame([{
        "scrape_id": scrape_id,
        "portal": portal,
        "fecha_hora_inicio": fecha_hora_inicio,
        "fecha_hora_fin": fecha_hora_fin,
        "enlaces_en_catalogo": total_catalogo,
        "nuevos_anuncios_guardados": nuevos_extraidos,
        "estado_ejecucion": estado
    }])
    if archivo_historial.exists():
        df_hist = pd.read_csv(archivo_historial)
        df_hist = _concatenar_seguro(df_hist, nuevo_registro)
    else:
        df_hist = nuevo_registro
    df_hist.to_csv(archivo_historial, index=False, encoding="utf-8-sig")