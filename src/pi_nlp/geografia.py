"""Normalización de distrito desde el texto de ubicación y clasificación del ámbito geográfico."""
from __future__ import annotations

import re

from .config import distritos
from .texto import normalizar

# Ámbitos: lima_metropolitana | callao | fuera | indeterminado


def _tokens_ubicacion(ubicacion: str) -> list[str]:
    return [normalizar(s).strip() for s in ubicacion.split(",") if s.strip()]


def clasificar_distrito(ubicacion: str | None, distrito_fuente: str | None = None) -> tuple[str | None, str]:
    """Devuelve (distrito_normalizado, ambito). Busca de derecha a izquierda en los segmentos
    de la ubicación, porque el distrito suele ir al final ('..., La Molina, Lima')."""
    d = distritos()
    lima = set(d["lima_metropolitana"])
    alias = d["alias"]
    callao = set(d["callao"])
    fuera = set(d["fuera_de_lima_metropolitana"])

    candidatos: list[str] = []
    if distrito_fuente:
        candidatos.append(normalizar(distrito_fuente).strip())
    if ubicacion:
        candidatos.extend(reversed(_tokens_ubicacion(ubicacion)))

    for c in candidatos:
        c = re.sub(r"\s+", " ", c)
        c = alias.get(c, c)
        if c in lima:
            return c, "lima_metropolitana"
        if c in callao:
            return c, "callao"
        if c in fuera:
            return c, "fuera"
    return None, "indeterminado"
