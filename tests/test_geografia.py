
import pytest

from pi_nlp.geografia import clasificar_distrito


@pytest.mark.parametrize(
    "ubicacion, esperado",
    [
        ("Zaragoza, Ate 15012, Peru, Lima", "ate"),
        ("Federico Villarreal en Comas, Lima", "comas"),
        ("Av. Javier Prado Oeste 800 - Magdalena, Lima", "magdalena del mar"),
        ("Cieneguilla Condominio El Refugio, Lima", "cieneguilla"),
    ],
)
def test_reconoce_distritos_dentro_de_ubicacion(ubicacion, esperado):
    distrito, ambito = clasificar_distrito(ubicacion)

    assert distrito == esperado
    assert ambito == "lima_metropolitana"


def test_reconoce_distrito_exacto():
    distrito, ambito = clasificar_distrito(
        "Departamento, Miraflores, Lima"
    )

    assert distrito == "miraflores"
    assert ambito == "lima_metropolitana"


def test_lima_sola_no_se_asigna_como_distrito():
    distrito, ambito = clasificar_distrito(
        "Av. Arequipa 748, Lima"
    )

    assert distrito is None
    assert ambito == "indeterminado"


@pytest.mark.parametrize(
    "ubicacion",
    [
        "Av. principal, Bellavista, Callao",
        "Avenida Costanera, La Perla, Callao",
        "Av. principal, Ventanilla, Callao",
        "Av. principal, Mi Perú, Callao",
    ],
)
def test_todos_los_distritos_del_callao_se_agrupan(ubicacion):
    distrito, ambito = clasificar_distrito(ubicacion)

    assert distrito == "callao"
    assert ambito == "callao"


def test_no_asigna_si_hay_dos_distritos_en_una_direccion():
    distrito, ambito = clasificar_distrito(
        "Límite entre Comas y Los Olivos, Lima"
    )

    assert distrito is None
    assert ambito == "indeterminado"
@pytest.mark.parametrize(
    "ubicacion, esperado",
    [
        (
            "Enrique Villar N.° 830, Santa Beatriz, Lima",
            "cercado de lima",
        ),
        (
            "Helio Santa Beatriz, Lima",
            "cercado de lima",
        ),
        (
            "Av. José Gálvez Urb. Santa Beatriz - Lima, Lima",
            "cercado de lima",
        ),
        (
            "Urbanización HUAMPANI I, Lima",
            "lurigancho",
        ),
        (
            "Jr. Las Camelias - Playa Arica, Lima",
            "lurin",
        ),
        (
            "Antigua Carretera a Huarochiri Cieneguilla al 18, Lima",
            "cieneguilla",
        ),
    ],
)
def test_reconoce_alias_y_referencias_territoriales(
    ubicacion, esperado
):
    distrito, ambito = clasificar_distrito(ubicacion)

    assert distrito == esperado
    assert ambito == "lima_metropolitana"


def test_huarochiri_no_se_confunde_con_cieneguilla():
    distrito, ambito = clasificar_distrito(
        "Antigua Carretera a Huarochiri, Lima"
    )

    assert distrito == "huarochiri"
    assert ambito == "fuera"


def test_alto_benavides_sin_distrito_verificable():
    distrito, ambito = clasificar_distrito(
        "Alto Benavides | Imagina Inmobiliaria, Lima"
    )

    assert distrito is None
    assert ambito == "indeterminado"