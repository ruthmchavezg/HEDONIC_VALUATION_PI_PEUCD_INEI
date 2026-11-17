"""Carga del CSV silver de redes sociales (`alquileres_social_silver.csv`) al esquema de base_analitica.

El silver ya viene estructurado (precio, area, dormitorios, atributos en 0/1, coordenadas) pero SIN el texto
del anuncio, asi que no pasa por la extraccion NLP: aqui solo se traduce al mismo formato que produce
`pipeline.ejecutar` para poder unirlo a los portales. Se mantienen el distrito/ambito, las banderas de
calidad y los nombres de atributos (`attr_*`) del resto de la base.

Decisiones documentadas:
  * tipo_inmueble: 'habitacion' -> 'cuarto'; 'mini departamento' -> 'departamento' (el original queda en
    tipo_inmueble_fuente).
  * precision_coord: 'ZONE' si la coordenada se repite en 3 o mas anuncios, tiene 3 decimales o menos, o el
    anuncio no trae direccion (suele ser el centro del distrito); 'DIRECCION' en los demas casos.
  * Facebook muestra el area en "pies cuadrados" pero muchos vendedores escriben metros cuadrados. Cuando un
    departamento o casa de Facebook tiene area < 15 m2 y el valor original (area / 0.0929) esta entre 15 y 400,
    se recupera ese valor y se marca flag_area_pies_corregida (es una heuristica: revisar).
  * Los atributos vacios del silver se toman como 0 (no mencionado) para los 18 atributos que ya existen en la
    base; los 11 atributos adicionales solo existen en redes sociales (en los portales quedan vacios).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calidad import banderas
from .config import settings
from .geografia import clasificar_distrito
from .texto import es_vacio

PIES_A_M2 = 0.09290304
ANIO_ACTUAL = 2026

TIPOS = {
    "departamento": "departamento",
    "mini departamento": "departamento",
    "casa": "casa",
    "habitacion": "cuarto",
    "habitación": "cuarto",
    "cuarto": "cuarto",
}

# columna del silver -> nombre del atributo en la base (lexicon.yaml)
ATRIBUTOS = {
    "amoblado": "amoblado", "ascensor": "ascensor", "piscina": "piscina", "gimnasio": "gimnasio",
    "lavanderia": "lavanderia", "cuarto_servicio": "cuarto_servicio", "seguridad": "seguridad",
    "pet_friendly": "mascotas", "vista_mar": "vista_mar", "jardin": "jardin", "terraza": "terraza",
    "aire_acondicionado": "aire_acondicionado", "cerca_transporte": "cerca_transporte",
    "cerca_comercio": "cerca_comercio", "cerca_colegio": "cerca_colegios", "cerca_parque": "cerca_parques",
    "de_estreno": "a_estrenar", "remodelado": "remodelado",
}
ATRIBUTOS_EXTRA = [
    "linea_blanca", "agua_caliente", "walk_in_closet", "alarma", "vista_ciudad", "vista_calle",
    "vista_golf", "coworking", "zona_parrilla", "internet", "cerca_universidad",
]


def _num(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce")


def _none(v):
    return None if (v is None or v != v) else v


def _tipo(valor) -> str | None:
    if es_vacio(valor):
        return None
    return TIPOS.get(str(valor).strip().lower())


def _decimales(serie: pd.Series) -> pd.Series:
    s = serie.astype("string").str.strip()
    return s.str.split(".", n=1).str[1].str.len().fillna(0)


def precision_coordenadas(lat: pd.Series, lon: pd.Series, direccion: pd.Series) -> pd.Series:
    """'ZONE' (coordenada probablemente del centro de zona/distrito) o 'DIRECCION'; None si no hay coordenada."""
    la, lo = _num(lat), _num(lon)
    clave = la.round(4).astype("string") + "," + lo.round(4).astype("string")
    repetida = clave.map(clave.value_counts()).ge(3)
    pocos_decimales = (_decimales(lat) <= 3) | (_decimales(lon) <= 3)
    sin_direccion = direccion.map(es_vacio)
    prec = pd.Series("DIRECCION", index=lat.index)
    prec = prec.mask(repetida | pocos_decimales | sin_direccion, "ZONE")
    return prec.mask(la.isna() | lo.isna(), None)


def cargar_silver(ruta, anio_actual: int = ANIO_ACTUAL) -> pd.DataFrame:
    """Devuelve el silver con las columnas de base_analitica (mas columnas propias de redes sociales)."""
    cfg = settings()
    cfg_cal = {**cfg["calidad"], "incluir_callao": cfg.get("incluir_callao", False)}

    crudo = pd.read_csv(ruta, encoding="utf-8-sig", dtype=str, keep_default_na=False, na_values=[""])
    c = crudo.copy()
    n = len(c)

    portal = c["portal"].fillna("social").str.strip()
    id_contenido = c["id_contenido"].str.strip()
    lat, lon = _num(c["latitud"]), _num(c["longitud"])
    pen, usd = _num(c["precio_pen"]), _num(c["precio_usd"])
    tipo_fuente = c["tipo_inmueble_homologado"].fillna(c["tipo_inmueble"])
    tipo = tipo_fuente.map(_tipo)
    es_fb = portal.eq("facebook_marketplace")

    # --- areas (con correccion de 'pies cuadrados' mal convertidos en Facebook)
    areas = {k: _num(c[k]) for k in ("area_total_m2", "area_construida_m2", "area_techada_m2")}
    corregida = pd.Series(False, index=c.index)
    for k, serie in areas.items():
        original = serie / PIES_A_M2
        candidata = es_fb & tipo.isin(["departamento", "casa"]) & serie.lt(15) & original.between(15, 400)
        areas[k] = serie.mask(candidata, original.round(1))
        corregida = corregida | candidata

    # --- geografia con la misma regla que los portales (distrito del silver + direccion)
    geo = [clasificar_distrito(_none(d) if not es_vacio(d) else None, _none(dist) if not es_vacio(dist) else None)
           for d, dist in zip(c["direccion"], c["distrito"])]
    distrito = [g[0] for g in geo]
    ambito = [g[1] for g in geo]

    out = pd.DataFrame(index=c.index)
    out["id_anuncio"] = portal + "-" + id_contenido
    out["portal"] = portal
    out["fecha_captura"] = c["timestamp"].str[:10]
    out["id_contenido"] = id_contenido
    out["tipo_inmueble_fuente"] = c["tipo_inmueble"]
    out["fecha_publicacion"] = c["fecha_publicación"] if "fecha_publicación" in c else c.get("fecha_publicacion")
    out["modalidad"] = c["modalidad"]
    out["titulo_anon"] = None
    out["descripcion_anon"] = None
    out["ubicacion_texto"] = c["direccion"]
    out["tipo_alquiler"] = c["tipo_alquiler"]
    out["motivo_temporalidad"] = "silver_redes_sociales"
    out["precio_pen_pub"] = pen
    out["precio_usd_pub"] = usd
    out["moneda_pub"] = [
        "PEN+USD" if (p == p and u == u) else "PEN" if p == p else "USD" if u == u else None
        for p, u in zip(pen, usd)
    ]
    out["distrito"] = distrito
    out["ambito"] = ambito
    out["dormitorios"] = _num(c["dormitorios_num"])
    banos_num = _num(c["banos_num"])
    out["banos"] = banos_num
    # El silver guarda los medios baños como decimales (1.5 = 1 baño + 1 medio baño)
    entero = np.floor(banos_num)
    out["banos_propios"] = entero.where(banos_num.notna())
    out["banos_visita"] = ((banos_num - entero).round(2) == 0.5).astype(float).where(banos_num.notna())
    out["banos_compartidos"] = None
    out["banos_tipo"] = None
    out["banos_evidencia"] = None
    out["estacionamientos"] = _num(c["estacionamientos_num"])
    out["area_total_m2"] = areas["area_total_m2"]
    out["area_construida_m2"] = areas["area_construida_m2"]
    out["area_techada_m2"] = areas["area_techada_m2"]
    out["tipo_inmueble"] = tipo
    out["tipo_inmueble_homologado"] = tipo
    # En habitaciones el silver solo trae CUANTOS baños hay (banos_num), no si son propios o compartidos
    # (no hay texto): no se supone propio. El total sigue en `banos`; el tipo queda "sin_dato".
    es_hab = tipo.eq("cuarto")
    out.loc[es_hab, "banos_propios"] = np.nan
    out["banos_tipo"] = out["banos_tipo"].mask(es_hab, "sin_dato")
    out["es_habitacion"] = es_hab
    # piso_departamento = piso donde esta el departamento o la habitacion; en una casa vale 0
    piso = _num(c["piso_inmueble"]).where(tipo.isin(["departamento", "cuarto"]))
    out["piso_departamento"] = piso.mask(tipo.eq("casa"), 0)
    # cant_pisos = pisos totales de la casa o del edificio (nunca menos que el piso de la unidad)
    cant = _num(c["pisos_edificio"])
    out["cant_pisos"] = cant.mask(cant < out["piso_departamento"])
    anio = _num(c["anio_construccion"])
    out["anio_construccion"] = anio.where(anio.between(1900, 2027))
    antig = (anio_actual - anio).clip(lower=0)
    estreno = _num(c["de_estreno"]).eq(1)
    out["antiguedad_anios"] = antig.mask(estreno & antig.isna(), 0)
    out["anio_construccion"] = out["anio_construccion"].fillna(anio_actual - out["antiguedad_anios"])
    out["latitud"], out["longitud"] = lat, lon
    out["precision_coord"] = precision_coordenadas(c["latitud"], c["longitud"], c["direccion"])
    out["tipo_inmueble_detalle"] = c["tipo_inmueble_homologado"]
    out["mantenimiento_pen"] = _num(c["mantenimiento_pen"])
    out["mantenimiento_usd"] = _num(c["mantenimiento_usd"])
    out["servicios_basicos_pen"] = _num(c["servicios_basicos_pen"])

    # --- atributos 0/1
    for col, nombre in ATRIBUTOS.items():
        out[f"attr_{nombre}"] = (_num(c[col]).fillna(0) > 0).astype(int)
    for col in ATRIBUTOS_EXTRA:
        out[f"attr_{col}"] = (_num(c[col]).fillna(0) > 0).astype(int)

    # Seguridad = vigilancia 24 h, alarma, etc.: se une la alarma al atributo seguridad
    out["attr_seguridad"] = ((out["attr_seguridad"] > 0) | (out["attr_alarma"] > 0)).astype(int)

    # Servicios basicos (dummy): 1 si el alquiler los incluye (monto informado = 0); si el anuncio
    # informa un monto aparte (> 0) o no dice nada, 0. El monto se conserva en servicios_basicos_pen.
    sbp = _num(c["servicios_basicos_pen"])
    out["attr_servicios_basicos"] = sbp.eq(0).astype(int)
    out["mantenimiento_incluido"] = (
        _num(c["mantenimiento_pen"]).eq(0) | _num(c["mantenimiento_usd"]).eq(0)
    )

    # --- banderas de calidad con la misma funcion que los portales
    filas_flags = []
    for i in range(n):
        fila = {
            "precio_pen_pub": _none(pen.iat[i]), "precio_usd_pub": _none(usd.iat[i]),
            "area_total_m2": _none(areas["area_total_m2"].iat[i]),
            "area_construida_m2": _none(areas["area_construida_m2"].iat[i]),
            "area_techada_m2": _none(areas["area_techada_m2"].iat[i]),
            "descripcion_anon": None, "ambito": ambito[i],
        }
        filas_flags.append(banderas(fila, cfg_cal))
    flags = pd.DataFrame(filas_flags, index=c.index)
    out = pd.concat([out, flags], axis=1)

    out["flag_texto_corto"] = None  # sin texto no aplica
    out["flag_modalidad_mixta"] = c["modalidad"].fillna("").str.contains("venta")
    out["flag_alquiler_temporada"] = c["tipo_alquiler"].eq("temporal")
    out["flag_area_pies_corregida"] = corregida
    out["flag_sin_coordenadas"] = lat.isna() | lon.isna()
    out["flag_coord_fuera_lima"] = (
        lat.notna() & lon.notna()
        & ~(lat.between(-12.55, -11.55) & lon.between(-77.25, -76.60))
    )
    return out.reset_index(drop=True)
