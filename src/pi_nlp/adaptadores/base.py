"""Contrato de entrada del módulo NLP: cada portal tiene un adaptador que convierte sus
columnas al esquema común. La limpieza, extracción y lexicón se aplican después, una sola vez."""
from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

ESQUEMA = [
    "id_anuncio", "portal", "url", "fecha_captura", "modalidad_esperada", "modalidad_url",
    "titulo", "descripcion", "precio_texto", "ubicacion_texto", "distrito_fuente",
    "caracteristicas_texto", "texto_tarjeta",
]


def limpiar_url(url) -> str | None:
    """Quita parámetros de búsqueda (?n_pos=..., #...) que cambian en cada captura."""
    if url is None or (isinstance(url, float) and url != url) or str(url).strip() in ("", "N/A"):
        return None
    return re.split(r"[?#]", str(url).strip())[0]


def id_desde_url(portal: str, url: str | None) -> str | None:
    """ID estable: último número largo de la URL; si no hay, hash corto de la URL."""
    if not url:
        return None
    numeros = re.findall(r"\d{6,}", url)
    base = numeros[-1] if numeros else hashlib.md5(url.encode()).hexdigest()[:10]
    return f"{portal}-{base}"


def modalidad_desde_url(url: str | None) -> str | None:
    if not url:
        return None
    u = url.lower()
    alq, ven = "alquiler" in u, "venta" in u
    if alq and not ven:
        return "alquiler"
    if ven and not alq:
        return "venta"
    return None


class Adaptador(ABC):
    portal: str = ""

    def __init__(self, modalidad_esperada: str, fecha_captura: str | None = None):
        self.modalidad_esperada = modalidad_esperada
        self.fecha_captura = fecha_captura

    def leer(self, ruta: str | Path) -> pd.DataFrame:
        return pd.read_csv(ruta, encoding="utf-8-sig", dtype=str, keep_default_na=False, na_values=[""])

    @abstractmethod
    def a_esquema(self, crudo: pd.DataFrame) -> pd.DataFrame:
        """Convierte el CSV crudo del portal al ESQUEMA común (sin limpiar texto)."""

    def _finalizar(self, df: pd.DataFrame) -> pd.DataFrame:
        df["portal"] = self.portal
        df["url"] = df["url"].map(limpiar_url)
        df["id_anuncio"] = [id_desde_url(self.portal, u) for u in df["url"]]
        df["modalidad_url"] = df["url"].map(modalidad_desde_url)
        df["modalidad_esperada"] = self.modalidad_esperada
        if "fecha_captura" not in df or df["fecha_captura"].isna().all():
            df["fecha_captura"] = self.fecha_captura
        for c in ESQUEMA:
            if c not in df:
                df[c] = None
        return df[ESQUEMA]
