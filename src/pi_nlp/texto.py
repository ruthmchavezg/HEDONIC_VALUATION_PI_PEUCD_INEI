"""Utilidades de limpieza y normalización de texto en español peruano."""
from __future__ import annotations

import html
import re
import unicodedata

VACIOS = {"", "no especificado", "nan", "none", "null", "n/a"}


def es_vacio(valor) -> bool:
    """True si el valor es nulo o un marcador de vacío ('No especificado', 'nan', ...)."""
    if valor is None:
        return True
    if isinstance(valor, float) and valor != valor:  # NaN
        return True
    return str(valor).strip().lower() in VACIOS


def limpiar_texto(valor) -> str | None:
    """Limpieza que conserva el sentido del texto: entidades HTML (M&sup2; -> M²), espacios,
    saltos de línea (-> ' | ') y caracteres invisibles. Devuelve None si el texto está vacío."""
    if es_vacio(valor):
        return None
    t = html.unescape(str(valor))
    t = unicodedata.normalize("NFC", t)
    t = t.replace(" ", " ").replace("​", "").replace("﻿", "")
    t = re.sub(r"\s*[\r\n]+\s*", " | ", t)
    t = re.sub(r"[ \t]+", " ", t).strip()
    return t or None


def normalizar(texto: str | None) -> str:
    """Minúsculas y sin tildes (ñ -> n, ² -> 2) para comparar con reglas y lexicón."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower()


def parse_numero(s: str) -> float | None:
    """Convierte '1,045' / '1.045' / '120,5' / '1,045.50' a float. None si no se puede."""
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        return float(re.sub(r"[.,]", "", s))
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d+", s):
        return float(s.replace(",", ""))
    m = re.fullmatch(r"(\d+)[.,](\d{1,2})", s)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    if re.fullmatch(r"\d+", s):
        return float(s)
    return None
