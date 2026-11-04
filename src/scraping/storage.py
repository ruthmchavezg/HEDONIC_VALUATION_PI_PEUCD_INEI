# [COMENTARIO] IMPORTACIÓN DE LIBRERÍAS Y CONFIGURACIONES
# Lo que hace: Importa módulos estándar (json, logging), la librería pandas para manejo de DataFrames y las rutas absolutas de las carpetas desde el archivo de configuración.
# Para qué sirve: Provee las herramientas necesarias para la manipulación de datos tabulares, el registro de eventos y la ubicación exacta de dónde leer o escribir los archivos generados.
# Metodología: Arquitectura de datos Medallion (Data Lakehouse local) estructurada en capas Bronze, Silver y Gold para mantener el código y el almacenamiento desacoplados[cite: 12].
import json
import logging
import pandas as pd
from config.settings import RAW_DIR, INTERIM_DIR, PROCESSED_DIR

# [COMENTARIO] FUNCIÓN: cargar_o_guardar_enlaces_cache
# Lo que hace: Verifica si se enviaron enlaces nuevos para guardarlos en un archivo JSON en la carpeta RAW_DIR; si no, lee el archivo JSON existente y devuelve los enlaces almacenados.
# Para qué sirve: Guarda el progreso de las URLs recolectadas para que, en caso de interrupción, el sistema no tenga que volver a navegar por todas las páginas web de listado desde el inicio.
# Metodología: Almacenamiento en caché (Caching) y persistencia del estado inicial en la capa Bronze[cite: 12].
def cargar_o_guardar_enlaces_cache(portal: str, fecha: str, nuevos_enlaces: list = None) -> list:
    archivo = RAW_DIR / f"enlaces_{portal}_{fecha}.json"
    if nuevos_enlaces is not None:
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(nuevos_enlaces, f, ensure_ascii=False, indent=2)
        return nuevos_enlaces
    if archivo.exists():
        with open(archivo, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# [COMENTARIO] FUNCIÓN: cargar_checkpoint_previo
# Lo que hace: Busca un archivo CSV de respaldo en INTERIM_DIR, lo convierte a diccionario y extrae una lista única de URLs que ya fueron procesadas en la ejecución de ese día.
# Para qué sirve: Permite que el scraper sepa exactamente qué anuncios ya descargó exitosamente hoy, saltándolos para reanudar el trabajo justo donde se quedó sin duplicar esfuerzo.
# Metodología: Tolerancia a fallos (Fault Tolerance) y reanudación incremental mediante Idempotencia en la capa Silver[cite: 11, 12].
def cargar_checkpoint_previo(portal: str, fecha: str) -> tuple[list, set]:
    archivo_backup = INTERIM_DIR / f"backup_emergencia_{portal}_{fecha}.csv"
    if archivo_backup.exists():
        df = pd.read_csv(archivo_backup)
        registros = df.to_dict(orient="records")
        urls_listas = set(df["url"].dropna().unique())
        logging.info(f"[+] Checkpoint detectado ({portal}): {len(urls_listas)} URLs ya procesadas hoy.")
        return registros, urls_listas
    return [], set()

# [COMENTARIO] FUNCIÓN: guardar_checkpoint_emergencia
# Lo que hace: Transforma la lista temporal de registros extraídos en un DataFrame de pandas y la exporta como un archivo CSV en la carpeta INTERIM_DIR, sobrescribiendo el anterior.
# Para qué sirve: Actúa como un sistema de autoguardado para asegurar que los datos recopilados durante la ejecución no se pierdan si el programa falla repentinamente.
# Metodología: Puntos de control incrementales (Incremental Checkpoints) y almacenamiento estructurado intermedio[cite: 12].
def guardar_checkpoint_emergencia(registros: list, portal: str, fecha: str):
    if not registros:
        return
    archivo_backup = INTERIM_DIR / f"backup_emergencia_{portal}_{fecha}.csv"
    pd.DataFrame(registros).to_csv(archivo_backup, index=False, encoding="utf-8-sig")
    logging.info(f"  [!] Checkpoint guardado: {len(registros)} filas aseguradas en {archivo_backup.name}")

# [COMENTARIO] FUNCIÓN: exportar_dataset_final_gold
# Lo que hace: Ejecuta tres guardados finales: 1) JSON crudo en la capa Bronze, 2) CSV específico del día en la capa Gold, y 3) añade los datos a la base maestra eliminando registros duplicados basados en ID y fecha.
# Para qué sirve: Consolida la información extraída preparándola definitivamente para el análisis. Mantiene el respaldo inmutable para auditoría y asegura que el archivo final no contenga anuncios repetidos que sesguen los modelos estadísticos.
# Metodología: Arquitectura Medallion completa (Bronze inmutable para auditoría, Gold consolidada y limpia para modelos), aplicando Trazabilidad y Deduplicación de registros[cite: 11, 12, 14].
def exportar_dataset_final_gold(registros: list, portal: str, fecha: str):
    if not registros:
        logging.warning(f"[-] No se obtuvieron registros válidos para exportar en {portal}.")
        return

    # 1. Respaldo Bronze en JSON crudo para auditoría del INEI
    raw_json = RAW_DIR / f"snapshot_{portal}_{fecha}.json"
    with open(raw_json, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)

    # 2. Exportación Gold por fecha y consolidación longitudinal
    df_hoy = pd.DataFrame(registros)
    csv_portal = PROCESSED_DIR / f"dataset_hedonico_{portal}_{fecha}.csv"
    df_hoy.to_csv(csv_portal, index=False, encoding="utf-8-sig")

    # 3. Base Maestra Multipropósito del INEI (Une Babilonia + Urbania + Capturas Lunes/Jueves)
    master_parquet = PROCESSED_DIR / "base_maestra_inmobiliaria_inei.parquet"
    master_csv = PROCESSED_DIR / "base_maestra_inmobiliaria_inei.csv"

    if master_parquet.exists():
        df_hist = pd.read_parquet(master_parquet)
        df_total = pd.concat([df_hist, df_hoy], ignore_index=True)
        df_total.drop_duplicates(subset=["id_anuncio", "fecha_captura"], keep="last", inplace=True)
    else:
        df_total = df_hoy

    df_total.to_parquet(master_parquet, index=False)
    df_total.to_csv(master_csv, index=False, encoding="utf-8-sig")
    logging.info(f"[✓] Exportación Gold exitosa: {csv_portal.name} | Total acumulado INEI: {len(df_total)} filas.")