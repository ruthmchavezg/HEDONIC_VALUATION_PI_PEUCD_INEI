"""Pruebas de src/pi_nlp/banos.py.  Ejecutar:  python tests/test_banos.py   (o pytest tests/)

Cada caso: (descripcion, titulo, caracteristicas, es_habitacion, total_ficha,
            (banos_tipo, banos_propios, banos_compartidos, banos_visita)).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pi_nlp.banos import extraer_banos  # noqa: E402
from pi_nlp.texto import normalizar  # noqa: E402


def clasificar(desc, titulo="", car="", hab=True, total=None):
    fuentes = [("titulo", normalizar(titulo)), ("caracteristicas", normalizar(car)),
               ("descripcion", normalizar(desc))]
    r = extraer_banos(fuentes, es_habitacion=hab, total=total)
    return r["banos_tipo"], r["banos_propios"], r["banos_compartidos"], r["banos_visita"]


casos=[
 ("SE ALQUILA HABITACION SIN AMOBLAR CON LAVADERO PRIVADO Y SE COMPARTE EL BAÑO CON UNA PERSONA QUE ES PUBLICISTA, INCLUYE LUZ, AGUA", "Habitacion Pueblo", "Baños : 1", True,1, ("compartido",0,1,None)),
 ("Cuentas con VISTA EXTERNA. (Baño compartido con una sola persona) <MONTO> es el pago", "Hermosa habitación", "Baños : 1", True,1, ("compartido",0,1,None)),
 ("Alquiler de habitación amplia 13 m2 con baño compartido a <MONTO_ALQUILER> en 3er piso", "Pueblo Libre", "Baños : 1", True,1, ("compartido",0,1,None)),
 ("Habitación amoblada con baño propio, ingreso independiente", "", "Baños : 1", True,1, ("propio",1,0,None)),
 ("Alquilo habitación amoblada con baño y ducha", "Habitación con baño", "", True,None, ("propio",1,0,None)),
 ("Alquilo habitación amoblada en Surco, cerca al metro", "Habitación en Surco", "Baños : 1", True,1, ("sin_dato",None,None,None)),
 ("Habitación con baño no compartido", "", "", True,None, ("propio",1,0,None)),
 ("Habitación sin baño propio, cocina y lavandería comunes", "", "", True,None, ("compartido",0,1,None)),
 ("Habitación en casa, comparte baño con 2 personas más", "", "", True,None, ("compartido",0,1,None)),
 ("Comparto departamento con una chica; tiene baño propio", "", "", True,None, ("propio",1,0,None)),
 ("Habitaciones con baños compartidos", "", "", True,3, ("compartido",0,3,None)),
 ("Hay 2 habitaciones: una con baño propio y otra con baño compartido", "", "", True,None, ("mixto",None,None,None)),
 ("Habitación con baño privado y medio baño de visita", "", "", True,None, ("propio",1,0,1)),
 ("No se comparte el baño. Habitación independiente", "", "", True,None, ("propio",1,0,None)),
 ("Habitación con cocina y baño compartidos con el resto de inquilinos", "", "", True,None, ("compartido",0,1,None)),
 ("Habitación con baño privado, cocina compartida", "", "", True,None, ("propio",1,0,None)),
 ("Se alquila cuarto. Baño compartido: No. Baño propio: Si", "", "", True,None, ("propio",1,0,None)),
 ("Cuarto amoblado. Baño compartido : Si", "", "", True,None, ("compartido",0,1,None)),
 ("Habitación amoblada, baño a compartir con un compañero", "", "", True,None, ("compartido",0,1,None)),
 ("Habitación sin baño. Baño fuera de la habitación", "", "", True,None, ("compartido",0,1,None)),
 ("Habitación independiente con luminarias con lavadero privado, griferia dentro de la habitacion, baño con una rapiducha", "", "Baños : 1", True,1, ("sin_dato",None,None,None)),
 ("Habitación con baño de servicio y entrada independiente", "", "Baños : 1", True,1, ("sin_dato",None,None,None)),
 ("Habitación comparten cocina, sala y baño entre 3 personas", "", "", True,None, ("compartido",0,1,None)),
 ("Departamento 3 dormitorios, 2 baños completos y 1 baño de visita", "", "", False,None, (None,2,None,1)),
 ("Casa de 4 dormitorios, 3.5 baños", "", "", False,None, (None,3,None,1)),
 ("Departamento con 2 dormitorios que comparten un baño", "", "Baños : 1", False,1, (None,1,None,None)),
 ("Departamento sin baño de visita, 2 baños", "", "", False,None, (None,2,None,None)),
 ("Departamento con baño de servicio, 2 baños y toilette", "", "", False,None, (None,2,None,1)),
 ("Dpto 2 baños", "", "Baños : 3 Baño de visita : 0", False,3, (None,3,None,None)),
 ("Habitación con baño compartido con una persona", "", "Ambientes Patio Baño Propio Comedor Desagüe Baños : 1", True,1, ("compartido",0,1,None)),
 ("Habitación amoblada", "", "Ambientes Patio Baño Propio Desagüe", True,1, ("propio",1,0,None)),
 ("Habitación amplia. Baño común derecho a uso de áreas comunes (cocina, lavandería, terraza)", "", "", True,None, ("compartido",0,1,None)),
 ("Áreas comunes; cocina completa, baño completo que se comparte con otro joven, además un baño de visita", "", "", True,None, ("compartido",0,1,1)),
 ("Los espacios son compartidos (cocina, sala y comedor grande, baños, patios y lavandería).", "", "", True,2, ("compartido",0,2,None)),
 ("Alquilo habitación + baño propio en 1er piso", "", "", True,None, ("propio",1,0,None)),
 ("Habitación. Un baño completo incluido, con agua caliente.", "", "", True,None, ("propio",1,0,None)),
 # --- casas y departamentos: el baño es propio y el numero sale de las caracteristicas
 ("Departamento con 2 baños y 1 baño de visita", "", "Baños : 3 Baño de visita : 1", False,3, (None,3,None,1)),
 ("Dormitorio principal con baño propio cada uno", "", "Baños : 3", False,3, (None,3,None,None)),
 ("Los dormitorios comparten un baño. Dormitorio principal con baño incorporado", "", "Baños : 2", False,2, (None,2,None,None)),
 ("Departamento amplio y luminoso", "Departamento en Surco", "Baños : 2", False,2, (None,2,None,None)),
 ("Departamento amplio y luminoso", "", "Baños : 2.5", False,2, (None,2,None,1)),
 ("Departamento 2.5 baños, cochera", "", "", False,2, (None,2,None,1)),
 ("Departamento con 3 baños", "Dpto 2 baños", "", False,2, (None,2,None,None)),
 ("Casa de 3 pisos", "", "Baños : 4 Baño de visita : 0", False,4, (None,4,None,None)),
 ("Departamento", "", "tot.: 200 m² | cub.: 200 m² | baños: 2 | estac.: 1 | medio baño: 1 | antigüedad: 26", False,2, (None,2,None,1)),
 ("Departamento", "", "medio baño: 1 | baños: 2 | estac.: 1", False,2, (None,2,None,1)),
 # --- habitaciones: lo que el texto no dice queda sin_dato (la regla por defecto se aplica en el script final)
 ("Habitación amoblada, zona tranquila", "", "Baños : 2", True,2, ("sin_dato",None,None,None)),
]


def test_casos():
    fallos = [(c[0][:70], clasificar(*c[:5]), c[5]) for c in casos if clasificar(*c[:5]) != c[5]]
    assert not fallos, fallos


# (titulo, categoria del portal, es habitacion?)  -- "4 habitaciones" cuenta dormitorios, no es una habitacion
CASOS_HABITACION = [
    ("Alquiler Dúplex Remodelado 4 Habitaciones 2.5 Baños", "departamento", False),
    ("Departamento 3 habitaciones", "departamento", False),
    ("Se Alquila Habitacion Para Universitarios", "departamento", True),
    ("Habitaciones amobladas en Surco", "departamento", True),
    ("Cuarto en alquiler", "departamento", True),
    ("Alquiler en Surco", "habitacion", True),
    ("Casa de 5 dormitorios", "casa", False),
]


def test_es_habitacion():
    from pi_nlp.extraccion import es_habitacion  # noqa: E402
    fallos = [(t, f) for t, f, esperado in CASOS_HABITACION
              if es_habitacion("departamento", f, normalizar(t)) != esperado]
    assert not fallos, fallos


if __name__ == "__main__":
    test_es_habitacion()
    malos = 0
    for caso in casos:
        obtenido = clasificar(*caso[:5])
        ok = obtenido == caso[5]
        malos += not ok
        print("OK " if ok else "XX ", obtenido, "" if ok else f"esperado {caso[5]} <- {caso[0][:70]}")
    print(f"fallos: {malos} de {len(casos)}")
    sys.exit(1 if malos else 0)
