"""Adaptador de Babilonia para transformar los anuncios al esquema común NLP."""
from __future__ import annotations

import pandas as pd

from ..texto import es_vacio
from .base import Adaptador


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

        # Campos adicionales para trazabilidad
        id_interno = crudo["id_interno"].astype("string").str.strip()

        df["id_interno"] = id_interno
        df["tipo_inmueble_fuente"] = crudo["tipo_inmueble"]
        df["json_ld"] = crudo["json_ld"]

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

        return resultado
