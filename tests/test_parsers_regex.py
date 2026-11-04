import unittest
from src.scraping.parsers import parsear_atributos_regex, limpiar_precio_moneda


class TestParsersRegex(unittest.TestCase):
    def test_parsear_atributos_regex_completo(self):
        texto = "Lindo departamento de 85 m2 construidos, 90 m² totales. Cuenta con 3 dormitorios, 2 baños y 1 cochera. Antigüedad 5 años."
        atributos = parsear_atributos_regex(texto)

        self.assertEqual(atributos["area_construida_m2"], 85.0)
        self.assertEqual(atributos["area_total_m2"], 90.0)
        self.assertEqual(atributos["dormitorios_num"], 3)
        self.assertEqual(atributos["banos_num"], 2)
        self.assertEqual(atributos["estacionamientos_num"], 1)
        self.assertEqual(atributos["antiguedad_anos"], 5)

    def test_parsear_atributos_estreno(self):
        texto = "Proyecto de estreno en Miraflores. 2 habs, 2 banos."
        atributos = parsear_atributos_regex(texto)

        self.assertEqual(atributos["antiguedad_anos"], 0)
        self.assertEqual(atributos["dormitorios_num"], 2)
        self.assertEqual(atributos["banos_num"], 2)

    def test_limpiar_precio_moneda_usd(self):
        texto = "USD 120,000 | Departamento en venta"
        moneda, monto = limpiar_precio_moneda(texto, {})
        self.assertEqual(moneda, "USD")
        self.assertEqual(monto, 120000.0)

    def test_limpiar_precio_moneda_pen(self):
        texto = "S/ 450,000 · Casa en Surco"
        moneda, monto = limpiar_precio_moneda(texto, {})
        self.assertEqual(moneda, "PEN")
        self.assertEqual(monto, 450000.0)


if __name__ == "__main__":
    unittest.main()

