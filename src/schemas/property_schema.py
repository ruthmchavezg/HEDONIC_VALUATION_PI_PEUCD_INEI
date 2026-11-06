from pydantic import BaseModel, ConfigDict
from typing import Optional

class OfertaInmobiliariaINEI(BaseModel):
    model_config = ConfigDict(extra="allow")

    id_anuncio: str
    scrape_id: str
    fecha_hora_scrapeo: str
    portal: str
    modalidad: str = "alquiler"
    tipo_inmueble: str
    url: str
    titulo: Optional[str] = "No especificado"
    precio_soles: Optional[float] = None
    precio_dolares: Optional[float] = None
    mantenimiento_soles: Optional[float] = None
    tipo_cambio_referencial_bcrp: Optional[float] = None
    distrito: Optional[str] = None
    ubicacion: Optional[str] = "No especificado"
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    area_total_m2: Optional[float] = None
    area_construida_m2: Optional[float] = None
    dormitorios_num: Optional[int] = None
    banos_num: Optional[int] = None
    estacionamientos_num: Optional[int] = None
    antiguedad_anos: Optional[int] = None
    es_proyecto_multiunidad: bool = False
    estado_proyecto: Optional[str] = "No especificado"
    datos_principales_generales: Optional[str] = "No especificado"
    caracteristicas: Optional[str] = "No especificado"
    otras_caracteristicas: Optional[str] = "No especificado"
    comodidades: Optional[str] = "No especificado"
    descripcion: Optional[str] = "No especificado"
    texto_completo_anuncio: Optional[str] = None