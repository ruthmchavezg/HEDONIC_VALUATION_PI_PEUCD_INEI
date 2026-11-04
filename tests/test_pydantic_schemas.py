import unittest
from pydantic import ValidationError
from src.schemas.schemas import OfertaInmobiliariaINEI


class TestPydanticSchemas(unittest.TestCase):
    def test_schema_conversion_usd_a_pen(self):
        """Verifica que un precio en USD se convierta a PEN usando el tipo de cambio del BCRP."""
        payload = {
            "id_anuncio": "urbania_12345",
            "fecha_captura": "2026-11-04",
            "portal": "urbania",
            "tipo_inmueble": "departamento",
            "url": "https://urbania.pe/propiedades/12345.html",
            "precio_original": 100000.0,
            "moneda_original": "USD",
            "tipo_cambio_bcrp": 3.75,
            "latitud": -12.08,
            "longitud": -77.03
        }
        oferta = OfertaInmobiliariaINEI(**payload)
        self.assertEqual(oferta.precio_usd, 100000.0)
        self.assertEqual(oferta.precio_pen, 375000.0)

    def test_schema_conversion_pen_a_usd(self):
        """Verifica que un precio en PEN se convierta a USD dividiendo entre el tipo de cambio."""
        payload = {
            "id_anuncio": "babilonia_67890",
            "fecha_captura": "2026-11-04",
            "portal": "babilonia",
            "tipo_inmueble": "casa",
            "url": "https://babilonia.pe/inmueble/67890",
            "precio_original": 375000.0,
            "moneda_original": "PEN",
            "tipo_cambio_bcrp": 3.75,
        }
        oferta = OfertaInmobiliariaINEI(**payload)
        self.assertEqual(oferta.precio_pen, 375000.0)
        self.assertEqual(oferta.precio_usd, 100000.0)

    def test_schema_bounding_box_coordenadas_invalidas(self):
        """Descarta inmuebles fuera de los límites de Lima Metropolitana."""
        payload = {
            "id_anuncio": "test_invalido",
            "fecha_captura": "2026-11-04",
            "portal": "babilonia",
            "tipo_inmueble": "casa",
            "url": "https://babilonia.pe/inmueble/999",
            "tipo_cambio_bcrp": 3.75,
            "latitud": 40.7128,  # Nueva York (fuera de Lima)
            "longitud": -74.0060
        }
        with self.assertRaises(ValidationError):
            OfertaInmobiliariaINEI(**payload)


if __name__ == "__main__":
    unittest.main()

