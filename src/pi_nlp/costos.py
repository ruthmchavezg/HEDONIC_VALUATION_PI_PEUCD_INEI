"""Mantenimiento del inmueble (cuota mensual de edificio/condominio) desde campos y texto libre.

Se busca, por orden de confianza:
  1. un campo estructurado del portal ("S/ 80", "USD 50", "Mantenimiento: S/1400");
  2. el texto del anuncio: "mantenimiento S/ 150", "mantenimiento aprox.: 220 soles", "gastos comunes $50",
     "S/ 180 de mantenimiento", "mantenimiento y arbitrios aparte: 450 soles", etc.

Tambien se marca si el mantenimiento esta INCLUIDO en el precio ("incluye mantenimiento"), porque eso
cambia como se interpreta el precio publicado.
No se confunde con garantias ni con "2x1" / "2 meses": el monto debe tener moneda o estar entre 20 y 8000.
"""
from __future__ import annotations

import re

from .texto import normalizar, parse_numero

_MON = r"(?:s\s*/\s*\.?|us\s*\$|usd|\$|soles|sol|nuevos\s+soles|dolares)"
_MONTO = r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
_KW = r"(?:cuota\s+de\s+mantenimiento|gastos?\s+de\s+mantenimiento|mantenimiento|mantto\.?|mant\.|gastos?\s+comunes)"
_RELLENO = (
    r"(?:\s*(?:mensual(?:es)?|variable|fijo|aprox(?:imado|imadamente)?\.?|aproximad[oa]|estimado|total|"
    r"del\s+edificio|de\s+edificio|y\s+arbitrios|aparte|adicional|extra|es\s+de|es|de|son|cuesta|costo|"
    r"ronda|alrededor\s+de|desde|:|-|=|\+|\.|,|a))*"
)
_NO_MONTO = r"(?!\s*(?:x\b|meses|mes\b|%|m2|anos?\b|dias|dormitorios?|baños|banos|soles\s+de\s+garantia))"

RE_MANT_A = re.compile(
    rf"{_KW}{_RELLENO}\s*(?P<mon>{_MON})?\s*{_MONTO}{_NO_MONTO}\s*(?P<mon2>soles|sol|dolares|usd|us\$|\$)?"
)
RE_MANT_B = re.compile(
    rf"(?P<mon>{_MON})?\s*{_MONTO}\s*(?P<mon2>soles|sol|dolares|usd)?\s*(?:mensuales?\s*)?"
    rf"(?:de|por|en|para|x|mas)?\s*(?:de\s+)?(?:cuota\s+de\s+)?(?:gastos?\s+de\s+)?mantenimiento\b"
)
RE_ESTRUCTURADO = re.compile(rf"(?P<mon>{_MON})?\s*{_MONTO}\s*(?P<mon2>soles|sol|dolares|usd)?")
RE_MANT_INCLUIDO = re.compile(
    r"mantenimiento\s+(?:ya\s+)?(?:esta\s+)?incluid[oa]|incluye\s+(?:el\s+)?(?:pago\s+de\s+)?mantenimiento"
    r"|incluid[oa]s?\s+(?:el\s+)?mantenimiento|incluid[oa]s?\s+(?:los\s+)?gastos\s+comunes"
    r"|incluye\s+(?:los\s+)?gastos\s+comunes|(?:sin|no\s+paga(?:s)?)\s+(?:cuota\s+de\s+)?mantenimiento"
)


def _moneda(mon: str | None, mon2: str | None) -> str:
    marca = " ".join(x for x in (mon, mon2) if x).replace(" ", "")
    return "USD" if any(k in marca for k in ("$", "usd", "dolar")) and "s/" not in marca else "PEN"


def _valido(valor: float | None, moneda: str, estructurado: bool, con_moneda: bool) -> bool:
    if valor is None:
        return False
    tope = 3000 if moneda == "USD" else 8000
    if estructurado:
        # En campos estructurados aparecen marcadores tipo "S/ 1" o "S/ 10": no son un monto real.
        # 0 si se acepta (significa "sin mantenimiento").
        return valor == 0 or (5 if moneda == "USD" else 20) <= valor <= tope
    piso = 5 if con_moneda else 20
    return piso <= valor <= tope


def _de_estructurado(texto: str | None) -> tuple[float, str] | None:
    if not texto or not str(texto).strip():
        return None
    m = RE_ESTRUCTURADO.search(normalizar(str(texto)))
    if not m:
        return None
    valor = parse_numero(m.group(2).rstrip(".,"))
    moneda = _moneda(m.group("mon"), m.group("mon2"))
    return (valor, moneda) if _valido(valor, moneda, True, True) else None


def _de_texto(texto: str) -> tuple[float, str] | None:
    for regex in (RE_MANT_A, RE_MANT_B):
        for m in regex.finditer(texto):
            valor = parse_numero(m.group(2).rstrip(".,"))
            moneda = _moneda(m.group("mon"), m.group("mon2"))
            if _valido(valor, moneda, False, bool(m.group("mon") or m.group("mon2"))):
                return valor, moneda
    return None


def extraer_mantenimiento(textos: list[str | None], estructurado: str | None = None) -> dict:
    """{mantenimiento_pen, mantenimiento_usd, mantenimiento_fuente, mantenimiento_incluido}."""
    out = {
        "mantenimiento_pen": None,
        "mantenimiento_usd": None,
        "mantenimiento_fuente": None,
        "mantenimiento_incluido": False,
    }

    hallado = _de_estructurado(estructurado)
    fuente = "estructurado" if hallado else None

    unido = " | ".join(normalizar(t) for t in textos if t)

    if hallado is None and unido:
        hallado = _de_texto(unido)
        fuente = "texto" if hallado else None

    if hallado:
        valor, moneda = hallado
        out["mantenimiento_pen" if moneda == "PEN" else "mantenimiento_usd"] = valor
        out["mantenimiento_fuente"] = fuente

    out["mantenimiento_incluido"] = bool(unido and RE_MANT_INCLUIDO.search(unido))
    return out
