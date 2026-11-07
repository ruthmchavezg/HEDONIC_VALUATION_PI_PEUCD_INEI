"""Adaptador de Adondevivir para transformar los datos del portal al esquema común."""
from __future__ import annotations

import pandas as pd

from ..texto import es_vacio
from .base import Adaptador


def _unir(*valores) -> str | None:
    """Une textos no vacíos y distintos, conservando el contenido original."""
    vistos: list[str] = []

    for v in valores:
        if not es_vacio(v):
            texto = str(v).strip()
            if texto not in vistos:
                vistos.append(texto)

    return " | ".join(vistos) or None


class AdaptadorAdondeVivir(Adaptador):
    portal = "adondevivir"

    def a_esquema(self, crudo: pd.DataFrame) -> pd.DataFrame:
        df = pd.DataFrame(index=crudo.index)

        # Identificación y datos principales
        df["url"] = crudo["url"]
        df["titulo"] = crudo.get("titulo")
        df["descripcion"] = crudo.get("descripcion")
        df["precio_texto"] = crudo.get("precio_general")
        df["ubicacion_texto"] = crudo.get("ubicacion")

        # Consolidación de características disponibles
        columnas_caracteristicas = [
            "datos_principales_generales",
            "comodidades_proyecto",
            "otras_caracteristicas",
            "unidades_detalladas",
            "caracteristicas_dinamicas",
            "estado_proyecto",
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

        # Fecha real de captura
        df["fecha_captura"] = (
            crudo["fecha_scrapeo"]
            if "fecha_scrapeo" in crudo.columns
            else crudo.get("fecha_captura")
        )

        return self._finalizar(df)