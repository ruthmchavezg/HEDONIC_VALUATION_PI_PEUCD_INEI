"""Adaptador de redes sociales (Facebook Marketplace y TikTok) a partir del CSV crudo de descartados.

El CSV (`alquileres_social_descartados.csv`) trae una fila por publicacion con su texto completo
(`descripcion`) y los datos de captura. Este adaptador lo convierte al esquema comun para que pase por
la misma limpieza, extraccion y lexicon que los portales.

Facebook Marketplace entrega el texto con una cabecera fija, separada por " | ":
    <titulo> | S/450/mes | Alquileres | [direccion, distrito, LM] | [N pies cuadrados] | ...
    ... | Ubicacion de la propiedad | <distrito>, LM | La ubicacion es aproximada | Descripcion | ...
o bien (publicaciones sin categoria):
    <titulo> | S/400 | · Disponible | Publicado en <distrito>, LM | Detalles | ... | <distrito>, LM · La ubicacion es aproximada
De esa cabecera se toman precio y ubicacion. El distrito del CSV ("distrito_bronce") NO se usa en
Facebook porque en varios casos corresponde a otro lugar; en TikTok si, porque el video no trae
cabecera.
"""
from __future__ import annotations

import re

import pandas as pd

from ..texto import es_vacio
from .base import Adaptador

RE_PRECIO_SEG = re.compile(r"^\s*(?:S/|US\$|\$|USD)\s*\.?\s*\d", re.I)
RE_UBIC_APROX = re.compile(r"(?:^|\|)\s*([^|]+?)\s*·\s*La ubicaci[oó]n es aproximada", re.I)
RE_UBIC_PROPIEDAD = re.compile(r"Ubicaci[oó]n de la propiedad\s*\|\s*([^|]+?)\s*(?:\||$)", re.I)
RE_PUBLICADO_EN = re.compile(r"Publicado\s+(?:hace\s+[^|]*?\s+)?en\s+([^|]+?)\s*(?:\||$)", re.I)
RE_DIRECCION_SEG3 = re.compile(r"^\s*(?:S/|US\$|\$)[^|]*\|\s*Alquileres\s*\|\s*([^|]+?)\s*\|", re.I)


def _segmentos(texto: str) -> list[str]:
    return [s.strip() for s in texto.split(" | ")]


def precio_de_cabecera(texto: str | None) -> str | None:
    """Segmento de precio de la cabecera de Facebook ('S/450/mes'), o None si no hay."""
    if es_vacio(texto):
        return None
    for seg in _segmentos(str(texto))[1:4]:
        if RE_PRECIO_SEG.match(seg):
            return seg
    return None


def ubicacion_de_cabecera(texto: str | None) -> str | None:
    """Ubicacion del inmueble en Facebook: 'Avenida X, Chorrillos, LM' o 'La Victoria, LM'."""
    if es_vacio(texto):
        return None
    t = str(texto)
    # 1) direccion completa en el tercer segmento (publicaciones con 'Detalles de la unidad')
    m = RE_DIRECCION_SEG3.match(t)
    if m and "pies cuadrados" not in m.group(1).lower() and not m.group(1).lower().startswith("publicado"):
        return m.group(1)
    for rx in (RE_UBIC_PROPIEDAD, RE_UBIC_APROX, RE_PUBLICADO_EN):
        m = rx.search(t)
        if m:
            return m.group(1)
    return None


def area_pies(texto: str | None) -> float | None:
    """'1434 pies cuadrados' -> 1434.0 (valor tal como lo muestra Facebook)."""
    if es_vacio(texto):
        return None
    m = re.search(r"(\d[\d.,]*)\s*pies cuadrados", str(texto), re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "").rstrip("."))
    except ValueError:
        return None


class AdaptadorSocial(Adaptador):
    """CSV de descartados de redes sociales (Facebook Marketplace / TikTok) -> esquema comun."""

    portal = "social"

    def a_esquema(self, crudo: pd.DataFrame) -> pd.DataFrame:
        df = pd.DataFrame(index=crudo.index)
        portal = crudo["portal"].fillna("social").astype(str).str.strip()
        texto = crudo["descripcion"]
        es_fb = portal.eq("facebook_marketplace")

        df["url"] = crudo["url"]
        df["titulo"] = [
            _segmentos(str(t))[0] if (fb and not es_vacio(t)) else None
            for t, fb in zip(texto, es_fb)
        ]
        df["descripcion"] = texto
        df["precio_texto"] = [
            precio_de_cabecera(t) if fb else None for t, fb in zip(texto, es_fb)
        ]
        df["ubicacion_texto"] = [
            ubicacion_de_cabecera(t) if fb else d
            for t, d, fb in zip(texto, crudo["distrito_bronce"], es_fb)
        ]
        df["distrito_fuente"] = [
            None if fb else d for d, fb in zip(crudo["distrito_bronce"], es_fb)
        ]
        df["caracteristicas_texto"] = None
        df["texto_tarjeta"] = texto
        df["fecha_captura"] = crudo["timestamp"]

        id_contenido = crudo["id_contenido"].astype("string").str.strip()
        df["id_contenido"] = id_contenido
        df["tipo_inmueble_fuente"] = crudo["tipo_inmueble_bronce"]
        df["fecha_publicacion"] = crudo["fecha_publicacion"]

        resultado = self._finalizar(df)
        # un mismo archivo mezcla portales: cada fila conserva el suyo
        resultado["portal"] = portal.to_numpy()
        resultado["id_anuncio"] = [
            f"{p}-{i}" for p, i in zip(portal, id_contenido.astype(str))
        ]
        for c in ("id_contenido", "tipo_inmueble_fuente", "fecha_publicacion"):
            resultado[c] = df[c]
        return resultado
