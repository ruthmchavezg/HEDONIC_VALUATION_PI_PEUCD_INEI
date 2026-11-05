"""Adaptador de AdondeVivir (scraper de Roque: solo guarda el texto de la tarjeta del listado).

Descarta banners ('Super destacado', 'WhatsApp / Contactar'), filas sin URL de anuncio y URLs repetidas.
Limitación: el texto de la tarjeta no es la descripción completa; hasta que el scraper entre a cada anuncio,
esta fuente aporta campos estructurados pero casi nada de texto libre.
"""
from __future__ import annotations

import re

import pandas as pd

from ..logging_utils import get_logger
from .base import Adaptador, limpiar_url

log = get_logger()
MIN_CHARS_TARJETA = 60
RE_LINEA_ESTRUCTURADA = re.compile(r"m²|m2|dorm|baño|bano|estac|cochera|S/|USD|US\$", re.I)
RE_LINEA_PRECIO = re.compile(r"S/|USD|US\$")


class AdaptadorAdondeVivir(Adaptador):
    portal = "adondevivir"

    def a_esquema(self, crudo: pd.DataFrame) -> pd.DataFrame:
        n0 = len(crudo)
        df = crudo.copy()
        df["url"] = df["url"].map(limpiar_url)
        df = df[df["url"].notna() & (df["texto_bruto"].fillna("").str.len() > MIN_CHARS_TARJETA)]
        df = df.drop_duplicates("url")
        log.info("AdondeVivir: %d filas crudas -> %d anuncios con URL y texto útil", n0, len(df))

        out = pd.DataFrame(index=df.index)
        out["url"] = df["url"]
        out["texto_tarjeta"] = df["texto_bruto"]
        lineas = df["texto_bruto"].fillna("").str.split("\n")
        # La descripción no debe repetir el precio (ya va en precio_texto): evita una falsa fuga de información.
        out["descripcion"] = [" | ".join(l for l in ls if not RE_LINEA_PRECIO.search(l)) or None for ls in lineas]
        out["precio_texto"] = [" | ".join(l for l in ls if re.search(r"S/|USD|US\$", l)) or None for ls in lineas]
        out["caracteristicas_texto"] = [
            " | ".join(l for l in ls if RE_LINEA_ESTRUCTURADA.search(l)) or None for ls in lineas
        ]
        out["distrito_fuente"] = df.get("distrito")
        out["fecha_captura"] = df.get("fecha_captura")
        return self._finalizar(out)
