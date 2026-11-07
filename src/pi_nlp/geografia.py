
"""Normalización de distrito desde el texto de ubicación y clasificación del ámbito geográfico."""
from __future__ import annotations

import re

from .config import distritos
from .texto import normalizar


def _tokens_ubicacion(ubicacion: str) -> list[str]:
    """Divide la ubicación en segmentos separados por comas."""
    return [
        normalizar(segmento).strip()
        for segmento in ubicacion.split(",")
        if segmento.strip()
    ]


def _buscar_coincidencias(
    texto: str,
    nombres: set[str],
    alias: dict[str, str],
) -> set[str]:
    """Busca nombres de distritos completos dentro de un texto."""
    encontrados = set()

    for nombre in nombres:
        expresion = rf"(?<!\w){re.escape(nombre)}(?!\w)"

        if re.search(expresion, texto):
            encontrados.add(alias.get(nombre, nombre))

    return encontrados


def _clasificar_nombre(
    distrito: str,
    lima: set[str],
    callao: set[str],
    fuera: set[str],
) -> tuple[str | None, str]:
    """Determina el ámbito geográfico y agrupa el Callao."""

    if distrito in lima:
        return distrito, "lima_metropolitana"

    if distrito in callao:
        return "callao", "callao"

    if distrito in fuera:
        return distrito, "fuera"

    return None, "indeterminado"

def clasificar_distrito(
    ubicacion: str | None,
    distrito_fuente: str | None = None,
) -> tuple[str | None, str]:
    """
    Devuelve (distrito_normalizado, ambito).

    Prioriza el distrito proporcionado directamente por la fuente.
    Luego busca en los segmentos de ubicación de derecha a izquierda.

    Si encuentra más de un distrito dentro del mismo segmento,
    devuelve una clasificación indeterminada.

    Cuando Callao aparece como referencia provincial, prioriza
    un distrito específico del Callao mencionado anteriormente.
    """
    config = distritos()

    lima = set(config["lima_metropolitana"])
    alias = config["alias"]
    callao = set(config["callao"])
    fuera = set(config["fuera_de_lima_metropolitana"])

    nombres_validos = lima | callao | fuera | set(alias)

    # 1. Priorizar el distrito proporcionado directamente por la fuente.
    if distrito_fuente:
        texto_fuente = normalizar(distrito_fuente).strip()
        texto_fuente = re.sub(r"\s+", " ", texto_fuente)

        coincidencias = _buscar_coincidencias(
            texto_fuente,
            nombres_validos,
            alias,
        )

        if len(coincidencias) == 1:
            distrito = coincidencias.pop()
            return _clasificar_nombre(distrito, lima, callao, fuera)

        if len(coincidencias) > 1:
            return None, "indeterminado"

    # 2. Buscar en la ubicación, desde el último segmento hacia el primero.
    if ubicacion:
        texto_ubicacion = normalizar(ubicacion)

        # Excepción: Huarochirí forma parte del nombre de la carretera,
        # mientras que Cieneguilla identifica el distrito.
        if (
            re.search(r"\bcarretera\s+a\s+huarochiri\b", texto_ubicacion)
            and re.search(r"\bcieneguilla\b", texto_ubicacion)
        ):
            return _clasificar_nombre(
                "cieneguilla", lima, callao, fuera
            )

        segmentos = _tokens_ubicacion(ubicacion)
        for indice in range(len(segmentos) - 1, -1, -1):
            segmento = re.sub(r"\s+", " ", segmentos[indice])

            # Primero comprobar coincidencia exacta del segmento.
            candidato = alias.get(segmento, segmento)

            if candidato == "callao":
                # Callao puede referirse a la provincia.
                # Revisar si hay un distrito específico en segmentos anteriores.
                segmentos_anteriores = segmentos[:indice]

                coincidencias_callao = set()

                for anterior in segmentos_anteriores:
                    coincidencias_callao.update(
                        _buscar_coincidencias(
                            anterior,
                            callao - {"callao"},
                            alias,
                        )
                    )

                if len(coincidencias_callao) == 1:
                    distrito = coincidencias_callao.pop()
                    return _clasificar_nombre(
                        distrito, lima, callao, fuera
                    )

                if len(coincidencias_callao) > 1:
                    return None, "indeterminado"

                return "callao", "callao"

            if candidato in lima | callao | fuera:
                return _clasificar_nombre(
                    candidato, lima, callao, fuera
                )

            # Si no hay coincidencia exacta, buscar dentro del segmento.
            coincidencias = _buscar_coincidencias(
                segmento,
                nombres_validos,
                alias,
            )

            if len(coincidencias) == 1:
                distrito = coincidencias.pop()
                return _clasificar_nombre(
                    distrito, lima, callao, fuera
                )

            if len(coincidencias) > 1:
                return None, "indeterminado"

    return None, "indeterminado"
