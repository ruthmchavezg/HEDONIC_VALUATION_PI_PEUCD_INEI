"""Baños por tipo: propios, compartidos y de visita (medio baño).

Criterios
---------
* Baño de servicio (empleada, mucama): no se cuenta en ninguna variable.
* Baño de visita: "medio baño", "1/2 baño", "toilette", "baño de visita / invitados / social".
* Baño compartido: "baño compartido / común / externo / fuera de la habitación", "se comparte el baño",
  "comparten cocina, sala y baño", "baño que se comparte con una persona", "sin baño propio", "sin baño".
* Baño propio: "baño propio / privado / exclusivo / incorporado / en suite / dentro de la habitación",
  "habitación con baño", y la negación de lo compartido ("baño no compartido", "no se comparte el baño").

En una HABITACION o CUARTO el tipo de baño sale del TEXTO. El "Baños: 1" de la ficha del portal (o el
`banos_num` del silver) solo dice cuántos baños hay, no de quién son. Para esos anuncios se devuelve
`banos_tipo` = 'propio' | 'compartido' | 'mixto' | 'sin_dato':

    compartido -> banos_compartidos = n (1 si el texto no dice cuántos), banos_propios = 0
    propio     -> banos_propios     = n (1 si no dice cuántos),          banos_compartidos = 0
    mixto      -> el texto afirma ambos (p. ej. "una con baño propio y otra con baño compartido"):
                  no se decide, ambos quedan vacíos
    sin_dato   -> el texto no dice nada: aquí NO se decide. construir_base_final.py (después de unir los
                  duplicados, por si otro anuncio del mismo inmueble sí lo dice) aplica la regla por defecto:
                  si la ficha indica n >= 1 baños, se toma COMPARTIDO (compartidos = n, propios = 0).

En casas y departamentos no hay baños compartidos (en un departamento completo "los dormitorios comparten un
baño" sigue siendo del inquilino): el baño es PROPIO por defecto. El número de baños sale de las
CARACTERISTICAS ("Baños : 2"; "2.5" = 2 propios + 1 de visita) y solo si la ficha no lo trae, del título o de
la descripción ("2 baños", "baño propio"), retirando antes los de visita, servicio y compartidos.

Todas las reglas trabajan sobre texto ya normalizado (minúsculas, sin tildes, ñ -> n).
"""
from __future__ import annotations

import re

NUM_PALABRA = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3,
    "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10,
}
_NUM = r"(\d{1,2}|" + "|".join(NUM_PALABRA) + r")"
_B = r"banos?"
_ART = r"(?:(?:el|la|los|las|un|una|1|su|mi)\s+)?"
_AREAS = (r"(?:cocina|sala|comedor|lavanderia|lavadero|patio|terraza|jardin|azotea|"
          r"areas?\s+comun(?:es)?|ambientes?|servicios?)")

MAX_BANOS = 15      # un conteo mayor es casi seguro un error de lectura
TOPE_CONTEO = 6


# --------------------------------------------------------------------------------------- patrones
RE_SERVICIO = re.compile(
    rf"\b(?:{_NUM}\s*)?{_B}\s+(?:de\s+|del\s+|para\s+(?:la\s+)?)?"
    r"(?:servicio|empleada|mucama|trabajadora|personal\s+de\s+servicio)\b"
    rf"|\b(?:dormitorio|cuarto|habitacion)\s+de\s+servicio\s+con\s+{_B}\b"
)

RE_VISITA = re.compile(
    rf"\b{_NUM}\s*(?:medios?\s+{_B}|1\s*/\s*2\s*{_B})"
    rf"|\bmedios?\s+{_B}\b"
    rf"|\b(?:{_NUM}\s*)?{_B}\s+(?:de\s+|para\s+)?(?:visitas?|invitados|social(?:es)?|cortesia)\b"
    r"|\btoilet(?:te)?s?\b|\bhalf\s+bath(?:room)?s?\b"
)

# Negación explícita de lo compartido => evidencia de baño propio
RE_NO_COMPARTIDO = re.compile(
    rf"\b{_B}\s+(?:(?:propios?|privad[oa]s?|exclusiv[oa]s?)\s+)?(?:y\s+)?(?:no|nada)\s+(?:es\s+|esta\s+|son\s+)?compartid\w*"
    rf"|\bsin\s+(?:compartir|compartido)\s+(?:el\s+|un\s+)?{_B}\b"
    rf"|\bsin\s+{_B}\s+compartid\w*"
    rf"|\bno\s+(?:se\s+)?compart\w*\s+(?:(?:el|un|1|su|los|las)\s+)?{_B}\b"
)

_COMP = (r"(?:compartid[oa]s?|comun(?:es)?|en\s+comun|de\s+uso\s+(?:comun|compartido|general)|colectivos?|"
         r"externos?|exteriores?|generales?|afuera|"
         r"fuera\s+(?:de\s+)?(?:la|el|las|los)\s*(?:habitacion|cuarto|dormitorio)(?:es)?)")
_VERBO_COMP = r"compart(?:e|en|ir|iendo|imos|ido|idos|ida|idas|o|a)"

RE_COMPARTIDO = [
    # baño compartido / 2 baños compartidos / baño externo / baño fuera de la habitación
    re.compile(rf"\b(?:{_NUM}\s*)?{_B}\s+{_COMP}\b"),
    # baño y cocina compartidos
    re.compile(rf"\b{_B}\s+(?:y|e)\s+(?:la\s+|el\s+)?\w+\s+compartid\w+"),
    # se comparte el baño / comparte baño con ... / comparten un baño / compartir el baño
    re.compile(rf"\b{_VERBO_COMP}\s+(?:(?:el|un|1|los|las|su|mi|solo|solamente|unico|mismo|"
               rf"con\s+(?:una?|otra|otro|dos|tres|\d+)\s+\w+)\s+){{0,2}}{_B}\b"),
    # comparten cocina, sala y baño
    re.compile(rf"\b{_VERBO_COMP}\s+{_ART}(?:{_AREAS}\s*(?:,|y|e)\s*{_ART}){{1,3}}{_B}\b"),
    # baño que se comparte / baño a compartir
    re.compile(rf"\b{_B}\s+(?:completos?\s+|y\s+(?:la\s+|el\s+)?\w+\s+)?(?:que\s+)?(?:se\s+)?{_VERBO_COMP}\b"),
    re.compile(rf"\b{_B}\s+(?:a|por|para)\s+compartir\b"),
    # uso compartido del baño
    re.compile(rf"\buso\s+(?:compartido|comun)\s+(?:del?|de\s+los)\s+{_B}\b"),
    # áreas compartidas: cocina, sala y baño / los espacios son compartidos (cocina, sala, baños, patios)
    re.compile(rf"\b(?:areas?|espacios|ambientes)\s+(?:(?:son|estan)\s+)?(?:comun(?:es)?|compartid\w+)\s*[:(\-]\s*"
               rf"(?:[a-z]+\s*,?\s*(?:y\s+|e\s+)?){{0,8}}?{_B}\b"),
]
# Sin baño propio => el baño es de uso común (no lleva negación previa: ya es una negación)
RE_SIN_BANO = re.compile(
    rf"\bsin\s+{_B}\s+(?:propio|privado|incorporado|interno|independiente)s?\b"
    rf"|\bno\s+(?:tiene|incluye|cuenta\s+con|hay)\s+{_B}\s+(?:propio|privado|incorporado|interno)s?\b"
    rf"|\bsin\s+{_B}\b(?!\s+(?:de\s+|para\s+)?(?:visitas?|invitados|servicio|empleada)|\s+compartid)"
)

RE_PROPIO = re.compile(
    rf"\b(?:{_NUM}\s*)?{_B}\s+(?:completos?\s+)?(?:propios?|privad[oa]s?|exclusiv[oa]s?|incorporad[oa]s?|"
    r"internos?|individuales?|independientes?|en\s+suite|"
    r"dentro\s+(?:de\s+)?(?:la|el|su)\s+(?:habitacion|cuarto|dormitorio)|"
    r"en\s+(?:la|el)\s+(?:habitacion|cuarto|dormitorio))\b"
    rf"|\b(?:propio|privado|exclusivo)\s+{_B}\b"
)
# "habitación con baño", "cuarto amoblado con baño", "habitación + baño", "baño completo incluido":
# afirman baño propio, pero más débil que lo explícito
RE_PROPIO_DEBIL = re.compile(
    rf"\b(?:habitacion(?:es)?|cuarto|dormitorio|room)\s+(?:[a-z]+\s+){{0,3}}?con\s+(?:su\s+|un\s+|1\s+)?{_B}\b"
    # "habitación + baño", "habitación y baño"
    rf"|\b(?:habitacion|cuarto|dormitorio)\s*(?:\+|y|e|mas)\s*(?:un\s+|su\s+|1\s+)?{_B}\b"
    # "un baño completo incluido"
    rf"|\b{_B}\s+(?:completos?\s+)?incluid[oa]s?\b"
)

# Conteo de propios cuando NO es habitación (comportamiento histórico)
RE_CONTEO_PROPIOS = re.compile(
    rf"\b{_NUM}\s*(?:banos?(?:\s+completos?)?|duchas?)\b"
    rf"|\b{_B}\s*[:\-]\s*(\d{{1,2}})\b"
    rf"|\b{_B}\s+(?:propios?|privados?|independientes?|en\s+suite|incorporados?|"
    r"dentro\s+de\s+(?:la\s+)?habitacion)\b"
)
RE_DECIMAL = re.compile(r"\b(\d{1,2})[.,]5\s*banos?\b")

# Negación inmediata antes: "sin baño", "no tiene baño", "no cuenta con baño", "ni baño", "no se comparte"
RE_NEG_PREVIA = re.compile(
    r"(?:\bsin\s+(?:(?:un|1|el|su|ningun|otro)\s+)?"
    r"|\b(?:no|ni|tampoco)\s+(?!solo\b)(?:(?:se|le)\s+)?"
    r"(?:(?:tiene|tienen|hay|cuenta|cuentan|incluye|incluyen|posee|dispone|ofrece|existe|es|son)\s+)?"
    r"(?:con\s+)?(?:(?:un|1|el|su|ningun|ese)\s+)?)$"
)
RE_ETIQUETA_NO = re.compile(r"^\s*[:\-]\s*(?:no|ninguno|nada)\b")
# Etiqueta de la ficha del portal: "Baños : 3" (o "Baños : 2.5"). Va antes de retirar los baños de visita
# porque en "Baños : 3 Baño de visita : 0" el 3 es de la etiqueta "Baños", no de la de visita.
RE_ETIQUETA_BANOS = re.compile(rf"\b{_B}\s*:\s*(\d{{1,2}})([.,]5)?\b")
RE_MEDIO_ANTES = re.compile(r"(?:medios?|1\s*/\s*2)\s*$")
RE_ETIQUETA_NUM = re.compile(r"^\s*[:\-]\s*(\d{1,2})\b")


# ------------------------------------------------------------------------------------- utilidades
def _valor(tok: str | None) -> int | None:
    if not tok:
        return None
    return int(tok) if tok.isdigit() else NUM_PALABRA.get(tok)


def _prefijo(texto: str, pos: int, ancho: int = 60) -> str:
    """Texto de la misma cláusula que precede a `pos`."""
    previo = texto[max(0, pos - ancho):pos]
    corte = max((previo.rfind(c) for c in ".;:|!?()[],"), default=-1)
    return previo[corte + 1:] if corte >= 0 else previo


def _hallazgos(regex: re.Pattern, texto: str):
    """Coincidencias de `regex`: (afirmadas, negadas), cada una como (n | None, fragmento, plural).

    Una coincidencia es negada si la precede "sin / no tiene / ni ..." o la sigue una etiqueta
    ": no" / ": 0".  Una etiqueta ": 2" fija la cantidad.
    """
    afirmadas, negadas = [], []
    for m in regex.finditer(texto):
        n = next((_valor(g) for g in m.groups() if g and _valor(g) is not None), None)
        negado = bool(RE_NEG_PREVIA.search(_prefijo(texto, m.start())))
        cola = texto[m.end():m.end() + 12]
        if RE_ETIQUETA_NO.match(cola):
            negado = True
        else:
            etiqueta = RE_ETIQUETA_NUM.match(cola)
            if etiqueta:
                n = int(etiqueta.group(1))
                negado = negado or n == 0
        fragmento = m.group(0).strip()
        plural = bool(re.search(r"\bbanos\b", fragmento))
        (negadas if negado else afirmadas).append((n, fragmento, plural))
    return afirmadas, negadas


def _cantidad(hallazgos, total: int | None) -> int:
    """Cantidad de baños de un tipo: el número escrito; si es plural sin número, el total (si es >= 2) o 2."""
    explicitos = [n for n, _, _ in hallazgos if n]
    if explicitos:
        return min(max(explicitos), TOPE_CONTEO)
    if any(plural for _, _, plural in hallazgos):
        return total if total and total >= 2 else 2
    return 1


def _analizar_texto(texto: str, es_ficha: bool = False) -> dict:
    """Evidencia de baños en un solo texto. Devuelve los hallazgos y el texto sin los tipos ya contados."""
    etiqueta = None
    if es_ficha:
        for m in RE_ETIQUETA_BANOS.finditer(texto):
            if RE_MEDIO_ANTES.search(texto[max(0, m.start() - 8):m.start()]):
                continue                                          # "medio baño : 1" es la etiqueta de visita
            etiqueta = (int(m.group(1)), bool(m.group(2)))      # (baños, trae medio baño)
            texto = texto[:m.start()] + " " + texto[m.end():]
            break
    t = RE_SERVICIO.sub(" ", texto)

    visita, _ = _hallazgos(RE_VISITA, t)
    t = RE_VISITA.sub(" ", t)

    propio, comp = [], []                         # evidencia de baño propio / compartido (afirmada)
    no_comp, _ = _hallazgos(RE_NO_COMPARTIDO, t)  # "no compartido" prueba baño propio
    propio += no_comp
    t = RE_NO_COMPARTIDO.sub(" ", t)

    for regex in RE_COMPARTIDO:
        afirmadas, negadas = _hallazgos(regex, t)
        comp += afirmadas
        propio += negadas                         # "no se comparte el baño" => propio
        t = regex.sub(" ", t)

    sin = [(1, m.group(0), False) for m in RE_SIN_BANO.finditer(t)]
    comp += sin                                   # "sin baño propio" => se usa un baño común
    t = RE_SIN_BANO.sub(" ", t)

    afirmadas, negadas = _hallazgos(RE_PROPIO, t)
    propio_explicito = propio + afirmadas
    comp += negadas                               # "no tiene baño propio" => compartido
    debil, _ = _hallazgos(RE_PROPIO_DEBIL, t)     # se evalúa tras retirar lo compartido

    return {"visita": visita, "compartido": comp, "propio": propio_explicito, "debil": debil, "resto": t,
            "etiqueta": etiqueta}


def _primero(analisis: list[dict], clave: str):
    """Hallazgos del texto de mayor prioridad (título > características > descripción) que los tenga."""
    for a in analisis:
        if a[clave]:
            return a[clave]
    return []


def _fragmento(hallazgos) -> str:
    return hallazgos[0][1][:50] if hallazgos else ""


# ----------------------------------------------------------------------------------- API pública
def extraer_banos(
    fuentes: list[tuple[str, str]],
    es_habitacion: bool = False,
    total: int | None = None,
) -> dict:
    """Baños propios, compartidos y de visita de un anuncio.

    fuentes        [(nombre, texto_normalizado)] en orden de prioridad (título, características, descripción)
    es_habitacion  True si el anuncio es una habitación/cuarto (tipo del texto o de la fuente)
    total          cantidad de baños de la ficha (campo `banos`); solo orienta el plural sin número

    Devuelve banos_propios, banos_compartidos, banos_visita, banos_tipo (solo habitaciones) y
    banos_evidencia (frase que decidió el tipo; sirve para auditar).
    """
    analisis = [_analizar_texto(texto, nombre == "caracteristicas") for nombre, texto in fuentes if texto]
    libre = [_analizar_texto(texto) for nombre, texto in fuentes if texto and nombre != "caracteristicas"]
    ficha = [_analizar_texto(texto, True) for nombre, texto in fuentes if texto and nombre == "caracteristicas"]
    out = {
        "banos_propios": None, "banos_compartidos": None, "banos_visita": None,
        "banos_tipo": None, "banos_evidencia": None,
    }

    # --- baños de visita / medio baño (igual para todos los tipos)
    visita = _primero(analisis, "visita")
    if visita:
        out["banos_visita"] = min(max([n for n, _, _ in visita if n] or [1]), TOPE_CONTEO)

    # --- habitaciones y cuartos: el tipo sale del texto
    if es_habitacion:
        # El texto que escribe el anunciante (título y descripción) manda sobre la ficha del portal: la casilla
        # genérica "Baño propio" de la ficha suele estar marcada aunque la descripción diga "baño compartido".
        # La ficha solo decide cuando el texto libre no dice nada.
        grupo = libre if any(a[k] for a in libre for k in ("compartido", "propio", "debil")) else ficha
        analisis = grupo
        comp = [h for a in grupo for h in a["compartido"]]
        propio = [h for a in grupo for h in a["propio"]]
        debil = [h for a in grupo for h in a["debil"]]

        if comp and propio:
            out["banos_tipo"] = "mixto"
            out["banos_evidencia"] = f"compartido:'{_fragmento(comp)}' + propio:'{_fragmento(propio)}'"
        elif comp:
            out["banos_tipo"] = "compartido"
            out["banos_compartidos"] = _cantidad(_primero(analisis, "compartido"), total)
            out["banos_propios"] = 0
            out["banos_evidencia"] = f"compartido:'{_fragmento(comp)}'"
        elif propio or debil:
            out["banos_tipo"] = "propio"
            fuente = _primero(analisis, "propio") or _primero(analisis, "debil")
            out["banos_propios"] = _cantidad(fuente, total)
            out["banos_compartidos"] = 0
            out["banos_evidencia"] = f"propio:'{_fragmento(propio or debil)}'"
        else:
            out["banos_tipo"] = "sin_dato"
        return out

    # --- casas y departamentos: no hay baños compartidos; el baño es propio y el número sale primero de las
    # características (etiqueta "Baños : n"), luego del título y de la descripción
    for a in ficha + libre:
        etiqueta = a["etiqueta"]
        if etiqueta is not None:
            propios, medio = etiqueta
            if medio:
                out["banos_visita"] = out["banos_visita"] or 1
        else:
            t = a["resto"]
            decimal = RE_DECIMAL.search(t)
            if decimal:
                propios = int(decimal.group(1))
                out["banos_visita"] = out["banos_visita"] or 1
                t = RE_DECIMAL.sub(" ", t)
            else:
                m = RE_CONTEO_PROPIOS.search(t)
                propios = next((_valor(g) for g in m.groups() if g and _valor(g) is not None), 1) if m else None
        if propios is not None and 0 <= propios <= MAX_BANOS:
            out["banos_propios"] = propios
            break
    return out
