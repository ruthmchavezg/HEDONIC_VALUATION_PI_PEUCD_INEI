"""Adaptador de Adondevivir para transformar los datos del portal al esquema común."""
from __future__ import annotations

import pandas as pd

from ..texto import es_vacio
from .base import Adaptador, parsear_coordenadas


def _unir(*valores) -> str | None:
    """Une textos no vacíos y distintos, conservando el contenido original."""
    vistos: list[str] = []

    for v in valores:
        if not es_vacio(v):
            texto = str(v).strip()
            if texto not in vistos:
                vistos.append(texto)

    return " | ".join(vistos) or None


def _datos_principales(valor):
    """Reescribe 'tot.: 200 m² | baños: 7 | dorm.: 1 | antigüedad: 20' al formato que
    entiende extraccion.py ('200 m² tot. | 7 baños | 1 dorm. | 20 años de antigüedad')."""
    if es_vacio(valor):
        return valor
    partes = []
    for p in str(valor).split("|"):
        if ":" not in p:
            partes.append(p.strip())
            continue
        etiqueta, _, dato = p.partition(":")
        e, d = etiqueta.strip().lower(), dato.strip()
        if e == "tot.":
            partes.append(f"{d} tot.")
        elif e == "cub.":
            partes.append(f"{d} cub.")
        elif e in ("baño", "baños"):
            partes.append(f"{d} {e}")
        elif e == "dorm.":
            partes.append(f"{d} dorm.")
        elif e == "estac.":
            partes.append(f"{d} estac.")
        elif e == "antigüedad":
            partes.append(f"{d} años de antigüedad")
        else:  # 'medio baño: 1', etc.: se conserva tal cual
            partes.append(p.strip())
    return " | ".join(partes)


class AdaptadorAdondeVivir(Adaptador):
    portal = "adondevivir"

    def a_esquema(self, crudo: pd.DataFrame) -> pd.DataFrame:
        df = pd.DataFrame(index=crudo.index)

        # Identificación y datos principales
        df["url"] = crudo["url"]
        df["titulo"] = crudo.get("titulo")
        df["descripcion"] = crudo.get("descripcion")
        df["precio_texto"] = crudo.get("precio_general")
        df["ubicacion_texto"] = crudo.get("ubicacion")

        # Consolidación de características disponibles
        columnas_caracteristicas = [
            "datos_principales_generales",
            "caracteristicas_generales",
            "servicios",
            "ambientes",
            "exteriores",
            "otros_apartados",
            # nombres del formato anterior del CSV (si no existen, se ignoran)
            "comodidades_proyecto",
            "otras_caracteristicas",
            "unidades_detalladas",
            "caracteristicas_dinamicas",
            "estado_proyecto",
        ]

        columnas_disponibles = [
            crudo[col] if col in crudo.columns
            else pd.Series(None, index=crudo.index)
            for col in columnas_caracteristicas
        ]

        df["caracteristicas_texto"] = [
            _unir(_datos_principales(valores[0]), *valores[1:])
            for valores in zip(*columnas_disponibles)
        ]

        # Texto complementario del anuncio
        df["texto_tarjeta"] = [
            _unir(titulo, precio, ubicacion)
            for titulo, precio, ubicacion in zip(
                df["titulo"],
                df["precio_texto"],
                df["ubicacion_texto"],
            )
        ]

        # Coordenadas ("lat, lon") y su precisión (EXACT / ZONE / NONE)
        coords = [
            parsear_coordenadas(v)
            for v in crudo.get("coordenadas_geograficas", pd.Series(None, index=crudo.index))
        ]
        df["latitud"] = [c[0] for c in coords]
        df["longitud"] = [c[1] for c in coords]
        df["precision_coord"] = [
            (p if not es_vacio(p) else "DESCONOCIDA") if c[0] is not None else None
            for p, c in zip(
                crudo.get("precision_ubicacion", pd.Series(None, index=crudo.index)),
                coords,
            )
        ]

        # Fecha real de captura
        df["fecha_captura"] = (
            crudo["fecha_scrapeo"]
            if "fecha_scrapeo" in crudo.columns
            else crudo.get("fecha_captura")
        )

        resultado = self._finalizar(df)

        # Tipo de inmueble informado por el portal (Departamento / Casa / Habitación)
        resultado["tipo_inmueble_fuente"] = crudo.get("tipo_inmueble")

        return resultado