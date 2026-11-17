
"""Clasificacion de anuncios segun la temporalidad del alquiler."""
from __future__ import annotations

import re
import unicodedata


def _normalizar(texto: str) -> str:
    """Convierte el texto a minusculas y elimina tildes."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)

    return "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )


# Evidencia de una tarifa mensual explicita.
# Reconoce tanto el marcador <MONTO> como importes numericos.
PATRON_TARIFA_MENSUAL = re.compile(
    r"(?:"
    r"(?:renta|precio|alquiler)\s*(?:mensual|por mes)"
    r"|"
    r"(?:precio\s+)?alquiler\s+(?:x|por)\s+mes"
    r"|"
    r"(?:<monto>|\d[\d.,]*)\s*(?:soles|dolares)\s+mensuales"
    r"|"
    r"(?:s/\s*\.?|us\$|usd|\$)?\s*"
    r"(?:<monto>|\d[\d.,]*)\s*(?:mensual(?:es)?|al mes)"
    r"|"
    r"(?:renta|precio de alquiler)\s*(?:es\s*)?(?:de\s*)?"
    r"(?:s/\s*\.?|us\$|usd|\$)?\s*"
    r"(?:<monto>|\d[\d.,]*)\s*(?:mensual(?:es)?|al mes)"
    r")",
    re.IGNORECASE,
)


# Evidencia de una oferta de alquiler anual.
PATRON_ALQUILER_ANUAL = re.compile(
    r"(?:alquiler|alquilo|alquilar)\s+anual"
    r"|alquiler\s+por\s+un\s+ano"
    r"|contrato\s+minimo\s+de?\s*1\s+ano"
    r"|contrato\s+minimo\s+de?\s+un\s+ano"
    r"|alquiler\s+temporal\s+y\s+anual"
    r"|alquiler\s+anual\s+y\s+temporal"
    r"|temporal\s+y\s+alquiler\s+anual",
    re.IGNORECASE,
)


# Evidencia explicita de una modalidad temporal.
PATRON_TEMPORAL = re.compile(
    r"alquiler\s+(?:de\s+)?temporada"
    r"|alquiler\s+exclusivo\s+de\s+temporada"
    r"|alquilo\s+por\s+temporada"
    r"|precio\s+por\s+toda\s+la\s+temporada"
    r"|alquiler\s+por\s+toda\s+la\s+temporada"
    r"|alquiler\s+por\s+dias"
    r"|se\s+alquila\s+por\s+dias"
    r"|alquiler\s+minimo\s+\d+\s+dias"
    r"|minimo\s+\d+\s+dias"
    r"|por\s+\d+\s+semanas?"
    r"|anual\s+y\s+temporal"
    r"|temporal\s+y\s+anual"
    # Redes sociales: alquiler por noches / estadias (patrones acotados para no confundir
    # "cuarto de huespedes" o "reuniones de fin de semana" con alquiler temporal)
    r"|(?:s/\s*\.?|us\$|\$)?\s*\d[\d.,]*\s*(?:soles\s+|dolares\s+)?(?:por|x|la|/)\s*noche"
    r"|(?:tarifa|precio|desde)\s+(?:por|x)\s+noche"
    r"|por\s+noches?\b"
    r"|(?:hasta|capacidad(?:\s+(?:para|de))?|max(?:imo)?(?:\s+de)?)\s+\d+\s+huespedes"
    r"|alquil\w*\s+(?:solo\s+|solamente\s+)?(?:por|para)\s+(?:los\s+)?(?:fines?|fin)\s+de\s+semana"
    r"|(?:para|ideal)\s+(?:tu\s+)?(?:estadia|escapada)\s+(?:corta|de\s+fin\s+de\s+semana)"
    r"|(?<!no\s)(?:alquilo|se\s+alquila)\s+(?:habitacion(?:es)?\s+)?tipo\s+(?:airbnb|hospedaje)",
    re.IGNORECASE,
)


def clasificar_temporalidad(
    titulo: str | None,
    descripcion: str | None,
) -> dict:
    """
    Clasifica el anuncio como mensual, temporal o indeterminado.

    Reglas:
    1. Una tarifa mensual explicita prevalece sobre otras modalidades.
    2. Una oferta anual y temporal sin tarifa mensual queda indeterminada.
    3. Una oferta anual sin evidencia temporal se clasifica como mensual.
    4. Una modalidad temporal explicita se clasifica como temporal.
    5. Si no hay evidencia de temporalidad, se asume alquiler mensual.
    6. Si no existe texto, se clasifica como indeterminado.
    """

    partes = [
        str(valor)
        for valor in (titulo, descripcion)
        if valor is not None and str(valor).strip()
    ]

    texto_original = " ".join(partes)

    if not texto_original.strip():
        return {
            "tipo_alquiler": "indeterminado",
            "motivo_temporalidad": "sin_texto",
        }

    texto = _normalizar(texto_original)

    tarifa_mensual = bool(
        PATRON_TARIFA_MENSUAL.search(texto)
    )

    alquiler_anual = bool(
        PATRON_ALQUILER_ANUAL.search(texto)
    )

    evidencia_temporal = bool(
        PATRON_TEMPORAL.search(texto)
    )

    # Una tarifa mensual explicita permite conservar anuncios mixtos.
    if tarifa_mensual:
        return {
            "tipo_alquiler": "mensual",
            "motivo_temporalidad": "tarifa_mensual_identificada",
        }

    # Una oferta anual y temporal sin tarifa identificable requiere revision.
    if alquiler_anual and evidencia_temporal:
        return {
            "tipo_alquiler": "indeterminado",
            "motivo_temporalidad": "oferta_anual_y_temporal_sin_tarifa_mensual",
        }

    # Una oferta anual sin evidencia temporal se conserva.
    if alquiler_anual:
        return {
            "tipo_alquiler": "mensual",
            "motivo_temporalidad": "oferta_anual",
        }

    # Se clasifica como temporal cuando existe evidencia explicita.
    if evidencia_temporal:
        return {
            "tipo_alquiler": "temporal",
            "motivo_temporalidad": "modalidad_temporal_explicita",
        }

    # Criterio por defecto: se asume alquiler mensual.
    return {
        "tipo_alquiler": "mensual",
        "motivo_temporalidad": "mensual_por_defecto",
    }
