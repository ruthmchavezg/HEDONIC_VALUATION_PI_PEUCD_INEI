"""Atributos no estructurados por lexicón con manejo de negación.

Un atributo vale 1 solo si algún término aparece AFIRMADO. Si todos los términos hallados están
negados (p. ej. "sin piscina", "no se aceptan mascotas") el atributo vale 0. Reglas simples y
explicables; no sustituyen a un modelo si la muestra anotada muestra que las reglas no alcanzan.
"""
from __future__ import annotations

import re

from .config import lexicon
from .texto import normalizar


def _negado(tokens: list[str], pos: int, negadores: set[str], ventana: int) -> bool:
    previos = tokens[max(0, pos - ventana): pos]
    return any(t in negadores for t in previos)


def extraer_atributos(texto: str | None) -> dict[str, int]:
    """Devuelve {'attr_<nombre>': 0/1} para todos los atributos del lexicón.
    La negación se evalúa dentro de cada cláusula (separada por , . ; : | ( ) ), nunca a través de ellas."""
    lex = lexicon()
    negadores = set(lex["negadores"])
    ventana = lex["ventana_negacion"]
    clausulas = [re.findall(r"[a-z0-9]+", c) for c in re.split(r"[,.;:|()\n]", normalizar(texto))]
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
                    if tokens[i: i + n] == term_tokens and not _negado(tokens, i, negadores, ventana):
                        afirmado = True
                        break
                if afirmado:
                    break
            if afirmado:
                break
        out[f"attr_{nombre}"] = int(afirmado)
    return out
