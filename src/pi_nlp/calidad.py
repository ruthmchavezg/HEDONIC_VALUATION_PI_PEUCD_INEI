"""Banderas de control de calidad y de fuga de información (no se elimina nada: se marca)."""
from __future__ import annotations

import re

import pandas as pd

from .texto import normalizar

RE_VENTA = re.compile(r"\b(?:en venta|se vende|vendo|venta de|precio de venta)\b")
# Alquiler de temporada: tarifa por día/semana/quincena (no es renta mensual, no es comparable)
RE_TEMPORADA = re.compile(r"\b(?:quincena|por noche|por dia|alquiler de temporada|fds)\b|\b(?:dia|semana|noche)\s*[:\-]?\s*<monto")


def fuga_precio(montos: list[dict], pen: float | None, usd: float | None, tol: float) -> bool:
    """True si algún monto 'de renta' (no garantía ni mantenimiento) escrito en el texto coincide
    (±tol) con el precio publicado en soles o dólares: el texto revela la variable objetivo."""
    for m in montos:
        if m["tipo"] != "otro" or not m["valor"]:
            continue
        for ref, mon in ((pen, "PEN"), (usd, "USD")):
            if ref and m["moneda"] == mon and abs(m["valor"] - ref) / ref <= tol:
                return True
    return False


def banderas(fila: dict, cfg: dict) -> dict:
    """Calcula las banderas de una fila ya procesada."""
    out: dict = {}
    pen, usd = fila.get("precio_pen_pub"), fila.get("precio_usd_pub")
    lo, hi = cfg["ratio_pen_usd"]
    out["flag_ratio_moneda"] = bool(pen and usd and not (lo <= pen / usd <= hi))
    out["flag_sin_precio"] = not (pen or usd)

    areas = [fila.get(k) for k in ("area_titulo_m2", "area_terreno_m2", "area_construida_m2", "area_total_m2")]
    out["flag_area_atipica"] = any(a is not None and (a <= 0 or a > cfg["area_max_m2"]) for a in areas)

    out["flag_texto_corto"] = len(fila.get("descripcion_anon") or "") < cfg["texto_min_chars"]
    out["flag_contradiccion"] = bool(
        fila.get("dormitorios_conflicto") or fila.get("banos_conflicto") or fila.get("estacionamientos_conflicto")
    )
    desc = normalizar(fila.get("descripcion_anon"))
    out["flag_modalidad_mixta"] = bool(RE_VENTA.search(desc))
    out["flag_alquiler_temporada"] = bool(RE_TEMPORADA.search(desc))
    permitidos = ("lima_metropolitana", "callao") if cfg.get("incluir_callao") else ("lima_metropolitana",)
    out["flag_ambito"] = fila.get("ambito") not in permitidos
    return out


def reporte_cobertura(df: pd.DataFrame, columnas: list[str]) -> dict[str, float]:
    """Porcentaje de filas con valor no nulo por columna (insumo del contrato de datos)."""
    n = max(len(df), 1)
    return {c: round(float(df[c].notna().sum()) / n * 100, 1) for c in columnas if c in df.columns}
