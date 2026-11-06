import unittest
from unittest.mock import patch
import shutil
import pandas as pd

from config.settings import PERFILES_PORTALES, BASE_DIR
from src.scraping.bcrp_client import obtener_tc_bcrp
from src.scraping.parsers import recolectar_enlaces_portal as recolectar_original
import src.scraping.storage as storage_module

from importlib import import_module
orquestador = import_module("pipelines.01_run_portals_scraper")

TEST_RAW_DIR = BASE_DIR / "data" / "raw" / "test_env"
TEST_INTERIM_DIR = BASE_DIR / "data" / "interim" / "test_env"

URLS_ELEGIDAS_EN_TEST = set()


def recolectar_solo_1_por_tipo(engine, perfil_portal: dict, url_semilla: str, max_paginas: int) -> list:
    """Ejecuta el recolector real en la página 1 y devuelve el primer enlace no repetido."""
    enlaces = recolectar_original(engine, perfil_portal, url_semilla, max_paginas=1)
    for enlace in enlaces:
        if enlace not in URLS_ELEGIDAS_EN_TEST:
            URLS_ELEGIDAS_EN_TEST.add(enlace)
            return [enlace]
    return enlaces[:1]


class TestSmoke21Portals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepara el entorno limpio de prueba."""
        URLS_ELEGIDAS_EN_TEST.clear()
        if TEST_RAW_DIR.exists():
            shutil.rmtree(TEST_RAW_DIR)
        if TEST_INTERIM_DIR.exists():
            shutil.rmtree(TEST_INTERIM_DIR)

        (TEST_RAW_DIR / "portals").mkdir(parents=True, exist_ok=True)
        (TEST_RAW_DIR / "sessions").mkdir(parents=True, exist_ok=True)
        (TEST_INTERIM_DIR / "portals_clean").mkdir(parents=True, exist_ok=True)
        (TEST_INTERIM_DIR / "checkpoints").mkdir(parents=True, exist_ok=True)

        orquestador.configurar_logs()
        cls.tc_bcrp = obtener_tc_bcrp()

    @patch.object(storage_module, "RAW_DIR", TEST_RAW_DIR)
    @patch.object(storage_module, "INTERIM_DIR", TEST_INTERIM_DIR)
    @patch.object(orquestador, "recolectar_enlaces_portal", side_effect=recolectar_solo_1_por_tipo)
    def test_extraer_21_anuncios_multiportal(self, mock_recolector):
        """
        Prueba 01_run_portals_scraper.py limitando desde el test a 1 anuncio
        por categoría (casa, departamento, habitación) en los 7 portales (21 en total).
        """
        portales = list(PERFILES_PORTALES.keys())
        print(f"\n[*] Iniciando Smoke Test en entorno aislado para {len(portales)} portales...")

        for portal in portales:
            print(f"\n---> Probando portal: {portal.upper()} (1 por categoría)")
            orquestador.procesar_portal(
                nombre_portal=portal,
                max_paginas=1,
                headless=False,
                tc_bcrp=self.tc_bcrp
            )

        master_test_csv = TEST_INTERIM_DIR / "base_maestra_inmobiliaria_inei.csv"
        historial_test_csv = TEST_INTERIM_DIR / "historial_scrapeo.csv"

        self.assertTrue(master_test_csv.exists(), "No se generó la base maestra en el entorno de prueba.")
        self.assertTrue(historial_test_csv.exists(), "No se generó el historial de scrapeo en el entorno de prueba.")

        df_resultado = pd.read_csv(master_test_csv)
        df_historial = pd.read_csv(historial_test_csv)

        print("\n" + "=" * 70)
        print("RESUMEN DE AUDITORÍA DEL SMOKE TEST (ENTORNO DE PRUEBA)")
        print("=" * 70)
        print(f"Total de anuncios extraídos: {len(df_resultado)} / 21 esperados")
        print("\nDistribución por portal y tipo de inmueble:")
        if not df_resultado.empty:
            resumen = df_resultado.groupby(["portal", "tipo_inmueble"]).size().unstack(fill_value=0)
            print(resumen)
        print(f"\nArchivo de prueba guardado en: {master_test_csv}")
        print("=" * 70)

        self.assertGreater(len(df_resultado), 0, "No se extrajo ningún anuncio.")
        self.assertEqual(len(df_historial), len(portales), "No se registraron todos los portales en el historial.")


if __name__ == "__main__":
    unittest.main(verbosity=2)