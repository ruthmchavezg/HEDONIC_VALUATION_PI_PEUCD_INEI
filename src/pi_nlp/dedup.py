"""Detección de duplicados y casi duplicados dentro de una fuente o entre fuentes.

Criterio (explícito y medible): dos anuncios son duplicados si, en el mismo bloque
(distrito + tipo de inmueble), su similitud coseno TF-IDF de la descripción anonimizada es
>= ``umbral_texto`` Y sus áreas y precios (cuando ambos existen) difieren menos que las tolerancias.
Los umbrales son PROVISIONALES: se calibran con pares anotados a mano (N6) y se reporta
precisión/recall del criterio. Se marca, no se elimina.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from .logging_utils import get_logger

log = get_logger()


def _rel(a, b) -> float:
    return abs(a - b) / max(abs(a), abs(b))



def marcar_duplicados(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Identifica duplicados de forma conservadora.

    Solo compara anuncios con distrito y tipo de inmueble identificados.
    Exige similitud textual y al menos una variable cuantitativa comparable
    (área o precio) que cumpla su tolerancia.
    """
    df = df.reset_index(drop=True).copy()
    n = len(df)
    padre = list(range(n))

    def find(x: int) -> int:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    # Preparación de variables
    textos = df["descripcion_anon"].fillna("").astype(str)
    validos = textos.str.len() >= cfg["min_chars_texto"]

    distrito = df["distrito"].astype("string").str.strip()
    tipo = df["tipo_inmueble"].astype("string").str.strip()

    area = (
        df[["area_construida_m2", "area_total_m2", "area_titulo_m2"]]
        .apply(pd.to_numeric, errors="coerce")
        .bfill(axis=1)
        .iloc[:, 0]
    )
    precio = pd.to_numeric(df["precio_pen_pub"], errors="coerce")

    # Solo se comparan registros con distrito y tipo identificados.
    comparables = (
        validos
        & distrito.notna()
        & distrito.ne("")
        & tipo.notna()
        & tipo.ne("")
    )

    if comparables.sum() >= 2:
        X = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=1,
        ).fit_transform(textos)

        indices_validos = df.index[comparables]

        bloques = df.loc[indices_validos].groupby(
            [distrito.loc[indices_validos], tipo.loc[indices_validos]]
        ).indices

        for idx in bloques.values():
            idx = list(idx)

            if len(idx) < 2:
                continue

            S = (X[idx] @ X[idx].T).tocoo()

            for a, b, similitud in zip(S.row, S.col, S.data):
                if a >= b or similitud < cfg["umbral_texto"]:
                    continue

                i, j = idx[a], idx[b]

                # Recopilar variables cuantitativas comparables.
                comparaciones = []

                if pd.notna(area.iloc[i]) and pd.notna(area.iloc[j]):
                    comparaciones.append(
                        _rel(area.iloc[i], area.iloc[j]) <= cfg["tol_area"]
                    )

                if pd.notna(precio.iloc[i]) and pd.notna(precio.iloc[j]):
                    comparaciones.append(
                        _rel(precio.iloc[i], precio.iloc[j]) <= cfg["tol_precio"]
                    )

                # Sin área ni precio comparables, no se confirma duplicación.
                if not comparaciones:
                    continue

                # Todas las variables disponibles deben cumplir su tolerancia.
                if not all(comparaciones):
                    continue

                padre[find(j)] = find(i)

    raices = np.array([find(i) for i in range(n)])
    df["id_grupo_dup"] = pd.factorize(raices)[0]
    df["es_duplicado"] = df.duplicated(
        "id_grupo_dup",
        keep="first",
    )

    log.info(
        "Deduplicación: %d anuncios, %d marcados como duplicados",
        n,
        int(df["es_duplicado"].sum()),
    )

    return df

