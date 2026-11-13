import pandas as pd

from pi_nlp.adaptadores.babilonia import AdaptadorBabilonia


def crear_datos_prueba():
    return pd.DataFrame({
        "id_interno": ["100001", "100002", "100003"],
        "url": [
            "https://babilonia.pe/anuncio/100001",
            "https://babilonia.pe/anuncio/100002",
            "https://babilonia.pe/anuncio/100003",
        ],
        "timestamp": [
            "2026-11-10T06:14:04",
            "2026-11-10T06:14:09",
            "2026-11-10T06:14:12",
        ],
        "tipo_inmueble": ["departamento", "casa", "habitacion"],
        "titulo": [
            "Departamento en alquiler",
            "Casa en alquiler",
            "Habitación en alquiler",
        ],
        "descripcion": [
            "Departamento de dos dormitorios",
            "Casa familiar",
            "Habitación individual",
        ],
        "precios_crudos": [
            "$1,000 S/3,418*",
            "$1,500 S/5,127*",
            "S/700",
        ],
        "direccion": [
            "Miraflores, Lima",
            "Surco, Lima",
            "Pueblo Libre, Lima",
        ],
        "info": [
            "2 Dormitorios | 2 Baños",
            "3 Dormitorios | 2 Baños",
            "1 Dormitorio | 1 Baño",
        ],
        "comodidades": ["Amoblado", "", "Internet"],
        "detalles_extra": ["", "", ""],
        "json_ld": [
            '{"@type":"Apartment"}',
            '{"@type":"House"}',
            '{"@type":"Room"}',
        ],
    })


def adaptar():
    crudo = crear_datos_prueba()
    resultado = AdaptadorBabilonia("alquiler").a_esquema(crudo)
    return crudo, resultado


def test_conserva_numero_de_registros():
    crudo, resultado = adaptar()
    assert len(resultado) == len(crudo)


def test_genera_identificadores_desde_id_interno():
    _, resultado = adaptar()
    assert resultado["id_anuncio"].tolist() == [
        "babilonia-100001",
        "babilonia-100002",
        "babilonia-100003",
    ]


def test_no_genera_ids_duplicados():
    _, resultado = adaptar()
    assert resultado["id_anuncio"].is_unique


def test_conserva_campos_de_trazabilidad():
    crudo, resultado = adaptar()

    assert resultado["id_interno"].tolist() == crudo["id_interno"].tolist()
    assert (
        resultado["tipo_inmueble_fuente"].tolist()
        == crudo["tipo_inmueble"].tolist()
    )
    assert resultado["json_ld"].tolist() == crudo["json_ld"].tolist()


def test_conserva_precios_y_caracteristicas():
    _, resultado = adaptar()

    assert resultado["precio_texto"].tolist() == [
        "$1,000 S/3,418*",
        "$1,500 S/5,127*",
        "S/700",
    ]

    assert resultado.loc[0, "caracteristicas_texto"] == (
        "2 Dormitorios | 2 Baños | Amoblado"
    )


def test_no_clasifica_automaticamente_departamentos_como_cuartos():
    _, resultado = adaptar()

    assert resultado["tipo_inmueble_fuente"].tolist() == [
        "departamento",
        "casa",
        "habitacion",
    ]

    assert resultado.loc[0, "tipo_inmueble_fuente"] == "departamento"

def test_usa_identificador_alternativo_si_id_interno_esta_vacio():
    crudo = crear_datos_prueba()
    crudo.loc[0, "id_interno"] = None

    resultado = AdaptadorBabilonia("alquiler").a_esquema(crudo)

    assert pd.notna(resultado.loc[0, "id_anuncio"])
    assert resultado["id_anuncio"].is_unique