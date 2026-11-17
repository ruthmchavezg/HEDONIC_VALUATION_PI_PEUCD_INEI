
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
        "permitido",
        "permitida",
        "permitidos",
        "permitidas",
        "aceptan",
        "aceptadas",
        "aceptados",
        "permiten",
        "admiten",
    }

    for i, token in enumerate(posteriores):
        if token == "no":
            siguientes = posteriores[i + 1:i + 4]
            if any(p in estados_negados for p in siguientes):
                return True

    return False




# "Permite mascotas: No"  ->  "sin permite mascotas"  (campos tipo etiqueta de los portales)
RE_ETIQUETA_NO = re.compile(
    r"([a-z0-9][a-z0-9 /\-]{2,40}?)\s*:\s*(?:no|n/a|ninguno|ninguna)\s*(?=[|,;.\n]|$)"
)


def _igual(token: str, termino: str) -> bool:
    """Igualdad de palabras tolerando plural simple (terraza/terrazas, ascensor/ascensores)."""
    if token == termino:
        return True
    if len(termino) < 4:
        return False
    return token in (termino + "s", termino + "es") or termino in (token + "s", token + "es")


def _longitud_coincidencia(tokens: list[str], inicio: int, patron: list[str]) -> int | None:
    """Palabras del texto que consume `patron` desde `inicio`, o None. "*" admite 0 a 2 palabras."""

    def rec(pi: int, ti: int) -> int | None:
        if pi == len(patron):
            return ti - inicio
        if patron[pi] == "*":
            for k in range(3):
                if ti + k <= len(tokens):
                    r = rec(pi + 1, ti + k)
                    if r is not None:
                        return r
            return None
        if ti < len(tokens) and _igual(tokens[ti], patron[pi]):
            return rec(pi + 1, ti + 1)
        return None

    return rec(0, inicio)


def _tokens_termino(term: str) -> list[str]:
    return re.findall(r"[a-z0-9*]+", normalizar(term).replace("*", " * "))


def extraer_atributos(texto: str | None) -> dict[str, int]:
    """Devuelve {'attr_<nombre>': 0/1} para todos los atributos."""

    lex = lexicon()
    negadores = set(lex["negadores"])
    ventana = lex["ventana_negacion"]
    exclusiones = lex.get("exclusiones") or {}

    t_norm = RE_ETIQUETA_NO.sub(r"sin \1 ", normalizar(texto))

    clausulas = [
        re.findall(r"[a-z0-9]+", c)
        for c in re.split(r"[,.;:|()\n]", t_norm)
    ]
    clausulas = [c for c in clausulas if c]

    out: dict[str, int] = {}

    for nombre, terminos in lex["atributos"].items():
        patrones = [p for p in (_tokens_termino(x) for x in terminos) if p and p[0] != "*" and p[-1] != "*"]
        excl = [p for p in (_tokens_termino(x) for x in exclusiones.get(nombre, [])) if p]
        afirmado = False

        for tokens in clausulas:
            # tramos del texto que anulan una coincidencia (ej. "jardin de infancia")
            tramos_excl = []
            for pe in excl:
                for i in range(len(tokens)):
                    n = _longitud_coincidencia(tokens, i, pe)
                    if n:
                        tramos_excl.append((i, i + n))

            for patron in patrones:
                for i in range(len(tokens)):
                    n = _longitud_coincidencia(tokens, i, patron)

                    if not n:
                        continue

                    if any(a <= i and i + n <= b or i < b and a < i + n for a, b in tramos_excl):
                        continue

                    if not _negado(tokens, i, n, negadores, ventana):
                        afirmado = True
                        break

                if afirmado:
                    break

            if afirmado:
                break

        out[f"attr_{nombre}"] = int(afirmado)

    return out
