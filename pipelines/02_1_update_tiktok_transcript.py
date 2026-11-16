import sys
import pandas as pd
from pathlib import Path
from playwright.sync_api import sync_playwright

# 1. Configurar rutas desde la carpeta pipelines/ hacia la raíz del proyecto
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR)) # Permite importar src y config sin errores

from src.social_scraping.tiktok_parser import TiktokParser
from config.settings import RAW_DIR

ARCHIVO_BRONCE = RAW_DIR / "social" / "alquileres_tiktok.csv"
SESSION_DIR = BASE_DIR / "data" / "tiktok_session"

def interceptar_recursos_pesados(route):
    # Modo Turbo: bloquea carga de videos, imágenes y fuentes
    if route.request.resource_type in ["image", "media", "font"]:
        route.abort()
    else:
        route.continue_()

def actualizar_descripciones():
    if not ARCHIVO_BRONCE.exists():
        print("❌ No se encontró el archivo alquileres_tiktok.csv")
        return

    # Cargamos tu base de datos actual
    df = pd.read_csv(ARCHIVO_BRONCE, low_memory=False)
    print(f"📊 Total de registros en la base de datos: {len(df)}")
    
    parser = TiktokParser()
    modificados = 0

    print("\n🚀 INICIANDO ACTUALIZACIÓN RETROACTIVA DE SUBTÍTULOS...")
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            channel="chrome",
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        page = context.new_page()
        page.route("**/*", interceptar_recursos_pesados) # Activamos modo turbo
        
        try:
            for idx, row in df.iterrows():
                url = str(row['url'])
                desc_actual = str(row.get('descripcion', ''))
                

                
                # Salta SOLO los videos que ya extrajeron texto real exitosamente
                if "[TEXTO EN VIDEO]" in desc_actual:
                    continue
                    
                print(f"  -> Actualizando [{idx+1}/{len(df)}]: {url}")
                
                try:
                    # Extrae la nueva descripción combinada
                    datos_nuevos = parser.extraer_video(page, url)
                    nueva_desc = datos_nuevos.get("descripcion", "")
                    
                    if nueva_desc and nueva_desc != desc_actual:
                        # Reemplaza exactamente en la celda correspondiente
                        df.at[idx, 'descripcion'] = nueva_desc
                        modificados += 1
                        
                    # Guardado de seguridad cada 20 videos
                    if modificados % 20 == 0 and modificados > 0:
                        df.to_csv(ARCHIVO_BRONCE, index=False, encoding="utf-8-sig")
                        print("     [💾] Progreso guardado temporalmente...")
                        
                except Exception as e:
                    print(f"     [!] Error visitando el video: {e}")
                    
        except KeyboardInterrupt:
            print("\n[!!!] Interrupción manual detectada.")
        finally:
            # Sobreescribimos el CSV original manteniendo la estructura intacta
            df.to_csv(ARCHIVO_BRONCE, index=False, encoding="utf-8-sig")
            print(f"\n✅ Proceso finalizado. Se actualizaron {modificados} descripciones históricas.")
            
            try:
                context.close()
            except:
                pass

if __name__ == "__main__":
    actualizar_descripciones()