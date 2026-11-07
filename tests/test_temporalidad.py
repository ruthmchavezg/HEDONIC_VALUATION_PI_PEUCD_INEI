from pi_nlp.temporalidad import clasificar_temporalidad


def test_tarifa_mensual_en_anuncio_mixto():
    titulo = "Departamento en alquiler temporal y anual"
    descripcion = (
        "Alquiler mínimo 15 días a $49 dólares diarios. "
        "<MONTO> DOLARES MENSUALES alquiler de 1 año."
    )

    resultado = clasificar_temporalidad(titulo, descripcion)

    assert resultado["tipo_alquiler"] == "mensual"
    assert resultado["motivo_temporalidad"] == "tarifa_mensual_identificada"


def test_anuncio_anual_y_temporal_sin_tarifa_mensual():
    titulo = "Alquiler temporal y anual"
    descripcion = "Alquiler mínimo 15 días. También se ofrece alquiler anual."

    resultado = clasificar_temporalidad(titulo, descripcion)

    assert resultado["tipo_alquiler"] == "indeterminado"
    assert resultado["motivo_temporalidad"] == (
        "oferta_anual_y_temporal_sin_tarifa_mensual"
    )


def test_anuncio_temporal_explicito():
    titulo = "Casa de playa en alquiler"
    descripcion = "Alquiler exclusivo de temporada de verano."

    resultado = clasificar_temporalidad(titulo, descripcion)

    assert resultado["tipo_alquiler"] == "temporal"
    assert resultado["motivo_temporalidad"] == "modalidad_temporal_explicita"


def test_anuncio_sin_evidencia_temporal():
    titulo = "Departamento en Miraflores"
    descripcion = "Departamento de dos dormitorios, sala y cocina."

    resultado = clasificar_temporalidad(titulo, descripcion)

    assert resultado["tipo_alquiler"] == "mensual"
    assert resultado["motivo_temporalidad"] == "mensual_por_defecto"


def test_anuncio_sin_texto():
    resultado = clasificar_temporalidad(None, None)

    assert resultado["tipo_alquiler"] == "indeterminado"
    assert resultado["motivo_temporalidad"] == "sin_texto"