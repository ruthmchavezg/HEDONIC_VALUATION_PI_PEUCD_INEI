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