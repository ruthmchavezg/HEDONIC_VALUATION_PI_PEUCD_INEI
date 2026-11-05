
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
