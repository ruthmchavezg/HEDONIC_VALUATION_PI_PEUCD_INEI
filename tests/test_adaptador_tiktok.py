import pandas as pd

from pi_nlp.adaptadores.base import ESQUEMA
from pi_nlp.adaptadores.tiktok import AdaptadorTikTok


def crear_datos_prueba():
    return pd.DataFrame({
        "id_contenido": ["1234567890123456789", "9876543210987654321"],
        "url": [
            "https://www.tiktok.com/@usuario/video/1234567890123456789",
            "https://www.tiktok.com/@usuario/video/9876543210987654321",
        ],
        "timestamp": [
            "2026-11-11T03:03:57",
            "2026-11-11T03:04:06",
        ],
        "distrito": ["Ancón", "Miraflores"],
        "tipo_inmueble": ["casa", "departamento"],
        "fecha_publicacion": ["2026-09-02", "2025-11-04"],
        "descripcion": ["Casa en alquiler", "Departamento en alquiler"],
    })


def test_devuelve_esquema_comun_completo():
    resultado = AdaptadorTikTok("alquiler").a_esquema(crear_datos_prueba())

    assert list(resultado.columns[:len(ESQUEMA)]) == ESQUEMA
    assert {
        "id_contenido",
        "tipo_inmueble_fuente",
        "fecha_publicacion",
    }.issubset(resultado.columns)


def test_genera_identificadores_con_prefijo_tiktok():
    resultado = AdaptadorTikTok("alquiler").a_esquema(crear_datos_prueba())

    assert resultado["id_anuncio"].tolist() == [
        "tiktok-1234567890123456789",
        "tiktok-9876543210987654321",
    ]


def test_identificadores_son_unicos():
    resultado = AdaptadorTikTok("alquiler").a_esquema(crear_datos_prueba())

    assert resultado["id_anuncio"].is_unique


def test_convierte_timestamp_en_fecha_captura():
    resultado = AdaptadorTikTok("alquiler").a_esquema(crear_datos_prueba())

    assert pd.api.types.is_datetime64_any_dtype(resultado["fecha_captura"])
    assert resultado.loc[0, "fecha_captura"] == pd.Timestamp("2026-11-11 03:03:57")


def test_conserva_fecha_publicacion():
    resultado = AdaptadorTikTok("alquiler").a_esquema(crear_datos_prueba())

    assert resultado["fecha_publicacion"].tolist() == [
        "2026-09-02",
        "2025-11-04",
    ]


def test_mapea_distrito_a_ubicacion_y_distrito_fuente():
    resultado = AdaptadorTikTok("alquiler").a_esquema(crear_datos_prueba())

    assert resultado["ubicacion_texto"].tolist() == ["Ancón", "Miraflores"]
    assert resultado["distrito_fuente"].tolist() == ["Ancón", "Miraflores"]


def test_identificador_anuncio_queda_vacio_si_falta_id_contenido():
    crudo = crear_datos_prueba()
    crudo.loc[0, "id_contenido"] = None

    resultado = AdaptadorTikTok("alquiler").a_esquema(crudo)

    assert pd.isna(resultado.loc[0, "id_anuncio"])
