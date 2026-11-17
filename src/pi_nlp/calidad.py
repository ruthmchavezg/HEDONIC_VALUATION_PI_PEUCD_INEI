
"""Banderas de control de calidad y de fuga de información (no se elimina nada: se marca)."""
from __future__ import annotations

import re

import pandas as pd

from .texto import normalizar

RE_VENTA = re.compile(
    r"\b(?:en venta|se vende|vendo|venta de|precio de venta|remato|traspaso)\b"
    r"|^\W*venta\s+(?:de\s+)?(?:casa|departamento|dpto|depa|terreno|local|oficina|lote|cuarto|habitacion|duplex)\b(?!.{0,200}\balquil)"
)

# Alquiler de temporada: tarifa por día/semana/quincena.
RE_TEMPORADA = re.compile(
    r"\b(?:quincena|por noche|por dia|alquiler de temporada|fds)\b"
    r"|\b(?:dia|semana|noche)\s*[:\-]?\s*<monto"
)



def _patron_numero(monto: dict) -> str | None:
    """Construye un patrón para localizar el importe original."""
    original = monto.get("texto_original", "")

    if original:
        numero = re.search(
            r"\d[\d.,]*(?:\s*(?:k|mil))?",
            original,
            re.I,
        )
        if numero:
            return re.escape(numero.group(0).strip())

    valor = monto.get("valor")

    if valor is None:
        return None

    valor_float = float(valor)

    if valor_float.is_integer():
        numero = str(int(valor_float))
        separador_miles = r"(?:,|\.|\s)?"
        return (
            r"\b"
            + re.escape(numero[0])
            + separador_miles
            + re.escape(numero[1:])
            + r"\b"
        )

    return re.escape(str(valor_float))



def fuga_precio(
    montos: list[dict],
    pen: float | None,
    usd: float | None,
    tol: float,
    textos_anonimizados: list[str | None],
) -> bool:
    """
    Detecta si un precio de alquiler publicado permanece expuesto
    en alguno de los textos anonimizados.

    Solo compara importes de la misma moneda.
    No considera garantía ni mantenimiento como precio de alquiler.
    """
    referencias = {
        "PEN": pen,
        "USD": usd,
    }

    patron_moneda = {
        "PEN": r"(?:S/\s*\.?|PEN|soles)",
        "USD": r"(?:US\$|USD|\$|d[oó]lares)",
    }

    textos = [
        texto
        for texto in textos_anonimizados
        if texto
    ]

    for monto in montos:
        if monto.get("tipo") != "alquiler":
            continue

        moneda = monto.get("moneda")
        valor = monto.get("valor")
        referencia = referencias.get(moneda)

        if (
            referencia is None
            or valor is None
            or valor <= 0
            or referencia <= 0
        ):
            continue

        if abs(valor - referencia) / referencia > tol:
            continue

        patron_numero = _patron_numero(monto)

        if patron_numero is None:
            continue

        moneda_regex = patron_moneda.get(moneda)

        if moneda_regex is None:
            continue

        patron = re.compile(
            rf"(?:{moneda_regex}\s*{patron_numero}"
            rf"|{patron_numero}\s*{moneda_regex})",
            re.I,
        )

        for texto in textos:
            if patron.search(texto):
                return True

    return False


def banderas(fila: dict, cfg: dict) -> dict:
    """Calcula las banderas de una fila ya procesada."""
    out: dict = {}

    pen = fila.get("precio_pen_pub")
    usd = fila.get("precio_usd_pub")

    lo, hi = cfg["ratio_pen_usd"]

    out["flag_ratio_moneda"] = bool(
        pen and usd and not (lo <= pen / usd <= hi)
    )

    out["flag_sin_precio"] = not (pen or usd)

    out["flag_precio_ambiguo"] = bool(
        fila.get("flag_precio_ambiguo", False)
    )

    # Superficies declaradas en el anuncio.
    area_titulo = fila.get("area_titulo_m2")
    area_terreno = fila.get("area_terreno_m2")
    area_construida = fila.get("area_construida_m2")
    area_techada = fila.get("area_techada_m2")
    area_total = fila.get("area_total_m2")

    areas = [
        area_titulo,
        area_terreno,
        area_construida,
        area_techada,
        area_total,
    ]

    out["flag_area_atipica"] = any(
        a is not None
        and (a <= 0 or a > cfg["area_max_m2"])
        for a in areas
    )

    out["flag_area_sospechosamente_pequena"] = any(
        a is not None
        and 0 < a <= cfg["area_min_revision_m2"]
        for a in areas
    )

    # Auditoría de consistencia entre superficies declaradas.
    # Se marca, pero no se corrige ni elimina ningún valor.
    out["flag_area_construida_techada_igual"] = bool(
        area_construida is not None
        and area_techada is not None
        and area_construida == area_techada
    )

    out["flag_area_total_menor_techada"] = bool(
        area_total is not None
        and area_techada is not None
        and area_total < area_techada
    )

    out["flag_area_total_menor_terreno"] = bool(
        area_total is not None
        and area_terreno is not None
        and area_total < area_terreno
    )

    out["flag_area_total_menor_construida"] = bool(
        area_total is not None
        and area_construida is not None
        and area_total < area_construida
    )

    out["flag_texto_corto"] = (
        len(fila.get("descripcion_anon") or "")
        < cfg["texto_min_chars"]
    )

    out["flag_contradiccion"] = bool(
        fila.get("dormitorios_conflicto")
        or fila.get("banos_conflicto")
        or fila.get("estacionamientos_conflicto")
    )

    desc = normalizar(fila.get("descripcion_anon"))

    out["flag_modalidad_mixta"] = bool(
        RE_VENTA.search(desc)
    )

    out["flag_alquiler_temporada"] = bool(
        RE_TEMPORADA.search(desc)
    )

    permitidos = (
        ("lima_metropolitana", "callao")
        if cfg.get("incluir_callao")
        else ("lima_metropolitana",)
    )

    out["flag_ambito"] = fila.get("ambito") not in permitidos

    return out


def reporte_cobertura(
    df: pd.DataFrame,
    columnas: list[str],
) -> dict[str, float]:
    """Porcentaje de filas con valor no nulo por columna."""
    n = max(len(df), 1)

    return {
        c: round(float(df[c].notna().sum()) / n * 100, 1)
        for c in columnas
        if c in df.columns
    }
