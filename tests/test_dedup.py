
import pandas as pd

from pi_nlp.dedup import marcar_duplicados


CFG = {
    "min_chars_texto": 20,
    "umbral_texto": 0.80,
    "tol_area": 0.05,
    "tol_precio": 0.10,
}


def crear_anuncios(
    distritos,
    areas,
    precios,
    descripcion=None,
):
    n = len(distritos)

    if descripcion is None:
        descripcion = [
            "Departamento amplio con sala comedor cocina y dormitorios "
            "en excelente estado de conservacion"
        ] * n

    return pd.DataFrame({
        "id_anuncio": [f"urbania-{i}" for i in range(n)],
        "distrito": distritos,
        "tipo_inmueble": ["departamento"] * n,
        "descripcion_anon": descripcion,
        "area_construida_m2": areas,
        "area_total_m2": [None] * n,
        "area_titulo_m2": [None] * n,
        "precio_pen_pub": precios,
    })


def test_no_compara_anuncios_sin_distrito():
    df = crear_anuncios(
        distritos=[None, None],
        areas=[70, 70],
        precios=[2000, 2000],
    )

    resultado = marcar_duplicados(df, CFG)

    assert resultado["es_duplicado"].sum() == 0


def test_no_agrupa_si_faltan_area_y_precio():
    df = crear_anuncios(
        distritos=["Miraflores", "Miraflores"],
        areas=[None, None],
        precios=[None, None],
    )

    resultado = marcar_duplicados(df, CFG)

    assert resultado["es_duplicado"].sum() == 0


def test_agrupa_anuncios_con_variables_compatibles():
    df = crear_anuncios(
        distritos=["Miraflores", "Miraflores"],
        areas=[70, 72],
        precios=[2000, 2050],
    )

    resultado = marcar_duplicados(df, CFG)

    assert resultado["es_duplicado"].sum() == 1


def test_no_agrupa_anuncios_con_areas_incompatibles():
    df = crear_anuncios(
        distritos=["Miraflores", "Miraflores"],
        areas=[70, 100],
        precios=[2000, 2000],
    )

    resultado = marcar_duplicados(df, CFG)

    assert resultado["es_duplicado"].sum() == 0
