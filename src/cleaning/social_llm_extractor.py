import json
import logging
from typing import List, Dict
from google import genai
from google.genai import types
from config.settings import GEMINI_API_KEY, DISTRITOS_LIMA
from src.schemas.social_schema import LoteExtraccionSocial, ItemInmuebleExtraido

def reparar_mojibake(texto: str) -> str:
    if not isinstance(texto, str) or not texto:
        return ""
    try:
        return texto.encode('latin1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto.strip()

def homologar_tipo_general(tipo_homologado: str) -> str:
    if tipo_homologado in ["habitación", "cuarto", "mini departamento"]:
        return "habitación"
    return tipo_homologado

class SocialBatchLLMExtractor:
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        distritos_str = ", ".join(DISTRITOS_LIMA)
        
        self.system_instruction = f"""
        Eres un extractor experto de datos inmobiliarios en Lima, Perú.
        
        REGLAS ESTRICTAS:
        1. DISTRITO: Extrae el distrito EXCLUSIVAMENTE leyendo el texto de la descripción. No adivines. Si el texto no menciona el distrito ni lugares conocidos que pertenezcan a uno, devuelve null. Si pertenece a otra ciudad/provincia, pon ese nombre (el sistema lo descartará luego).
        2. VALORES NULOS (NULL): Si cualquier dato o característica no se menciona en absoluto en el texto, asígnale `null`. Para los binarios: Usa 1 solo si afirma tenerlo. Usa 0 SOLO si explícitamente prohíbe o dice no tenerlo.
        3. ÁREAS Y CONVERSIÓN: Si el área está en "pies cuadrados" (sq ft) o "ft2", conviértela obligatoriamente a metros cuadrados (m2) multiplicando por 0.092903.
        4. GEOCODIFICACIÓN HEDÓNICA (CRÍTICO): Tu objetivo es la máxima precisión espacial para un modelo econométrico. Sigue esta jerarquía estricta para la latitud y longitud:
           - Nivel 1 (Exacto): Si hay dirección con número (ej. Av. Larco 345), usa esas coordenadas exactas.
           - Nivel 2 (Intersección/Urbanización): Si menciona una avenida larga (ej. "Av. Los Alisos", "Javier Prado") SIN número, OBLIGATORIAMENTE busca en el texto una intersección, urbanización (ej. "Urb. Previ"), colegio, o parque cercano. Genera las coordenadas EXACTAS de ese cruce o polígono, NUNCA el centro de la avenida.
           - Nivel 3 (Referencia/Landmark): ej. si dice "a espaldas de MegaPlaza", usa las coordenadas perimetrales de MegaPlaza.
           - Nivel 4 (Centroide): SOLO usa el centro del distrito si el texto no da absolutamente ninguna pista, calle o referencia.
        5. PRECIO TEMPORAL: Si el alquiler es por día, calcula el precio mensual multiplicando por 30.
        """

    def procesar_lote(self, lote_anuncios: List[Dict]) -> Dict[int, ItemInmuebleExtraido]:
        bloques_texto = []
        for item in lote_anuncios:
            texto_limpio = reparar_mojibake(item["texto"])
            bloques_texto.append(
                f"--- ANUNCIO [idx={item['idx']}] (Año Publicación: {item['anio_pub']}) ---\n{texto_limpio}\n"
            )
        
        prompt_lote = "\n".join(bloques_texto)

        try:
            response = self.client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=prompt_lote,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    response_mime_type="application/json",
                    response_schema=LoteExtraccionSocial,
                    temperature=0.0
                ),
            )
            data = json.loads(response.text)
            lote_obj = LoteExtraccionSocial(**data)
            return {res.idx_lote: res for res in lote_obj.resultados}
        except Exception as e:
            logging.error(f"Error en Gemini API: {e}")
            return {}