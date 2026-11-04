import urllib.request
import json
import logging
import ssl

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

from config.settings import BCRP_API_URL, TIPO_CAMBIO_FALLBACK

def obtener_tc_bcrp() -> float:
    """Consulta la serie PD04640PD del BCRP para estandarizar precios a Soles (PEN)."""
    
    try:
        req = urllib.request.Request(
            BCRP_API_URL,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
            periodos = data.get("periods", [])
            
            if periodos:
                ultimo = periodos[-1].get("values", [None])[0]
                if ultimo and ultimo != "n.d.":
                    tc = round(float(ultimo), 4)
                    logging.info(f"[+] Tipo de Cambio BCRP obtenido: S/ {tc}")
                    return tc
                    
    except Exception as e:
        logging.warning(f"[*] Aviso BCRP ({e}). Usando tipo de cambio fallback: S/ {TIPO_CAMBIO_FALLBACK}")
    return TIPO_CAMBIO_FALLBACK