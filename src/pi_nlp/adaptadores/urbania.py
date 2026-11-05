"""Adaptador de Urbania (scraper de Giorgio: una fila por anuncio con descripción completa)."""
from __future__ import annotations

import pandas as pd

from ..texto import es_vacio
from .base import Adaptador


def _unir(*valores) -> str | None:
    """Une textos no vacíos y distintos (en Urbania varias columnas repiten el mismo contenido)."""
    vistos: list[str] = []
    for v in valores:
        if not es_vacio(v) and str(v) not in vistos:
            vistos.append(str(v))
    return " | ".join(vistos) or None


class AdaptadorUrbania(Adaptador):
    portal = "urbania"

    def a_esquema(self, crudo: pd.DataFrame) -> pd.DataFrame:
        df = pd.DataFrame(index=crudo.index)
        df["url"] = crudo["url"]
        df["titulo"] = crudo.get("titulo")
        df["descripcion"] = crudo.get("descripcion")
        df["precio_texto"] = crudo.get("precio_general")
        df["ubicacion_texto"] = crudo.get("ubicacion")
        df["caracteristicas_texto"] = [
            _unir(a, b) for a, b in zip(crudo.get("caracteristicas_dinamicas"), crudo.get("datos_principales_generales"))
        ]
        df["fecha_captura"] = crudo["fecha_captura"] if "fecha_captura" in crudo else None
        return self._finalizar(df)
