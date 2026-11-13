
from pi_nlp.precio import asignar_precio_desde_montos


def test_asigna_un_alquiler_en_soles():
    montos = [
        {"valor": 1500, "moneda": "PEN", "tipo": "alquiler"}
    ]

    resultado = asignar_precio_desde_montos(montos)

    assert resultado["precio_pen_pub"] == 1500
    assert resultado["precio_usd_pub"] is None
    assert resultado["moneda_pub"] == "PEN"
    assert resultado["flag_precio_ambiguo"] is False


def test_asigna_un_alquiler_en_dolares():
    montos = [
        {"valor": 450, "moneda": "USD", "tipo": "alquiler"}
    ]

    resultado = asignar_precio_desde_montos(montos)

    assert resultado["precio_pen_pub"] is None
    assert resultado["precio_usd_pub"] == 450
    assert resultado["moneda_pub"] == "USD"


def test_asigna_alquiler_en_ambas_monedas():
    montos = [
        {"valor": 1500, "moneda": "PEN", "tipo": "alquiler"},
        {"valor": 450, "moneda": "USD", "tipo": "alquiler"},
    ]

    resultado = asignar_precio_desde_montos(montos)

    assert resultado["precio_pen_pub"] == 1500
    assert resultado["precio_usd_pub"] == 450
    assert resultado["moneda_pub"] == "PEN+USD"
    assert resultado["flag_precio_ambiguo"] is False


def test_marca_ambiguedad_con_dos_alquileres_en_soles():
    montos = [
        {"valor": 1500, "moneda": "PEN", "tipo": "alquiler"},
        {"valor": 1800, "moneda": "PEN", "tipo": "alquiler"},
    ]

    resultado = asignar_precio_desde_montos(montos)

    assert resultado["precio_pen_pub"] is None
    assert resultado["flag_precio_ambiguo"] is True


def test_marca_ambiguedad_con_dos_alquileres_en_dolares():
    montos = [
        {"valor": 450, "moneda": "USD", "tipo": "alquiler"},
        {"valor": 500, "moneda": "USD", "tipo": "alquiler"},
    ]

    resultado = asignar_precio_desde_montos(montos)

    assert resultado["precio_usd_pub"] is None
    assert resultado["flag_precio_ambiguo"] is True


def test_no_confunde_garantia_con_alquiler():
    montos = [
        {"valor": 1500, "moneda": "PEN", "tipo": "alquiler"},
        {"valor": 1500, "moneda": "PEN", "tipo": "garantia"},
        {"valor": 150, "moneda": "PEN", "tipo": "mantenimiento"},
    ]

    resultado = asignar_precio_desde_montos(montos)

    assert resultado["precio_pen_pub"] == 1500
    assert resultado["flag_precio_ambiguo"] is False


def test_no_asigna_garantia_ni_mantenimiento():
    montos = [
        {"valor": 1500, "moneda": "PEN", "tipo": "garantia"},
        {"valor": 150, "moneda": "PEN", "tipo": "mantenimiento"},
    ]

    resultado = asignar_precio_desde_montos(montos)

    assert resultado["precio_pen_pub"] is None
    assert resultado["precio_usd_pub"] is None
    assert resultado["flag_precio_ambiguo"] is False


def test_monto_otro_no_se_asigna_automaticamente():
    montos = [
        {"valor": 1500, "moneda": "PEN", "tipo": "otro"}
    ]

    resultado = asignar_precio_desde_montos(montos)

    assert resultado["precio_pen_pub"] is None
    assert resultado["precio_usd_pub"] is None
    assert resultado["flag_precio_ambiguo"] is False
