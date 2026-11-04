# [COMENTARIO] IMPORTACIONES DE LIBRERÍAS
# Lo que hace: Importa clases específicas de Pydantic para definir modelos, campos y validadores, así como el módulo 'Optional' de Python.
# Para qué sirve: Permite crear esquemas de datos estructurados para validación y manejo de tipos opcionales en el código.
# Metodología: Uso de librerías de validación de datos modernas y tipado estático (Typing) para evitar errores de tipo en tiempo de ejecución.
from pydantic import BaseModel, Field, model_validator
from typing import Optional

# [COMENTARIO] DEFINICIÓN DE CLASE DEL MODELO
# Lo que hace: Define la clase base 'OfertaInmobiliariaINEI' que hereda de 'BaseModel' de Pydantic.
# Para qué sirve: Establece la estructura o plantilla principal de datos que el scraper debe capturar y validar para cada anuncio inmobiliario[cite: 11, 12].
# Metodología: Modelado de datos orientado a objetos y validación declarativa.
class OfertaInmobiliariaINEI(BaseModel):
    # [COMENTARIO] VARIABLES DE IDENTIFICACIÓN
    # Lo que hace: Define los campos básicos de identificación de un anuncio (ID, fecha, portal, tipo de inmueble, estado multiunidad, y URL) junto con reglas de longitud en el ID.
    # Para qué sirve: Asegura que cada anuncio tenga un ID válido, de un portal específico, en una fecha determinada y permite verificar su fuente[cite: 11].
    # Metodología: Tipado estricto y validación de atributos mínimos para trazabilidad del dato.
    id_anuncio: str = Field(..., min_length=2)
    fecha_captura: str
    portal: str
    tipo_inmueble: str
    es_proyecto_multiunidad: bool = False
    url: str

    # Variables Económicas y Control Cambiario (BCRP)
    # [COMENTARIO] VARIABLES ECONÓMICAS
    # Lo que hace: Define variables para controlar el precio y la moneda, con reglas como que el precio debe ser mayor a 500 y la moneda solo "USD" o "PEN". También exige un tipo de cambio y reserva espacios opcionales para los precios convertidos.
    # Para qué sirve: Obliga al scraper a extraer datos económicos confiables y permite estandarizar precios a una sola moneda usando el tipo de cambio del BCRP[cite: 12].
    # Metodología: Restricciones de valor (gt=500), validación mediante expresiones regulares (pattern) para consistencia y campos nulos por defecto.
    moneda_original: Optional[str] = Field(default="PEN", pattern="^(USD|PEN)$")
    precio_original: Optional[float] = Field(default=None, gt=500)
    tipo_cambio_bcrp: float = Field(..., gt=1.0)
    precio_pen: Optional[float] = None
    precio_usd: Optional[float] = None

    # Variables Estructurales Numéricas (Extraídas con Regex / JSON-LD)
    # [COMENTARIO] VARIABLES ESTRUCTURALES
    # Lo que hace: Define campos opcionales con restricciones lógicas para las características físicas del inmueble: áreas mayores a 0, número de habitaciones/baños/estacionamientos entre 0 y 40, y antigüedad hasta 150 años.
    # Para qué sirve: Controla que los valores extraídos por Regex sean realistas (ej. que una casa no tenga -2 baños o 300 estacionamientos), preparando variables limpias para el modelo de Machine Learning[cite: 12].
    # Metodología: Parametrización de límites de dominio (ge=0, le=40) para garantizar la calidad y limpieza de la base de datos estructural.
    area_total_m2: Optional[float] = Field(default=None, gt=0)
    area_construida_m2: Optional[float] = Field(default=None, gt=0)
    dormitorios_num: Optional[int] = Field(default=None, ge=0, le=40)
    banos_num: Optional[int] = Field(default=None, ge=0, le=40)
    estacionamientos_num: Optional[int] = Field(default=None, ge=0, le=40)
    antiguedad_anos: Optional[int] = Field(default=None, ge=0, le=150)

    # Variables Geoespaciales (Para cruce con OpenStreetMap e Índice de Moran)
    # [COMENTARIO] VARIABLES GEOESPACIALES
    # Lo que hace: Define variables de ubicación, exigiendo que las coordenadas de latitud y longitud, si existen, correspondan exclusivamente al recuadro geográfico de Lima Metropolitana.
    # Para qué sirve: Filtra automáticamente inmuebles que estén fuera de Lima y guarda las coordenadas necesarias para el análisis espacial y distancias en OpenStreetMap[cite: 12].
    # Metodología: Filtrado geoespacial automatizado en tiempo de validación a través de bounding boxes (cajas delimitadoras de coordenadas).
    distrito: Optional[str] = None
    ubicacion: str = "No especificado"
    latitud: Optional[float] = Field(default=None, ge=-13.2, le=-11.4)
    longitud: Optional[float] = Field(default=None, ge=-77.4, le=-76.5)

    # Variables Textuales Crudas (Para Etapa 3: NLP y Limpieza)
    # [COMENTARIO] VARIABLES DE TEXTO LIBRE
    # Lo que hace: Inicializa en "No especificado" los campos de texto largo relacionados con títulos, comodidades y descripciones.
    # Para qué sirve: Almacena los bloques de texto crudo raspados de la web para su posterior análisis con Procesamiento de Lenguaje Natural (NLP)[cite: 12].
    # Metodología: Almacenamiento "crudo" con valores de respaldo (fallbacks) para manejar ausencias de datos en anuncios incompletos de forma segura.
    titulo: str = "No especificado"
    precio_general: str = "No especificado"
    estado_proyecto: str = "No especificado"
    datos_principales_generales: str = "No especificado"
    caracteristicas: str = "No especificado"
    otras_caracteristicas: str = "No especificado"
    comodidades: str = "No especificado"
    descripcion: str = "No especificado"
    unidades_detalladas: str = "[]"

    # [COMENTARIO] FUNCIÓN VALIDADORA AUTOMÁTICA
    # Lo que hace: Se ejecuta automáticamente después (mode="after") de que el modelo se ha inicializado y valida o modifica los datos del objeto.
    # Para qué sirve: Realiza la conversión matemática automática del precio original a USD y PEN basándose en el tipo de cambio del BCRP capturado ese día[cite: 12].
    # Metodología: Lógica de transformación ("Feature Engineering") integrada en la validación (Pydantic model_validator).
    @model_validator(mode="after")
    def calcular_conversion_cambiaria(self):
        # [COMENTARIO] CÁLCULO DE TIPO DE CAMBIO
        # Lo que hace: Verifica si hay precio y moneda válidos. Si la moneda es USD, calcula y guarda el valor en soles (PEN) usando el tipo de cambio. Si es PEN, hace lo inverso.
        # Para qué sirve: Estandariza económicamente los anuncios a dos columnas numéricas uniformes, sin importar cómo se publicó el anuncio originalmente.
        # Metodología: Aritmética simple con redondeo a dos decimales para manejo financiero estándar.
        if self.precio_original and self.moneda_original:
            if self.moneda_original == "USD":
                self.precio_usd = round(self.precio_original, 2)
                self.precio_pen = round(self.precio_original * self.tipo_cambio_bcrp, 2)
            else:
                self.precio_pen = round(self.precio_original, 2)
                self.precio_usd = round(self.precio_original / self.tipo_cambio_bcrp, 2)
        return self