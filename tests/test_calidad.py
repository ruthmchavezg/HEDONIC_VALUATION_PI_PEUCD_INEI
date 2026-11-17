from pi_nlp.calidad import banderas
from pi_nlp.config import settings


CFG = {
    **settings()["calidad"],
    "incluir_callao": False,
}


def crear_fila(area):
    return {
        "precio_pen_pub": 2000,
        "precio_usd_pub": None,
        "descripcion_anon": (
            "Departamento en alquiler con buenas características "
            "y excelente ubicación en Lima"
        ),
        "ambito": "lima_metropolitana",
        "area_total_m2": area,
    }


def test_marca_area_de_1_m2():
    resultado = banderas(crear_fila(1), CFG)
    assert resultado["flag_area_sospechosamente_pequena"] is True


def test_marca_area_de_5_m2():
    resultado = banderas(crear_fila(5), CFG)
    assert resultado["flag_area_sospechosamente_pequena"] is True


def test_no_marca_area_mayor_a_5_m2():
    resultado = banderas(crear_fila(6), CFG)
    assert resultado["flag_area_sospechosamente_pequena"] is False


def test_no_marca_area_de_12_m2():
    resultado = banderas(crear_fila(12), CFG)
    assert resultado["flag_area_sospechosamente_pequena"] is False


def test_conserva_bandera_area_atipica():
    resultado = banderas(crear_fila(1), CFG)
    assert resultado["flag_area_atipica"] is False

from pi_nlp.calidad import fuga_precio


def test_precio_alquiler_enmascarado_no_es_fuga():
    montos = [{
        "valor": 1500,
        "moneda": "PEN",
        "tipo": "alquiler",
        "enmascarado": True,
    }]

    resultado = fuga_precio(
        montos, 1500, None, 0.01,
        ["Alquiler mensual: <MONTO_ALQUILER>"]
    )

    assert resultado is False


def test_precio_expuesto_en_descripcion_es_fuga():
    montos = [{
        "valor": 1500,
        "moneda": "PEN",
        "tipo": "alquiler",
        "enmascarado": False,
    }]

    resultado = fuga_precio(
        montos, 1500, None, 0.01,
        ["Alquiler mensual: S/ 1,500"]
    )

    assert resultado is True


def test_precio_expuesto_en_caracteristicas_es_fuga():
    montos = [{
        "valor": 1500,
        "moneda": "PEN",
        "tipo": "alquiler",
        "enmascarado": False,
    }]

    resultado = fuga_precio(
        montos, 1500, None, 0.01,
        ["", "", "Precio de alquiler: S/ 1,500"]
    )

    assert resultado is True


def test_garantia_no_se_considera_fuga():
    montos = [{
        "valor": 1500,
        "moneda": "PEN",
        "tipo": "garantia",
        "enmascarado": True,
    }]

    resultado = fuga_precio(
        montos, 1500, None, 0.01,
        ["Garantía: <MONTO_GARANTIA>"]
    )

    assert resultado is False

def test_detecta_precio_repetido_en_texto_anonimizado():
    montos = [{
        "valor": 1500,
        "moneda": "PEN",
        "tipo": "alquiler",
        "texto_original": "S/ 1,500",
        "enmascarado": True,
    }]

    resultado = fuga_precio(
        montos, 1500, None, 0.01,
        [
            "Alquiler mensual: <MONTO_ALQUILER>",
            "El precio es S/ 1,500",
        ]
    )

    assert resultado is True

def test_area_construida_techada_igual():
    fila = crear_fila(290)
    fila.update({
        "area_construida_m2": 130,
        "area_techada_m2": 130,
    })

    resultado = banderas(fila, CFG)

    assert resultado["flag_area_construida_techada_igual"] is True


def test_area_total_menor_techada():
    fila = crear_fila(267)
    fila.update({
        "area_total_m2": 267,
        "area_techada_m2": 403,
    })

    resultado = banderas(fila, CFG)

    assert resultado["flag_area_total_menor_techada"] is True


def test_area_total_menor_terreno():
    fila = crear_fila(200)
    fila.update({
        "area_total_m2": 200,
        "area_terreno_m2": 3504,
    })

    resultado = banderas(fila, CFG)

    assert resultado["flag_area_total_menor_terreno"] is True


def test_area_total_menor_construida():
    fila = crear_fila(200)
    fila.update({
        "area_total_m2": 200,
        "area_construida_m2": 260,
    })

    resultado = banderas(fila, CFG)

    assert resultado["flag_area_total_menor_construida"] is True


def test_superficies_faltantes_no_generan_alertas():
    fila = crear_fila(290)

    resultado = banderas(fila, CFG)

    assert resultado["flag_area_construida_techada_igual"] is False
    assert resultado["flag_area_total_menor_techada"] is False
    assert resultado["flag_area_total_menor_terreno"] is False
    assert resultado["flag_area_total_menor_construida"] is False


def test_area_techada_sospechosamente_pequena():
    fila = crear_fila(12)
    fila["area_techada_m2"] = 5

    resultado = banderas(fila, CFG)

    assert resultado["flag_area_sospechosamente_pequena"] is True


def test_area_techada_atipica():
    fila = crear_fila(12)
    fila["area_techada_m2"] = 10001

    resultado = banderas(fila, CFG)

    assert resultado["flag_area_atipica"] is True