
"""Atributos no estructurados por lexicón con manejo de negación.

Un atributo vale 1 si algún término aparece afirmado.
Se consideran negaciones anteriores y posteriores al atributo,
con excepciones para expresiones como "no solo".
"""
from __future__ import annotations

import re

from .config import lexicon
from .texto import normalizar




def _negado(
    tokens: list[str],
    pos: int,
    longitud: int,
    negadores: set[str],
    ventana: int,
) -> bool:
    """Determina si un término aparece negado en su contexto."""

    previos = tokens[max(0, pos - ventana):pos]

    # Una afirmación introducida por "y con" rompe
    # la propagación de una negación anterior.
    for i in range(len(previos) - 1):
        if previos[i] == "y" and previos[i + 1] == "con":
            previos = previos[i + 2:]
            break

    # Excepciones y conectores afirmativos.
    for i, token in enumerate(previos):
        if token in {"pero", "sino", "aunque"}:
            previos = previos[i + 1:]

    # "No solo" no niega el atributo.
    for i, token in enumerate(previos):
        if token == "no":
            if i + 1 < len(previos) and previos[i + 1] == "solo":
                continue
            return True

        if token in negadores:
            return True

    # Negación posterior: "piscina no disponible".
    posteriores = tokens[pos + longitud:pos + longitud + 4]

    estados_negados = {
        "disponible",
        "incluido",
        "incluida",
        "incluidos",
        "incluidas",
    }

    for i, token in enumerate(posteriores):
        if token == "no":
            siguientes = posteriores[i + 1:i + 4]
            if any(p in estados_negados for p in siguientes):
                return True

    return False




def extraer_atributos(texto: str | None) -> dict[str, int]:
    """Devuelve {'attr_<nombre>': 0/1} para todos los atributos."""

    lex = lexicon()
    negadores = set(lex["negadores"])
    ventana = lex["ventana_negacion"]

    clausulas = [
        re.findall(r"[a-z0-9]+", c)
        for c in re.split(r"[,.;:|()\n]", normalizar(texto))
    ]
    clausulas = [c for c in clausulas if c]

    out: dict[str, int] = {}

    for nombre, terminos in lex["atributos"].items():
        afirmado = False

        for term in terminos:
            term_tokens = re.findall(r"[a-z0-9]+", normalizar(term))

            if not term_tokens:
                continue

            n = len(term_tokens)

            for tokens in clausulas:
                for i in range(len(tokens) - n + 1):
                    if tokens[i:i + n] != term_tokens:
                        continue

                    if not _negado(
                        tokens, i, n, negadores, ventana
                    ):
                        afirmado = True
                        break

                if afirmado:
                    break

            if afirmado:
                break

        out[f"attr_{nombre}"] = int(afirmado)

    return out
