"""Carga de configuración YAML (settings, lexicón y distritos)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
DIR_CONFIG = RAIZ / "config"


def _leer(nombre: str) -> dict:
    with open(DIR_CONFIG / nombre, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def settings() -> dict:
    return _leer("settings.yaml")


@lru_cache(maxsize=None)
def lexicon() -> dict:
    """lexicon.yaml + (opcional) lexicon_extra.yaml.

    lexicon_extra.yaml AMPLIA el lexicon: sus terminos se suman a los de lexicon.yaml (no los reemplaza),
    agrega atributos nuevos y, si existe la clave "exclusiones", frases que anulan una coincidencia
    (por ejemplo "jardin de infancia" no es un jardin).
    """
    base = _leer("lexicon.yaml")
    ruta_extra = DIR_CONFIG / "lexicon_extra.yaml"
    if not ruta_extra.exists():
        return base

    extra = _leer("lexicon_extra.yaml") or {}
    atributos = {k: list(v or []) for k, v in (base.get("atributos") or {}).items()}
    for nombre, terminos in (extra.get("atributos") or {}).items():
        actuales = atributos.setdefault(nombre, [])
        actuales.extend(t for t in (terminos or []) if t not in actuales)

    negadores = list(base.get("negadores") or [])
    negadores.extend(n for n in (extra.get("negadores") or []) if n not in negadores)

    return {**base, "atributos": atributos, "negadores": negadores,
            "exclusiones": extra.get("exclusiones") or {}}


@lru_cache(maxsize=None)
def distritos() -> dict:
    return _leer("distritos.yaml")
