
"""Orquestador: crudo -> esquema común -> limpieza -> anonimización -> extracción
-> lexicón -> banderas de calidad -> deduplicación -> base analítica + reporte.

Cada paso es una función de módulo propio, por lo que se puede probar y
documentar por separado.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .adaptadores import ADAPTADORES
from .anonimizar import anonimizar
from .calidad import banderas, fuga_precio, reporte_cobertura
from .config import settings
from .costos import extraer_mantenimiento
from .dedup import marcar_duplicados
from .extraccion import extraer_campos
from .geografia import clasificar_distrito
from .lexicon import extraer_atributos
from .logging_utils import get_logger
from .precio import asignar_precio_desde_montos, parsear_precio
from .texto import limpiar_texto, normalizar
from .temporalidad import clasificar_temporalidad

log = get_logger()


@dataclass
class Entrada:
    fuente: str
    ruta: Path
    modalidad: str


def _num_o_none(v):
    """Convierte a float; None si está vacío o no es número (NaN incluido)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _anio_captura(valor, por_defecto: int = 2026) -> int:
    """Año de la fecha de captura ('2026-11-08', '2026-11-10T06:14:04'); por_defecto si no se puede leer."""
    try:
        anio = int(str(valor)[:4])
        return anio if 2000 <= anio <= 2100 else por_defecto
    except (TypeError, ValueError):
        return por_defecto


def _procesar_fila(r: pd.Series, cfg_cal: dict, cfg_ext: dict) -> dict:
    """Procesa un anuncio y devuelve una fila de la base analítica."""

    # Limpieza inicial de los campos
    titulo = limpiar_texto(r["titulo"])
    descr = limpiar_texto(r["descripcion"])
    caract = limpiar_texto(r["caracteristicas_texto"])
    ubic = limpiar_texto(r["ubicacion_texto"])
    precio_txt = limpiar_texto(r["precio_texto"])

    # Anonimización
    a_tit = anonimizar(titulo)
    a_des = anonimizar(descr)
    a_car = anonimizar(caract)

    contacto = (
        a_des.n_telefonos
        + a_des.n_correos
        + a_des.n_contactos
        + a_car.n_telefonos
        + a_car.n_contactos
    )

    # Construcción inicial de la fila
    fila: dict = {
        "id_anuncio": r["id_anuncio"],
        "portal": r["portal"],
        "fecha_captura": r["fecha_captura"],

        # Trazabilidad de fuentes con identificadores propios.
        "id_contenido": r.get("id_contenido"),
        "tipo_inmueble_fuente": r.get("tipo_inmueble_fuente"),
        "fecha_publicacion": r.get("fecha_publicacion"),

        "modalidad": (
        r["modalidad_url"]
        if pd.notna(r["modalidad_url"]) and str(r["modalidad_url"]).strip()
        else r["modalidad_esperada"]
        ),
        "titulo_anon": a_tit.texto,
        "descripcion_anon": a_des.texto,
        "ubicacion_texto": ubic,

        # Coordenadas del portal (pasan tal cual desde el adaptador)
        "latitud": _num_o_none(r.get("latitud")),
        "longitud": _num_o_none(r.get("longitud")),
        "precision_coord": r.get("precision_coord") if pd.notna(r.get("precision_coord")) else None,
    }

    # Clasificación de la temporalidad del alquiler
    fila.update(
        clasificar_temporalidad(
            fila["titulo_anon"],
            fila["descripcion_anon"],
        )
    )


    # Extracción del precio publicado según la fuente
    if r["portal"] == "tiktok":
        montos_detectados = (
            a_tit.montos
            + a_des.montos
            + a_car.montos
        )

        fila.update(
            asignar_precio_desde_montos(montos_detectados)
        )
    else:
        fila.update(parsear_precio(precio_txt))


    # Clasificación geográfica
    fila["distrito"], fila["ambito"] = clasificar_distrito(
        ubic,
        limpiar_texto(r["distrito_fuente"]),
    )

    # Extracción de características estructuradas
    fila.update(
        extraer_campos(
            a_tit.texto,
            a_car.texto,
            a_des.texto,
            cfg_ext,
        )
    )
    # Mantenimiento mensual (campo estructurado del portal o texto libre) y si viene incluido en el precio
    fila.update(
        extraer_mantenimiento(
            [titulo, caract, descr],
            r.get("mantenimiento_texto"),
        )
    )

    # Año de construcción: el explícito del anuncio; si no, año de captura menos antigüedad
    antig = fila.get("antiguedad_anios")
    if fila.get("anio_construccion_texto"):
        fila["anio_construccion"] = fila["anio_construccion_texto"]
        fila["anio_construccion_fuente"] = "texto"
    elif antig is not None and antig == antig:
        fila["anio_construccion"] = _anio_captura(fila["fecha_captura"]) - int(antig)
        fila["anio_construccion_fuente"] = "antiguedad"
    else:
        fila["anio_construccion"] = None
        fila["anio_construccion_fuente"] = None

    # Homologación del tipo de inmueble informado por la fuente.
    tipo_fuente = normalizar(limpiar_texto(r.get("tipo_inmueble_fuente")))

    homologacion_tipos = {
        "casa": "casa",
        "departamento": "departamento",
        "habitacion": "cuarto",
    }

    fila["tipo_inmueble_homologado"] = homologacion_tipos.get(
        tipo_fuente
    )

    # Extracción de atributos mediante el lexicón
    fila.update(
        extraer_atributos(
            " | ".join(
                x for x in (a_car.texto, a_des.texto) if x
            )
        )
    )

    # Indicadores de calidad
    fila["n_palabras"] = len((a_des.texto or "").split())
    fila["flag_contacto_en_texto"] = contacto > 0

    fila["flag_fuga_precio"] = fuga_precio(
    a_des.montos + a_tit.montos + a_car.montos,
    fila["precio_pen_pub"],
    fila["precio_usd_pub"],
    cfg_cal["tolerancia_fuga"],
    [
        a_tit.texto,
        a_des.texto,
        a_car.texto,
    ],
)

    fila.update(banderas(fila, cfg_cal))

    # Control de coordenadas: sin dato, o fuera de una caja aproximada de Lima y Callao
    lat, lon = fila["latitud"], fila["longitud"]
    fila["flag_sin_coordenadas"] = lat is None or lon is None
    fila["flag_coord_fuera_lima"] = bool(
        lat is not None and lon is not None
        and not (-12.55 <= lat <= -11.55 and -77.25 <= lon <= -76.60)
    )

    return fila


def ejecutar(
    entradas: list[Entrada],
    dir_salida: Path,
    fecha_captura: str | None = None,
    modalidad_objetivo: str | None = None,
) -> pd.DataFrame:
    """
    Ejecuta el pipeline completo sobre una o varias fuentes.

    Genera la base analítica y el reporte de calidad.
    La clasificación temporal no elimina anuncios: únicamente agrega
    las columnas tipo_alquiler y motivo_temporalidad.
    """

    cfg = settings()

    random.seed(cfg["seed"])
    np.random.seed(cfg["seed"])

    objetivo = modalidad_objetivo or cfg["modalidad_objetivo"]

    dir_salida.mkdir(parents=True, exist_ok=True)

    reporte: dict = {
        "modalidad_objetivo": objetivo,
        "fuentes": {},
    }

    partes = []

    # Lectura y adaptación de las fuentes
    for e in entradas:
        log.info(
            "Fuente %s (modalidad declarada: %s) <- %s",
            e.fuente,
            e.modalidad,
            e.ruta,
        )

        adaptador = ADAPTADORES[e.fuente](e.modalidad, fecha_captura)

        esquema = adaptador.a_esquema(
            adaptador.leer(e.ruta)
        )

        n_in = len(esquema)

        modal = esquema["modalidad_url"].fillna(
            esquema["modalidad_esperada"]
        )

        excluidas = int((modal != objetivo).sum())

        esquema = esquema[modal == objetivo]

        log.info(
            "  %d anuncios en esquema; %d excluidos por modalidad distinta de '%s'",
            n_in,
            excluidas,
            objetivo,
        )

        clave_fuente = f"{e.fuente}_{e.ruta.stem}"

        reporte["fuentes"][clave_fuente] = {
            "anuncios_esquema": n_in,
            "excluidos_por_modalidad": excluidas,
        }

        partes.append(esquema)

    esquema_total = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame()
    )

    if esquema_total.empty:
        log.warning(
            "No quedaron anuncios de modalidad '%s'; no se genera base analítica.",
            objetivo,
        )

        reporte["filas_salida"] = 0

        (
            dir_salida / "reporte_calidad.json"
        ).write_text(
            json.dumps(reporte, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return pd.DataFrame()

    # Configuración de calidad
    cfg_cal = {
        **cfg["calidad"],
        "incluir_callao": cfg.get("incluir_callao", False),
    }

    # Procesamiento individual de anuncios
    filas = []

    for _, r in esquema_total.iterrows():
        try:
            filas.append(
                _procesar_fila(r, cfg_cal, cfg["calidad"])
            )
        except Exception:
            # Un anuncio defectuoso no debe detener todo el lote
            log.exception(
                "Error procesando %s; se omite",
                r.get("url"),
            )

    df = pd.DataFrame(filas)

    # Preservar identificadores de TikTok como texto
    if "id_contenido" in df.columns:
        df["id_contenido"] = pd.array(
            [fila.get("id_contenido") for fila in filas],
            dtype="string",
        )


    # Identificación de duplicados sin eliminarlos
    df = marcar_duplicados(df, cfg["dedup"])

    # Columnas utilizadas para calcular cobertura
    cols_cobertura = [
        "precio_pen_pub",
        "precio_usd_pub",
        "distrito",
        "tipo_inmueble",
        "dormitorios",
        "banos",
        "estacionamientos",
        "area_titulo_m2",
        "area_terreno_m2",
        "area_construida_m2",
        "area_techada_m2",
        "area_total_m2",
        "n_pisos",
        "piso_departamento",
        "pisos_edificio",
        "antiguedad_anios",
        "anio_construccion",
        "banos_propios",
        "banos_compartidos",
        "banos_visita",
        "mantenimiento_pen",
        "mantenimiento_usd",
        "descripcion_anon",
        "latitud",
        "longitud",
    ]

    # Resumen de clasificación temporal
    resumen_temporalidad = (
        df["tipo_alquiler"].value_counts(dropna=False).to_dict()
    )

    # Reporte de calidad
    reporte.update({
        "filas_salida": len(df),
        "por_portal": df["portal"].value_counts().to_dict(),
        "cobertura_pct": reporte_cobertura(
            df,
            cols_cobertura,
        ),
        "banderas": {
            c: int(df[c].sum())
            for c in df.columns
            if c.startswith("flag_")
        },
        "duplicados": int(df["es_duplicado"].sum()),
        "ambito": df["ambito"].value_counts().to_dict(),
        "fecha_captura_disponible": bool(
            df["fecha_captura"].notna().any()
        ),
        "clasificacion_temporalidad": resumen_temporalidad,
    })

    # Guardado de resultados
    df.to_csv(
        dir_salida / "base_analitica.csv",
        index=False,
        encoding="utf-8-sig",
    )

    (
        dir_salida / "reporte_calidad.json"
    ).write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log.info(
        "Listo: %d filas -> %s",
        len(df),
        dir_salida,
    )

    return df
