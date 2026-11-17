
import unittest

from src.pi_nlp.extraccion import extraer_campos


CFG = {
    "max_dormitorios": 15,
    "max_banos": 15,
    "max_estacionamientos": 20,
}


class TestExtraccionSuperficies(unittest.TestCase):

    def extraer(self, caracteristicas):
        return extraer_campos(
            titulo="Departamento en alquiler",
            estructurado=caracteristicas,
            descripcion=None,
            cfg=CFG,
        )

    def test_area_construida_y_techada_separadas(self):
        resultado = self.extraer(
            "150 m2 construidos y 90 m2 techados"
        )

        self.assertEqual(resultado["area_construida_m2"], 150.0)
        self.assertEqual(resultado["area_techada_m2"], 90.0)

    def test_area_techada_explicita(self):
        resultado = self.extraer("Área techada: 90 m2")

        self.assertEqual(resultado["area_techada_m2"], 90.0)
        self.assertIsNone(resultado["area_construida_m2"])

    def test_area_total_y_terreno_se_conservan(self):
        resultado = self.extraer(
            "200 m2 de terreno | 175 m2 de área total"
        )

        self.assertEqual(resultado["area_terreno_m2"], 200.0)
        self.assertEqual(resultado["area_total_m2"], 175.0)

    def test_sin_area_techada(self):
        resultado = self.extraer("85 m2 construidos")

        self.assertEqual(resultado["area_construida_m2"], 85.0)
        self.assertIsNone(resultado["area_techada_m2"])

    def test_abreviaturas_conservadas(self):
        resultado = self.extraer("A.C. 150 m2 | A.T. 200 m2")

        self.assertEqual(resultado["area_construida_m2"], 150.0)
        self.assertEqual(resultado["area_terreno_m2"], 200.0)


if __name__ == "__main__":
    unittest.main()
