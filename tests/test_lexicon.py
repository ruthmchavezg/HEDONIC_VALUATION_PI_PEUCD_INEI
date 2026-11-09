
"""Pruebas unitarias para la extracción de atributos por lexicón."""

import pytest

from pi_nlp.lexicon import extraer_atributos


@pytest.mark.parametrize(
    "texto, atributo, esperado",
    [
        ("Departamento con piscina", "attr_piscina", 1),
        ("Departamento sin piscina", "attr_piscina", 0),
        ("No cuenta con piscina", "attr_piscina", 0),
        ("Piscina no disponible", "attr_piscina", 0),
        ("Piscina no incluida", "attr_piscina", 0),
        ("No solo tiene piscina", "attr_piscina", 1),
        ("No se aceptan mascotas", "attr_mascotas", 0),
        ("Departamento pet friendly", "attr_mascotas", 1),
        ("Cuenta con piscina y gimnasio", "attr_piscina", 1),
        ("Cuenta con piscina y gimnasio", "attr_gimnasio", 1),
        ("Departamento sin piscina y con gimnasio", "attr_gimnasio", 1),
        ("Departamento sin piscina y con gimnasio", "attr_piscina", 0),
        ("Departamento sin atributos adicionales", "attr_piscina", 0),
        ("Sin piscina ni gimnasio", "attr_piscina", 0),
        ("Sin piscina ni gimnasio", "attr_gimnasio", 0),
        ("No tiene piscina, pero sí gimnasio", "attr_piscina", 0),
        ("No tiene piscina, pero sí gimnasio", "attr_gimnasio", 1),
        ("Departamento con piscina, sin ascensor", "attr_piscina", 1),
    ],
)
def test_extraccion_atributos(texto, atributo, esperado):
    resultado = extraer_atributos(texto)
    assert resultado[atributo] == esperado
