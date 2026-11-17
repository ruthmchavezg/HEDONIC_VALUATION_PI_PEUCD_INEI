
"""Adaptador de Urbania para transformar los datos extraídos del portal al esquema común."""
from __future__ import annotations

import pandas as pd

from ..texto import es_vacio
from .base import Adaptador, parsear_coordenadas


def _unir(*valores) -> str | None:
    """Une textos no vacíos y distintos, conservando el contenido original."""
    vistos: list[str] = []

    for v in valores:
        if not es_vacio(v):
            texto = str(v).strip()
            if texto not in vistos:
                vistos.append(texto)

    return " | ".join(vistos) or None


class AdaptadorUrbania(Adaptador):
    portal = "urbania"

    def a_esquema(self, crudo: pd.DataFrame) -> pd.DataFrame:
        df = pd.DataFrame(index=crudo.index)

        # Identificación y datos principales del anuncio
        df["url"] = crudo["url"]
        df["titulo"] = crudo.get("titulo")
        df["descripcion"] = crudo.get("descripcion")
        df["precio_texto"] = crudo.get("precio_general")
        df["ubicacion_texto"] = crudo.get("ubicacion")

        # Consolidación de características disponibles en Urbania.
        columnas_caracteristicas = [
            "datos_principales_generales",
            "caracteristicas_generales",
            "servicios",
            "ambientes",
            "exteriores",
            "comodidades_proyecto",
            "otras_caracteristicas_proyecto",
        ]

        columnas_disponibles = [
            crudo[col] if col in crudo.columns
            else pd.Series(None, index=crudo.index)
            for col in columnas_caracteristicas
        ]

        df["caracteristicas_texto"] = [
            _unir(
                *(
                    valor
                    for columna, valor in zip(columnas_caracteristicas, valores)
                    if not (
                        columna == "datos_principales_generales"
                        and isinstance(valor, str)
                        and "unidades" in valor.lower()
                    )
                )
            )
            for valores in zip(*columnas_disponibles)
        ]

        # Texto complementario de la tarjeta del anuncio
        df["texto_tarjeta"] = [
            _unir(titulo, precio, ubicacion)
            for titulo, precio, ubicacion in zip(
                df["titulo"],
                df["precio_texto"],
                df["ubicacion_texto"],
            )
        ]

        # Coordenadas del anuncio (columna "coordenadas": "lat,lon"). Urbania no informa precisión.
        coords = [
            parsear_coordenadas(v)
            for v in crudo.get("coordenadas", pd.Series(None, index=crudo.index))
        ]
        df["latitud"] = [c[0] for c in coords]
        df["longitud"] = [c[1] for c in coords]
        df["precision_coord"] = [
            "DESCONOCIDA" if c[0] is not None else None for c in coords
        ]

        # Fecha de captura, si está disponible
        df["fecha_captura"] = (
            crudo["fecha_captura"]
            if "fecha_captura" in crudo.columns
            else None
        )

        resultado = self._finalizar(df)

        # Priorizar la modalidad explícita del precio publicado en Urbania.
        precio_original = crudo.get(
            "precio_general",
            pd.Series("", index=crudo.index)
        ).fillna("").astype(str)

        modalidad_precio = precio_original.str.extract(
            r"^\s*(alquiler|venta)\b",
            flags=__import__("re").IGNORECASE,
            expand=False
        ).str.lower()

        resultado["modalidad_url"] = modalidad_precio.combine_first(
            resultado["modalidad_url"]
        )

        return resultado
