"""Lectura del precio publicado (renta mensual) desde el texto del portal.

Formato típico: 'alquiler | S/ 8,330 | · | USD 2,450 | 9% | Avisarme si baja de precio'.
Se toma el primer monto en soles y el primero en dólares, ignorando montos precedidos por
'mantenimiento'. No se convierte moneda aquí: la conversión con tipo de cambio BCRP es decisión de modelamiento.
"""
from __future__ import annotations

import re

from .texto import normalizar, parse_numero

RE_PEN = re.compile(r"S/\.?\s*(\d[\d.,]*)")
RE_USD = re.compile(r"(?:US\$|USD|\$)\s*(\d[\d.,]*)")


def _primer_monto(regex: re.Pattern, texto: str) -> float | None:
    for m in regex.finditer(texto):
        previo = normalizar(re.split(r"[|·.;]", texto[: m.start()])[-1][-25:])
        if "mantenim" in previo or "garant" in previo:
            continue
        v = parse_numero(m.group(1).rstrip(".,"))
        if v:
            return v
    return None


def parsear_precio(precio_texto: str | None) -> dict:
    if not precio_texto:
        return {"precio_pen_pub": None, "precio_usd_pub": None, "moneda_pub": None}
    pen = _primer_monto(RE_PEN, precio_texto)
    usd = _primer_monto(RE_USD, precio_texto)
    if pen and usd:
        moneda = "PEN+USD"
    elif pen:
        moneda = "PEN"
    elif usd:
        moneda = "USD"
    else:
        moneda = None
    return {"precio_pen_pub": pen, "precio_usd_pub": usd, "moneda_pub": moneda}


def asignar_precio_desde_montos(montos: list[dict]) -> dict:
    """
    Asigna precios de alquiler desde los montos detectados y clasificados
    por anonimizar(). Solo considera montos de tipo 'alquiler'.

    Si hay varios candidatos en una misma moneda, no asigna un precio
    y marca la ambigüedad.
    """
    candidatos_pen = [
        m["valor"]
        for m in montos
        if m.get("tipo") == "alquiler"
        and m.get("moneda") == "PEN"
        and m.get("valor") is not None
        and m["valor"] > 0
    ]

    candidatos_usd = [
        m["valor"]
        for m in montos
        if m.get("tipo") == "alquiler"
        and m.get("moneda") == "USD"
        and m.get("valor") is not None
        and m["valor"] > 0
    ]

    ambiguo_pen = len(candidatos_pen) > 1
    ambiguo_usd = len(candidatos_usd) > 1

    pen = candidatos_pen[0] if len(candidatos_pen) == 1 else None
    usd = candidatos_usd[0] if len(candidatos_usd) == 1 else None

    if pen is not None and usd is not None:
        moneda = "PEN+USD"
    elif pen is not None:
        moneda = "PEN"
    elif usd is not None:
        moneda = "USD"
    else:
        moneda = None

    return {
        "precio_pen_pub": pen,
        "precio_usd_pub": usd,
        "moneda_pub": moneda,
        "flag_precio_ambiguo": ambiguo_pen or ambiguo_usd,
    }
