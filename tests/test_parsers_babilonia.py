import json
import sys
from pathlib import Path

# Asegurar que reconozca la carpeta src
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.scraping.stealth_fetcher import obtener_motor
from src.scraping.parsers import obtener_parser

def test_extraccion_bronce_individual():
    # Las dos URLs exactas que analizamos
    url_casa = "https://babilonia.pe/inmueble/casa-en-alquiler-en-chorrillos-de-3-dormitorios-2-banios-180m2-area-1500-usd-de-mass-real-estate-177044"
    url_depa = "https://babilonia.pe/inmueble/departamento-en-alquiler-en-san-isidro-de-2-dormitorios-3-banios-160m2-area-3900-usd-de-peru-luxury-properties-168138"
    
    print("[*] Iniciando motor de red (Playwright)...")
    engine = obtener_motor("playwright")
    parser = obtener_parser("babilonia")
    
    try:
        print("\n==================================================")
        print("  EXTRAYENDO CASA (CAPA BRONCE)")
        print("==================================================")
        datos_casa = parser.extraer_anuncio(engine, url_casa)
        datos_casa["tipo_inmueble"] = "casa"
        
        # Mostramos los datos en consola de forma bonita, ignorando el HTML gigante para no saturar la pantalla
        datos_mostrar_casa = {k: v for k, v in datos_casa.items() if k != "html_texto_completo"}
        print(json.dumps(datos_mostrar_casa, indent=4, ensure_ascii=False))
        
        print("\n==================================================")
        print("  EXTRAYENDO DEPARTAMENTO (CAPA BRONCE)")
        print("==================================================")
        datos_depa = parser.extraer_anuncio(engine, url_depa)
        datos_depa["tipo_inmueble"] = "departamento"
        
        datos_mostrar_depa = {k: v for k, v in datos_depa.items() if k != "html_texto_completo"}
        print(json.dumps(datos_mostrar_depa, indent=4, ensure_ascii=False))
        
    except Exception as e:
        print(f"[!] Error durante la prueba: {e}")
    finally:
        engine.cerrar()
        print("\n[✓] Motor cerrado. Prueba finalizada.")

if __name__ == "__main__":
    test_extraccion_bronce_individual()