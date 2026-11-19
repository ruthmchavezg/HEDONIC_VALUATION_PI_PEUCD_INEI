"""Adaptador de Babilonia para transformar los anuncios al esquema común NLP."""
from __future__ import annotations

import re

import pandas as pd

from ..texto import es_vacio
from .base import Adaptador

RE_MANTENIMIENTO = re.compile(r"Mantenimiento\s*:\s*([^|]+)", re.I)


def _mantenimiento(detalles) -> str | None:
    """'Año de construcción: 1996 | Mantenimiento: S/1400 | ...' -> 'S/1400'."""
    if es_vacio(detalles):
        return None
    m = RE_MANTENIMIENTO.search(str(detalles))
    return m.group(1).strip() if m else None


def _decimales(valor) -> int:
    texto = str(valor).strip()
    return len(texto.split(".", 1)[1]) if "." in texto else 0


def _precision(lat: pd.Series, lon: pd.Series) -> pd.Series:
    """'ZONE' si la coordenada se repite en 3 o mas anuncios o tiene <= 3 decimales (centro de zona);
    'EXACT' en los demas casos; None si no hay coordenada."""
    la = pd.to_numeric(lat, errors="coerce")
    lo = pd.to_numeric(lon, errors="coerce")
    clave = la.round(4).astype("string") + "," + lo.round(4).astype("string")
    repetida = clave.map(clave.value_counts()).ge(3)
    pocos = pd.Series([_decimales(a) <= 3 or _decimales(b) <= 3 for a, b in zip(lat, lon)], index=lat.index)
    prec = pd.Series("EXACT", index=lat.index).mask(repetida | pocos, "ZONE")
    return prec.mask(la.isna() | lo.isna(), None)


def _unir(*valores) -> str | None:
    """Une textos no vacíos y distintos, conservando el contenido original."""
    vistos: list[str] = []

    for valor in valores:
        if not es_vacio(valor):
            texto = str(valor).strip()
            if texto not in vistos:
                vistos.append(texto)

    return " | ".join(vistos) or None


class AdaptadorBabilonia(Adaptador):
    portal = "babilonia"

    def a_esquema(self, crudo: pd.DataFrame) -> pd.DataFrame:
        df = pd.DataFrame(index=crudo.index)

        # Identificación y datos principales
        df["url"] = crudo["url"]
        df["titulo"] = crudo.get("titulo")
        df["descripcion"] = crudo.get("descripcion")
        df["precio_texto"] = crudo.get("precios_crudos")
        df["ubicacion_texto"] = crudo.get("direccion")

        # Características disponibles en Babilonia
        columnas_caracteristicas = [
            "info",
            "comodidades",
            "detalles_extra",
        ]

        columnas_disponibles = [
            crudo[col] if col in crudo.columns
            else pd.Series(None, index=crudo.index)
            for col in columnas_caracteristicas
        ]

        df["caracteristicas_texto"] = [
            _unir(*valores)
            for valores in zip(*columnas_disponibles)
        ]

        # Texto complementario del anuncio
        df["texto_tarjeta"] = [
            _unir(titulo, precio, ubicacion)
            for titulo, precio, ubicacion in zip(
                df["titulo"],
                df["precio_texto"],
                df["ubicacion_texto"],
            )
        ]

        # Fecha de captura
        df["fecha_captura"] = crudo.get("timestamp")

        # Coordenadas (el portal las publica en latitud / longitud)
        if "latitud" in crudo.columns and "longitud" in crudo.columns:
            df["latitud"] = pd.to_numeric(crudo["latitud"], errors="coerce")
            df["longitud"] = pd.to_numeric(crudo["longitud"], errors="coerce")
            df["precision_coord"] = _precision(crudo["latitud"], crudo["longitud"])

        # Campos adicionales para trazabilidad
        id_interno = crudo["id_interno"].astype("string").str.strip()

        df["id_interno"] = id_interno
        df["tipo_inmueble_fuente"] = crudo["tipo_inmueble"]
        df["json_ld"] = crudo["json_ld"] if "json_ld" in crudo.columns else None
        df["mantenimiento_texto"] = crudo["detalles_extra"].map(_mantenimiento) if "detalles_extra" in crudo.columns else None

        resultado = self._finalizar(df)

        # Identificador estable basado en el ID original de Babilonia
        resultado["id_anuncio"] = [
            f"babilonia-{valor}"
            if not es_vacio(valor)
            else id_anuncio
            for valor, id_anuncio in zip(
                id_interno,
                resultado["id_anuncio"],
            )
        ]

        # Recuperación de campos adicionales no incluidos en ESQUEMA
        resultado["id_interno"] = id_interno
        resultado["tipo_inmueble_fuente"] = df["tipo_inmueble_fuente"]
        resultado["json_ld"] = df["json_ld"]
        resultado["mantenimiento_texto"] = df["mantenimiento_texto"]

        return resultado
