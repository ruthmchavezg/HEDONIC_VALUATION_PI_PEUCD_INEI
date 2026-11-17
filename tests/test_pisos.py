"""Pruebas de src/pi_nlp/pisos.py.  Ejecutar:  python tests/test_pisos.py   (o pytest tests/)

Cada caso: (titulo, caracteristicas, descripcion, tipo, (piso_departamento, cant_pisos)).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pi_nlp.pisos import extraer_pisos  # noqa: E402
from pi_nlp.texto import normalizar  # noqa: E402

casos = [
    # --- habitaciones: ficha del portal y texto (capturas del usuario)
    ("Habitacion privada lavadero privado con bano compartido",
     "Caseta de guardia Jardín(es) Terraza Seguridad Piso en el que se encuentra : 1 Intercomunicador",
     "SE ALQUILA HABITACION SIN AMOBLAR CON LAVADERO PRIVADO Y SE COMPARTE EL BAÑO", "cuarto", (1, None)),
    ("Alquiler de habitación", "", "Habitación ubicada en el 2.º piso de un departamento, baño compartido", "cuarto", (2, None)),
    ("Alquilo habitación", "", "Se ubica en el 1er piso, cerca al parque", "cuarto", (1, None)),
    ("Habitación en 3er piso", "", "Con ascensor", "cuarto", (3, None)),
    ("Solo señorita habitación", "", "Habitación en tercer piso con ventana", "cuarto", (3, None)),
    ("Alquiler habitaciones", "", "1er piso: S/ 600 con baño. 2do piso: S/ 700", "cuarto", (None, None)),
    # --- departamentos: ficha
    ("Departamento en Surco", "Número de pisos : 12 Piso en el que se encuentra : 9", "", "departamento", (9, 12)),
    ("Departamento", "Número de pisos : 0 Piso en el que se encuentra : 4", "", "departamento", (4, None)),
    ("Departamento", "Número de pisos : 1 Piso en el que se encuentra : 5", "", "departamento", (5, None)),   # inconsistente
    ("Departamento", "Número de pisos : 5", "", "departamento", (None, 5)),
    ("Departamento", "Pisos del edificio : 8 Piso de la unidad : 3", "", "departamento", (3, 8)),
    # --- departamentos: texto
    ("Duplex Alquiler en 5 Piso Surco", "", "", "departamento", (5, None)),
    ("Departamento amplio", "", "Ubicado en el piso 15, vista al mar. Edificio de 20 pisos con ascensor", "departamento", (15, 20)),
    ("Departamento", "", "Área total: 58 m² piso: 13 con vista a la ciudad", "departamento", (13, None)),
    ("Departamento", "", "Cuenta con 3 dormitorios en piso 2 dormitorios amplios", "departamento", (None, None)),
    ("Departamento", "", "Piso laminado en dormitorios, cocina equipada", "departamento", (None, None)),
    ("Departamento", "", "Departamento de 1 piso con terraza", "departamento", (None, None)),
    ("Departamento", "", "Piso N° 4 con balcón. Torre de 18 niveles", "departamento", (4, 18)),
    ("Departamento", "", "Quinto piso con ascensor, edificio de 10 pisos", "departamento", (5, 10)),
    ("Departamento", "", "Dúplex: primer piso sala y cocina, segundo piso dormitorios", "departamento", (None, None)),
    ("Departamento", "", "Se encuentra en el último piso. Edificio de 7 pisos", "departamento", (7, 7)),
    ("Departamento", "", "Terraza en el último piso del edificio", "departamento", (None, None)),
    ("Departamento", "", "10 pisos en el edificio, ascensor, piso 6", "departamento", (6, 10)),
    ("Departamento", "", "Edificio nuevo de 12 pisos, ubicado en el 3° piso", "departamento", (3, 12)),
    ("Departamento", "", "Piso 7. Edificio de 5 pisos", "departamento", (7, None)),            # edificio < piso: inconsistente
    ("Depa", "", "Alquilo en el 4to piso, 2do ascensor", "departamento", (4, None)),
    # --- casas: piso = 0, cant_pisos = niveles de la casa
    ("Casa en La Molina", "Número de pisos : 3", "", "casa", (0, 3)),
    ("Casa de 2 pisos", "", "Casa de dos pisos con jardín y cochera", "casa", (0, 2)),
    ("Casa", "", "Casa de un solo piso, 4 dormitorios", "casa", (0, 1)),
    ("Casa", "Niveles construidos : 2", "", "casa", (0, 2)),
    ("Casa", "", "Casa amplia con jardín", "casa", (0, None)),
    ("Casa", "", "Casa de 3 plantas, frente a parque. Piso porcelanato", "casa", (0, 3)),
    ("Casa", "Número de pisos : 0", "", "casa", (0, None)),
    # --- menciones que NO son el piso de la unidad
    ("Departamento", "", "Número de departamentos por piso: 4. Año de construcción: 2020", "departamento", (None, None)),
    ("Departamento", "", "Edificio con zonas comunes en el 1er piso, gimnasio y recepción", "departamento", (None, None)),
    ("Departamento", "", "Ubicado en piso 14 con vista externa. Gimnasio (piso 1), parrilla (piso 20)", "departamento", (14, None)),
    ("Departamento", "", "Es un edificio que tiene en el 1er piso áreas comerciales, tiendas", "departamento", (None, None)),
    ("Departamento", "", "Habitaciones: 2 + 1 estudio piso: 9 vive en Barranco", "departamento", (9, None)),
    ("Departamento", "", "Terraza en el 5to piso con ascensor privado", "departamento", (None, None)),   # ¿terraza del edificio? no se adivina
    ("Departamento", "", "Entrada independiente en el 1er piso, de la calle a tu habitación", "cuarto", (1, None)),
    ("Departamento", "", "Habitaciones en 2do y 3er piso, ambas independientes", "cuarto", (None, None)),
    ("Departamento", "", "Ubicada en el segundo piso de un inmueble sobre la Av. Salaverry", "cuarto", (2, None)),
    ("Departamento", "", "Parrilla (piso 20) y coworking (piso 3). El departamento está en el piso 8", "departamento", (8, None)),
    ("Departamento", "", "Dpto. de 90m2 (5to.piso) con vista interna, ideal para pareja", "departamento", (5, None)),
    ("Departamento", "", "Área total: 70 m² (7mo piso) 2 dormitorios", "departamento", (7, None)),
    ("Departamento", "", "Viene con una cochera techada en primer piso. Áreas comunes de piscina", "departamento", (None, None)),
    ("Departamento", "", "Cochera ubicada en el primer piso, justo en la entrada. Departamento en piso 6", "departamento", (6, None)),
]


def clasificar(t, e, d, tipo):
    r = extraer_pisos(normalizar(t), normalizar(e), normalizar(d), tipo)
    return r["piso_departamento"], r["cant_pisos"]


def test_casos():
    fallos = [(c[0][:40], clasificar(*c[:4]), c[4]) for c in casos if clasificar(*c[:4]) != c[4]]
    assert not fallos, fallos


if __name__ == "__main__":
    malos = 0
    for caso in casos:
        obtenido = clasificar(*caso[:4])
        ok = obtenido == caso[4]
        malos += not ok
        print("OK " if ok else "XX ", obtenido, "" if ok else f"esperado {caso[4]} <- {caso[0][:40]} | {caso[2][:70]}")
    print(f"fallos: {malos} de {len(casos)}")
    sys.exit(1 if malos else 0)
