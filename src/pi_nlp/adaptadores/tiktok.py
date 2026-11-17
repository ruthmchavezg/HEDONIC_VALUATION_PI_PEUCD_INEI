"""Adaptador de TikTok para transformar publicaciones al esquema común NLP."""
from __future__ import annotations

import pandas as pd

from .base import Adaptador


class AdaptadorTikTok(Adaptador):
    portal = "tiktok"

    def a_esquema(self, crudo: pd.DataFrame) -> pd.DataFrame:
        df = pd.DataFrame(index=crudo.index)

        id_contenido = crudo["id_contenido"].astype("string").str.strip()

        df["url"] = crudo["url"]
        df["titulo"] = None
        df["descripcion"] = crudo["descripcion"]
        df["precio_texto"] = None
        df["ubicacion_texto"] = crudo["distrito"]
        df["distrito_fuente"] = crudo["distrito"]
        df["caracteristicas_texto"] = None
        df["texto_tarjeta"] = crudo["descripcion"]

        df["fecha_captura"] = pd.to_datetime(
            crudo["timestamp"],
            format="%Y-%m-%dT%H:%M:%S",
            errors="coerce",
        )

        df["id_contenido"] = id_contenido
        df["tipo_inmueble_fuente"] = crudo["tipo_inmueble"]
        df["fecha_publicacion"] = crudo["fecha_publicacion"]

        resultado = self._finalizar(df)

        resultado["id_anuncio"] = (
            "tiktok-" + id_contenido.astype(str)
        )

        resultado["id_contenido"] = id_contenido
        resultado["tipo_inmueble_fuente"] = df["tipo_inmueble_fuente"]
        resultado["fecha_publicacion"] = df["fecha_publicacion"]

        return resultado