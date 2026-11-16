from typing import Optional, List, Literal
from pydantic import BaseModel, Field

class ItemInmuebleExtraido(BaseModel):
    # El idx es interno del código, ese sí es obligatorio
    idx_lote: int = Field(description="El número de índice [idx] exacto del anuncio recibido en el lote.")
    
    # --- DATOS GENERALES ---
    modalidad: Optional[Literal["alquiler", "alquiler/venta", "venta", "otro"]] = Field(
        default=None, description="'alquiler' si solo se alquila. 'alquiler/venta' si se alquila y se vende. 'venta' si es solo venta."
    )
    direccion: Optional[str] = Field(default=None, description="Dirección exacta o referencial. Null si no menciona.")
    distrito: Optional[str] = Field(default=None, description="Distrito extraído en formato DISTRITOS_LIMA exclusivamente de la descripción. Null si no menciona.")
    latitud: Optional[float] = Field(
        default=None, 
        description="Latitud geográfica de la dirección exacta o de la referencia más cercana mencionada (cruce, parque, avenida, urbanización). Null si no hay datos."
    )
    longitud: Optional[float] = Field(
        default=None, 
        description="Longitud geográfica de la dirección exacta o de la referencia más cercana mencionada. Null si no hay datos."
    )
    
    # --- PRECIOS Y COSTOS ---
    precio_usd: Optional[float] = Field(default=None, description="Precio de alquiler mensual en dólares. Null si no menciona.")
    precio_pen: Optional[float] = Field(default=None, description="Precio de alquiler mensual en soles. Null si no menciona.")
    mantenimiento_usd: Optional[float] = Field(default=None, description="Monto de mantenimiento en dólares. Null si no menciona.")
    mantenimiento_pen: Optional[float] = Field(default=None, description="Monto de mantenimiento en soles. Null si no menciona.")
    servicios_basicos_usd: Optional[float] = Field(default=None, description="Monto de servicios básicos en dólares. Null si no menciona.")
    servicios_basicos_pen: Optional[float] = Field(default=None, description="Monto de servicios básicos en soles. Null si no menciona.")
    tipo_alquiler: Optional[Literal["mensual", "temporal"]] = Field(default=None, description="'mensual' o 'temporal'. Null si no menciona.")
    
    # --- CARACTERÍSTICAS FÍSICAS ---
    tipo_inmueble_homologado: Optional[Literal["casa", "departamento", "habitación", "cuarto", "mini departamento"]] = Field(
        default=None, description="Clasificar estrictamente en uno de estos 5 valores. Null si no se deduce."
    )
    area_total_m2: Optional[float] = Field(default=None, description="Área total en m2. Null si no menciona.")
    area_construida_m2: Optional[float] = Field(default=None, description="Área construida convertida a m2. Null si no menciona.")
    area_techada_m2: Optional[float] = Field(default=None, description="Área techada convertida a m2. Null si no menciona.")
    dormitorios_num: Optional[int] = Field(default=None, description="Número de dormitorios. Null si no menciona.")
    banos_num: Optional[float] = Field(default=None, description="Número de baños (acepta 1.5). Null si no menciona.")
    estacionamientos_num: Optional[int] = Field(default=None, description="Número de estacionamientos/cocheras. Null si no menciona.")
    anio_construccion: Optional[int] = Field(default=None, description="Año de construcción. Null si no menciona.")
    pisos_edificio: Optional[int] = Field(default=None, description="Pisos totales del edificio. Null si no menciona.")
    piso_inmueble: Optional[int] = Field(default=None, description="Piso en el que se ubica. Null si no menciona.")
    
    # --- AMENIDADES Y EXTRAS (1 = Sí, 0 = Explícitamente No, Null = No se menciona) ---
    amoblado: Optional[int] = Field(default=None, description="1 si cuenta con muebles, 0 si dice sin muebles. Null si no menciona.")
    linea_blanca: Optional[int] = Field(default=None, description="1 si tiene línea blanca, 0 si dice no. Null si no menciona.")
    agua_caliente: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    walk_in_closet: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    ascensor: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    piscina: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    gimnasio: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    lavanderia: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    cuarto_servicio: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    seguridad: Optional[int] = Field(default=None, description="1 si tiene vigilancia, 0 si no. Null si no menciona.")
    alarma: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    pet_friendly: Optional[int] = Field(default=None, description="1 si acepta mascotas, 0 si explícitamente prohíbe. Null si no menciona.")
    vista_mar: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    vista_ciudad: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    vista_calle: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    vista_golf: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    coworking: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    zona_parrilla: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    jardin: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    terraza: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    internet: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    aire_acondicionado: Optional[int] = Field(default=None, description="1 si tiene, 0 si no. Null si no menciona.")
    cerca_transporte: Optional[int] = Field(default=None, description="1 si menciona cercanía, 0 si no. Null si no menciona.")
    cerca_comercio: Optional[int] = Field(default=None, description="1 si menciona cercanía, 0 si no. Null si no menciona.")
    cerca_colegio: Optional[int] = Field(default=None, description="1 si menciona cercanía, 0 si no. Null si no menciona.")
    cerca_parque: Optional[int] = Field(default=None, description="1 si menciona cercanía, 0 si no. Null si no menciona.")
    cerca_universidad: Optional[int] = Field(default=None, description="1 si menciona cercanía, 0 si no. Null si no menciona.")
    de_estreno: Optional[int] = Field(default=None, description="1 si es de estreno, 0 si no. Null si no menciona.")
    remodelado: Optional[int] = Field(default=None, description="1 si está remodelado, 0 si no. Null si no menciona.")

class LoteExtraccionSocial(BaseModel):
    resultados: List[ItemInmuebleExtraido]