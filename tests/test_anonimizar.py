
import pytest

from pi_nlp.anonimizar import anonimizar


def test_anonimiza_contacto_con_dos_puntos():
    texto = "Contacto: Juan Pérez"
    resultado = anonimizar(texto)

    assert "<CONTACTO>" in resultado.texto
    assert "Juan Pérez" not in resultado.texto


def test_anonimiza_telefono_con_puntos():
    texto = "Teléfono: 9.8.7.6.5.4.3.2.1"
    resultado = anonimizar(texto)

    assert "<TELEFONO>" in resultado.texto
    assert resultado.n_telefonos == 1


def test_detecta_nombre_despues_de_contactanos():
    texto = (
        "Contáctanos para coordinar una visita. | "
        "María López - Asesora inmobiliaria."
    )
    resultado = anonimizar(texto)

    assert "María López" not in resultado.texto


def test_detecta_nombre_despues_de_comunicate():
    texto = "Comunícate con Juan Pérez para más información."
    resultado = anonimizar(texto)

    assert "Juan Pérez" not in resultado.texto


def test_conserva_caracteristicas_inmobiliarias():
    texto = (
        "Departamento de 60 m², 2 dormitorios, "
        "sin estacionamiento y cerca de parques."
    )
    resultado = anonimizar(texto)

    assert "60 m²" in resultado.texto
    assert "2 dormitorios" in resultado.texto
    assert "sin estacionamiento" in resultado.texto
    assert "cerca de parques" in resultado.texto

def test_conserva_caracteristicas_despues_de_contactanos():
    texto = (
        "Contáctanos para coordinar una visita. | "
        "Terraza, piscina y gimnasio. | "
        "María López - Asesora inmobiliaria."
    )

    resultado = anonimizar(texto)

    assert "María López" not in resultado.texto
    assert "Terraza" in resultado.texto
    assert "piscina" in resultado.texto
    assert "gimnasio" in resultado.texto

def test_anonimiza_precio_en_soles():
    resultado = anonimizar("Alquiler mensual: S/ 2,500")

    assert "<MONTO_ALQUILER>" in resultado.texto
    assert resultado.montos[0]["tipo"] == "alquiler"
    assert "2,500" not in resultado.texto
    assert resultado.montos[0]  ["valor"] == 2500
    assert resultado.montos[0]["moneda"] == "PEN"
    assert resultado.montos[0]["texto_original"] == "S/ 2,500"
    assert resultado.montos[0]["etiqueta"] == "<MONTO_ALQUILER>"
    assert resultado.montos[0]["enmascarado"] is True


def test_anonimiza_precio_en_dolares():
    resultado = anonimizar("Alquiler mensual: USD 800")

    assert "<MONTO_ALQUILER>" in resultado.texto
    assert resultado.montos[0]["tipo"] == "alquiler"
    assert "800" not in resultado.texto
    assert resultado.montos[0]["valor"] == 800
    assert resultado.montos[0]["moneda"] == "USD"


def test_distingue_garantia():
    resultado = anonimizar("Garantía: S/ 2,500")

    assert "<MONTO_GARANTIA>" in resultado.texto
    assert resultado.montos[0]["tipo"] == "garantia"


def test_distingue_mantenimiento():
    resultado = anonimizar("Mantenimiento: S/ 200")

    assert "<MONTO_MANTENIMIENTO>" in resultado.texto
    assert resultado.montos[0]["tipo"] == "mantenimiento"


def test_conserva_area_inmobiliaria():
    resultado = anonimizar("Departamento de 80 m²")

    assert "80 m²" in resultado.texto
    assert resultado.montos == []

def test_distingue_garantia_y_mantenimiento_en_misma_oracion():
    resultado = anonimizar(
        "Garantía de S/ 1,500 y mantenimiento de S/ 200."
    )

    assert resultado.montos[0]["tipo"] == "garantia"
    assert resultado.montos[1]["tipo"] == "mantenimiento"


def test_distingue_alquiler_y_garantia():
    resultado = anonimizar(
        "Alquiler S/ 1,500, dos meses de garantía S/ 3,000."
    )

    assert resultado.montos[0]["tipo"] == "alquiler"
    assert resultado.montos[1]["tipo"] == "garantia"


def test_identifica_monto_en_contexto_de_venta():
    resultado = anonimizar(
        "Departamento en venta a USD 85,000."
    )

    assert resultado.montos[0]["tipo"] == "venta"
    assert "<MONTO_VENTA>" in resultado.texto


def test_no_hereda_contexto_de_garantia_a_mantenimiento():
    resultado = anonimizar(
        "Garantía S/ 1,500; mantenimiento S/ 200."
    )

    assert resultado.montos[0]["tipo"] == "garantia"
    assert resultado.montos[1]["tipo"] == "mantenimiento"

def test_detecta_precio_con_sufijo_k():
    resultado = anonimizar("Alquiler mensual: S/ 1.5k")

    assert resultado.montos[0]["valor"] == 1500
    assert resultado.montos[0]["moneda"] == "PEN"
    assert resultado.montos[0]["tipo"] == "alquiler"


def test_detecta_precio_con_sufijo_mil():
    resultado = anonimizar("Alquiler mensual: S/ 1,5 mil")

    assert resultado.montos[0]["valor"] == 1500
    assert resultado.montos[0]["moneda"] == "PEN"
    assert resultado.montos[0]["tipo"] == "alquiler"


def test_detecta_precio_sin_simbolo_de_moneda():
    resultado = anonimizar("Alquiler mensual: 1500 soles")

    assert resultado.montos[0]["valor"] == 1500
    assert resultado.montos[0]["moneda"] == "PEN"
    assert resultado.montos[0]["tipo"] == "alquiler"


def test_detecta_precio_en_dolares_sin_simbolo():
    resultado = anonimizar("Alquiler mensual: 450 dolares")

    assert resultado.montos[0]["valor"] == 450
    assert resultado.montos[0]["moneda"] == "USD"
    assert resultado.montos[0]["tipo"] == "alquiler"

def test_identifica_alquiler_con_contexto_posterior():
    resultado = anonimizar("S/ 1,500 por alquiler")

    assert resultado.montos[0]["tipo"] == "alquiler"


def test_precio_sin_contexto_explicito_se_considera_alquiler():
    resultado = anonimizar("Precio: S/ 1,500")

    assert resultado.montos[0]["tipo"] == "alquiler"


def test_precio_de_venta_no_se_clasifica_como_alquiler():
    resultado = anonimizar("Precio de venta: USD 85,000")

    assert resultado.montos[0]["tipo"] == "venta"


def test_identifica_venta_con_contexto_posterior():
    resultado = anonimizar("USD 85,000 por venta")

    assert resultado.montos[0]["tipo"] == "venta"


def test_separa_contextos_de_venta_y_alquiler():
    resultado = anonimizar(
        "Venta USD 85,000; alquiler S/ 2,500"
    )

    assert resultado.montos[0]["tipo"] == "venta"
    assert resultado.montos[1]["tipo"] == "alquiler"