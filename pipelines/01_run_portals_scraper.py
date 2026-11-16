import argparse
import logging
from datetime import datetime
from config.settings import PERFILES_PORTALES
from src.scraping.stealth_fetcher import obtener_motor
from src.scraping.parsers import obtener_parser
from src.scraping.storage import obtener_urls_procesadas_bronce, guardar_lote_bronce

def configurar_logs():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def procesar_portal(nombre_portal: str):
    perfil = PERFILES_PORTALES[nombre_portal]
    scrape_id = f"{nombre_portal}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Memoria para no repetir extracciones pasadas
    urls_ya_procesadas = obtener_urls_procesadas_bronce(nombre_portal)
    
    engine = obtener_motor(perfil["motor_red"])
    parser = obtener_parser(nombre_portal)
    
    datos_brutos_buffer = []
    
    print(f"\n=======================================================")
    print(f"  INICIANDO SCRAPING CAPA BRONCE: {nombre_portal.upper()}  ")
    print("=======================================================")
    print("Presiona [Ctrl + C] en cualquier momento para detener y guardar.\n")

    try:
        # FASE 1: Recolectar URLs de forma dinámica con Parada Inteligente
        enlaces_a_procesar = []
        for tipo_inm, urls_lista in perfil["urls_semilla"]:
            logging.info(f"Buscando catálogos de {tipo_inm}...")
            
            for url_semilla in urls_lista:
                # Le pasamos la memoria (urls_ya_procesadas) al parser
                nuevos_urls = parser.recolectar_enlaces(engine, url_semilla, perfil, urls_ya_procesadas)
                if not nuevos_urls:
                    break
                    
                for u in nuevos_urls:
                    if u not in urls_ya_procesadas:
                        enlaces_a_procesar.append({"url": u, "tipo_inmueble": tipo_inm})
                        urls_ya_procesadas.add(u)

        logging.info(f"Nuevos enlaces únicos listos para extraer: {len(enlaces_a_procesar)}")

        # FASE 2: Extracción Cruda
        for idx, item in enumerate(enlaces_a_procesar, 1):
            url = item["url"]
            try:
                datos_crudos = parser.extraer_anuncio(engine, url)
                
                datos_crudos["url"] = url
                datos_crudos["tipo_inmueble"] = item["tipo_inmueble"]
                datos_crudos["portal"] = nombre_portal
                datos_crudos["scrape_id"] = scrape_id
                datos_crudos["timestamp"] = datetime.now().isoformat(timespec="seconds")
                
                datos_brutos_buffer.append(datos_crudos)
                logging.info(f"  [{idx}/{len(enlaces_a_procesar)}] {item['tipo_inmueble']} extraído: {url}")
                
            except Exception as e:
                logging.error(f"Error procesando {url}: {e}")

    except KeyboardInterrupt:
        print("\n[!!!] INTERRUPCIÓN MANUAL DETECTADA (Ctrl+C). Deteniendo scraper de forma segura...")
    finally:
        # FASE 3: Guardado garantizado (Graceful Exit)
        engine.cerrar()
        if datos_brutos_buffer:
            print(f"\n[*] Guardando {len(datos_brutos_buffer)} registros en la Capa Bronce de {nombre_portal}...")
            guardar_lote_bronce(datos_brutos_buffer, nombre_portal)
        else:
            print(f"\n[-] Proceso finalizado. No hubo nuevos datos para guardar en {nombre_portal}.")

if __name__ == "__main__":
    configurar_logs()
    parser = argparse.ArgumentParser()
    parser.add_argument("--portal", default="babilonia")
    args = parser.parse_args()
    
    portales = list(PERFILES_PORTALES.keys()) if args.portal == "todos" else [args.portal]
    for p in portales:
        procesar_portal(p)