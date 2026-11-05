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
