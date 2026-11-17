"""CLI:  python -m pi_nlp run --input urbania:alquiler=ruta.csv [--input adondevivir:alquiler=ruta2.csv]"""
from __future__ import annotations

import argparse
from pathlib import Path

from .adaptadores import ADAPTADORES
from .config import settings
from .pipeline import Entrada, ejecutar


def _parsear_entrada(spec: str, defecto: str) -> Entrada:
    """Formato: fuente[:modalidad]=ruta   (ej.: urbania:alquiler=data/raw/urbania.csv)"""
    izq, _, ruta = spec.partition("=")
    fuente, _, modalidad = izq.partition(":")
    if fuente not in ADAPTADORES:
        raise SystemExit(f"Fuente desconocida '{fuente}'. Disponibles: {', '.join(ADAPTADORES)}")
    return Entrada(fuente, Path(ruta), modalidad or defecto)


def main() -> None:
    p = argparse.ArgumentParser(prog="pi_nlp", description="Pipeline NLP del Proyecto Integrador")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Ejecuta el pipeline completo")
    r.add_argument("--input", action="append", required=True, metavar="FUENTE[:MODALIDAD]=RUTA")
    r.add_argument("--out", default="data/processed", help="Carpeta de salida")
    r.add_argument("--fecha-captura", default=None, help="YYYY-MM-DD si el CSV no trae fecha_captura")
    r.add_argument("--modalidad-objetivo", default=None, help="Por defecto, la de config/settings.yaml")
    a = p.parse_args()
    objetivo = a.modalidad_objetivo or settings()["modalidad_objetivo"]
    entradas = [_parsear_entrada(s, objetivo) for s in a.input]
    ejecutar(entradas, Path(a.out), a.fecha_captura, a.modalidad_objetivo)


if __name__ == "__main__":
    main()
