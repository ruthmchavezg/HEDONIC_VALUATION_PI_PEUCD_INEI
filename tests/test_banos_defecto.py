"""Pruebas de la regla por defecto de baños (banos_por_defecto en scripts/construir_base_final.py).
Ejecutar:  python tests/test_banos_defecto.py   (o pytest tests/)
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
spec = importlib.util.spec_from_file_location("construir_base_final", RAIZ / "scripts" / "construir_base_final.py")
cbf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cbf)


def _fila(tipo, banos, propios=np.nan, comp=np.nan, hab=None):
    return {"banos_tipo": tipo, "banos": banos, "banos_propios": propios, "banos_compartidos": comp,
            "banos_evidencia": None, "es_habitacion": (tipo is not None) if hab is None else hab}


def test_reglas():
    df = pd.DataFrame([
        _fila("sin_dato", 2),                      # 0 habitacion con 2 baños y sin texto -> compartido 2
        _fila("sin_dato", 1.5),                    # 1 silver: 1.5 = 1 baño + medio baño -> compartido 1
        _fila("sin_dato", np.nan),                 # 2 sin baños en la ficha -> vacio
        _fila("sin_dato", 0),                      # 3 ficha 0 -> vacio
        _fila("propio", 1, 1, 0),                  # 4 propio detectado: no se toca
        _fila("compartido", 1, 0, 1),              # 5 compartido detectado: no se toca
        _fila("mixto", 2),                         # 6 mixto: no se decide
        _fila(None, 2),                            # 7 departamento sin propios -> propios = ficha
        _fila(None, 3, 2),                         # 8 departamento con propios: no se toca
        _fila(None, np.nan),                       # 9 departamento sin baños -> vacio
    ])
    out, n_hab, n_dep = cbf.banos_por_defecto(df)
    comp, prop, tipo = out["banos_compartidos"], out["banos_propios"], out["banos_tipo"]
    assert (n_hab, n_dep) == (2, 1)
    assert comp[7] == 0 and comp[8] == 0 and pd.isna(comp[9])   # propio => 0 compartidos; sin baños => vacio
    assert (comp[0], prop[0], tipo[0]) == (2, 0, "compartido") and out["banos_evidencia"][0].startswith("por defecto")
    assert (comp[1], prop[1]) == (1, 0)
    assert pd.isna(comp[2]) and pd.isna(prop[2]) and tipo[2] == "sin_dato"
    assert pd.isna(comp[3]) and pd.isna(prop[3])
    assert (prop[4], comp[4]) == (1, 0) and (prop[5], comp[5]) == (0, 1)
    assert pd.isna(comp[6]) and pd.isna(prop[6]) and tipo[6] == "mixto"
    assert prop[7] == 2
    assert prop[8] == 2
    assert pd.isna(prop[9])





def test_tipos():
    """cf_tipo_inmueble_homologado = lo que es (5 valores); cf_tipo_inmueble = agrupado en 3."""
    def f(**k):
        base = {"tipo_inmueble_fuente": None, "tipo_inmueble": "departamento", "titulo_anon": "", "descripcion_anon": "",
                "origen_dato": "portal", "tipo_inmueble_detalle": None, "es_habitacion": False}
        base.update(k)
        return base
    df = pd.DataFrame([
        f(tipo_inmueble_fuente="Casa", tipo_inmueble="casa"),                                          # 0 casa
        f(tipo_inmueble_fuente="Departamento"),                                                        # 1 departamento
        f(tipo_inmueble_fuente="Departamento", titulo_anon="Mini departamento amoblado"),             # 2 minidepartamento
        f(tipo_inmueble_fuente="Departamento", titulo_anon="Monoambiente en Surco"),                  # 3 minidepartamento
        f(tipo_inmueble_fuente="Habitación", tipo_inmueble="cuarto", es_habitacion=True,
          titulo_anon="Habitación amoblada"),                                                         # 4 habitacion
        f(tipo_inmueble_fuente="Habitación", tipo_inmueble="cuarto", es_habitacion=True,
          titulo_anon="Cuarto en alquiler"),                                                          # 5 cuarto
        f(tipo_inmueble_fuente="Departamento", tipo_inmueble="cuarto", es_habitacion=True,
          titulo_anon="Se alquila habitacion para universitarios"),                                   # 6 habitacion (titulo)
        f(tipo_inmueble_fuente="Departamento", tipo_inmueble="cuarto", es_habitacion=False,
          titulo_anon="Departamento 3 dormitorios", descripcion_anon="incluye cuarto de servicio"),   # 7 departamento
        f(tipo_inmueble_fuente="habitación", tipo_inmueble="departamento", origen_dato="silver_amiga",
          tipo_inmueble_detalle="mini departamento"),                                                  # 8 silver minidepartamento
        f(tipo_inmueble_fuente="habitación", tipo_inmueble="cuarto", origen_dato="silver_amiga",
          tipo_inmueble_detalle="cuarto", es_habitacion=True),                                         # 9 silver cuarto
        f(tipo_inmueble_fuente=None, tipo_inmueble="casa"),                                            # 10 sin categoria
    ])
    cf, hom = cbf.tipos_usuario(df)
    assert list(hom) == ["casa", "departamento", "minidepartamento", "minidepartamento", "habitación", "cuarto",
                         "habitación", "departamento", "minidepartamento", "cuarto", "casa"], list(hom)
    assert list(cf) == ["casa", "departamento", "departamento", "departamento", "habitación", "habitación",
                        "habitación", "departamento", "departamento", "habitación", "casa"], list(cf)


if __name__ == "__main__":
    test_reglas()
    test_tipos()
    print("OK banos_por_defecto y tipos")
