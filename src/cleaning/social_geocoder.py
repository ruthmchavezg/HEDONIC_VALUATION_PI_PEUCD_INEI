import json
import time
import unicodedata
import logging
from typing import Tuple, Optional
from geopy.geocoders import GoogleV3, Nominatim
from config.settings import INTERIM_DIR, DISTRITOS_LIMA, GOOGLE_MAPS_API_KEY

CACHE_FILE = INTERIM_DIR / "checkpoints" / "geocache_lima.json"

def normalizar_texto(texto: str) -> str:
    if not texto: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto).lower()) if unicodedata.category(c) != 'Mn').strip()

class SocialGoogleGeocoder:
    def __init__(self):
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self._cargar_cache()
        self.mapa_distritos = {normalizar_texto(d): d for d in DISTRITOS_LIMA}
        
        if GOOGLE_MAPS_API_KEY:
            self.geolocator = GoogleV3(api_key=GOOGLE_MAPS_API_KEY, timeout=10)
            self.usa_google = True
            self.delay = 0.05
        else:
            logging.warning("[!] GOOGLE_MAPS_API_KEY vacía. Usando Nominatim (OpenStreetMap) como respaldo.")
            self.geolocator = Nominatim(user_agent="hedonic_peucd_inei_geo", timeout=10)
            self.usa_google = False
            self.delay = 1.1

    def _cargar_cache(self) -> dict:
        if CACHE_FILE.exists():
            try:
                return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _guardar_cache(self):
        CACHE_FILE.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def homologar_distrito_lima(self, texto: Optional[str]) -> Optional[str]:
        if not texto:
            return None
        norm = normalizar_texto(texto)
        if norm in self.mapa_distritos:
            return self.mapa_distritos[norm]
        # Búsqueda de coincidencia dentro de la dirección devuelta por Google Maps
        for key_norm, nombre_oficial in self.mapa_distritos.items():
            if f" {key_norm}" in f" {norm}" or f"{key_norm}," in norm:
                return nombre_oficial
        return None

    def _extraer_distrito_de_google_raw(self, raw_data: dict, formatted_address: str) -> Optional[str]:
        """Inspecciona los componentes de Google Maps para identificar el distrito de Lima."""
        components = raw_data.get("address_components", [])
        for comp in components:
            types_list = comp.get("types", [])
            if any(t in types_list for t in ["locality", "sublocality", "administrative_area_level_3"]):
                candidato = self.homologar_distrito_lima(comp.get("long_name", ""))
                if candidato:
                    return candidato
        return self.homologar_distrito_lima(formatted_address)

    def resolver_geografia(self, distrito_ia: Optional[str], direccion_ia: Optional[str]) -> Tuple[Optional[str], str, Optional[float], Optional[float]]:
        """
        Retorna: (distrito_oficial_lima, direccion_consolidada, latitud, longitud)
        """
        distrito_oficial = self.homologar_distrito_lima(distrito_ia)

        # Si el anuncio menciona explícitamente otra provincia fuera de Lima, descartamos sin gastar Google Maps
        if distrito_ia and not distrito_oficial:
            provincias_externas = [
                "trujillo", "ica", "arequipa", "piura", "cusco", "chiclayo", "huancayo", 
                "chimbote", "tacna", "pucallpa", "iquitos", "cajamarca", "ayacucho", "asia", "canete", "chincha"
            ]
            if any(p in normalizar_texto(distrito_ia) for p in provincias_externas):
                return None, "", None, None

        # Si no hay dirección específica, pero sí distrito oficial, buscamos el CENTROIDE del distrito
        if direccion_ia and distrito_oficial:
            query = f"{direccion_ia}, {distrito_oficial}, Lima, Peru"
            direccion_final = direccion_ia
        elif direccion_ia and not distrito_oficial:
            query = f"{direccion_ia}, Lima, Peru"
            direccion_final = direccion_ia
        elif distrito_oficial and not direccion_ia:
            query = f"Distrito de {distrito_oficial}, Lima, Peru"
            direccion_final = f"Centroide de {distrito_oficial}"
        else:
            return None, "", None, None

        query_key = normalizar_texto(query)

        # 1. Consultar Caché Local
        if query_key in self.cache:
            c = self.cache[query_key]
            dist_resuelto = distrito_oficial or self.homologar_distrito_lima(c.get("distrito_mapa"))
            return dist_resuelto, direccion_final, c.get("lat"), c.get("lon")

        # 2. Consultar Google Maps API
        try:
            time.sleep(self.delay)
            if self.usa_google:
                location = self.geolocator.geocode(query, region="pe", language="es")
            else:
                location = self.geolocator.geocode(query, addressdetails=True, country_codes="pe")

            if location:
                lat, lon = round(location.latitude, 6), round(location.longitude, 6)
                if self.usa_google:
                    distrito_mapa = self._extraer_distrito_de_google_raw(location.raw, location.address)
                else:
                    distrito_mapa = self.homologar_distrito_lima(str(location.address))

                self.cache[query_key] = {"lat": lat, "lon": lon, "distrito_mapa": distrito_mapa}
                self._guardar_cache()

                distrito_consolidado = distrito_oficial or distrito_mapa
                return distrito_consolidado, direccion_final, lat, lon

        except Exception as e:
            logging.warning(f"Error en geocodificación para '{query}': {e}")

        # Fallback: Si la calle referencial falló pero teníamos el distrito, obtenemos el centroide del distrito
        if distrito_oficial and direccion_ia:
            return self.resolver_geografia(distrito_oficial, None)

        self.cache[query_key] = {"lat": None, "lon": None, "distrito_mapa": None}
        self._guardar_cache()
        return distrito_oficial, direccion_final, None, None