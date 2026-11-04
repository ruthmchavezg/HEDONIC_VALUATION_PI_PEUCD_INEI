import unittest
from unittest.mock import patch, MagicMock
import io
import json
from src.scraping.bcrp_client import obtener_tc_bcrp
from config.settings import TIPO_CAMBIO_FALLBACK

class TestBCRPClient(unittest.TestCase):
    def test_obtener_tc_bcrp_real_connection(self):
        """Prueba la conexión real al endpoint del BCRP y muestra el tipo de cambio capturado."""
        # Llamada en vivo a la función que parchea el SSL y se conecta a internet
        tc = obtener_tc_bcrp()
        
        # Impresión explícita del resultado
        print(f"\n[VALIDACIÓN EN VIVO] El tipo de cambio capturado AHORA MISMO es: S/ {tc}")
        
        # Verificación estructural
        self.assertIsInstance(tc, float)
        self.assertGreater(tc, 1.0)
        self.assertLess(tc, 10.0)

    @patch("urllib.request.urlopen")
    def test_obtener_tc_bcrp_mock_success(self, mock_urlopen):
        """Prueba el parseo exitoso simulando respuesta JSON de la API del BCRP."""
        mock_response_data = {
            "periods": [
                {"name": "01.Nov.26", "values": ["3.7420"]},
                {"name": "02.Nov.26", "values": ["3.7510"]}
            ]
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_cm

        tc = obtener_tc_bcrp()
        self.assertEqual(tc, 3.751)

    @patch("urllib.request.urlopen")
    def test_obtener_tc_bcrp_fallback_on_network_error(self, mock_urlopen):
        """Prueba que si la API del BCRP falla o hay timeout, se use el valor fallback de manera segura."""
        mock_urlopen.side_effect = Exception("Connection timeout / Network error")

        tc = obtener_tc_bcrp()
        self.assertEqual(tc, TIPO_CAMBIO_FALLBACK)

    @patch("urllib.request.urlopen")
    def test_obtener_tc_bcrp_fallback_on_empty_periods(self, mock_urlopen):
        """Prueba respuesta con periods vacíos o valor 'n.d.' (no disponible)."""
        mock_response_data = {
            "periods": [
                {"name": "03.Nov.26", "values": ["n.d."]}
            ]
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_cm

        tc = obtener_tc_bcrp()
        self.assertEqual(tc, TIPO_CAMBIO_FALLBACK)

if __name__ == "__main__":
    unittest.main(buffer=False)
