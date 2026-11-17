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
    return _leer("lexicon.yaml")


@lru_cache(maxsize=None)
def distritos() -> dict:
    return _leer("distritos.yaml")
