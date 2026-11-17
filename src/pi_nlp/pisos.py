"""Pisos: en qué piso está el inmueble y cuántos pisos tiene la casa o el edificio.

Variables
---------
piso_departamento  Piso en el que se encuentra el DEPARTAMENTO o la HABITACION (1 = primer piso).
                   En una CASA vale siempre 0. Vacío si el anuncio no lo dice o lo dice de forma ambigua.
cant_pisos         Cantidad TOTAL de pisos: los niveles de la casa, o los pisos del edificio que contiene
                   el departamento o la habitación. Vacío si no se informa.

Criterios
---------
* Prioridad de fuentes: ficha del portal (características) > título > descripción.
* Ficha del portal: "Piso en el que se encuentra : 3" es el piso de la unidad y "Número de pisos : 12" son
  los pisos del edificio (en los datos de Urbania/Adondevivir el piso de la unidad es <= "Número de pisos" en
  el 98 % de los casos). "Número de pisos : 0" significa que no se informó.
* Piso de la unidad en texto libre: "1er piso", "2.º piso", "3° piso", "segundo piso", "piso 5", "piso: 13",
  "piso N° 4", "ubicado en el 5 piso", "se encuentra en el último piso" (si se conoce cant_pisos).
  No se toman "de 1 piso", "piso 2 dormitorios" ni "piso laminado".
* Si el texto libre menciona varios pisos distintos ("1er piso: S/ 600, 2do piso: S/ 700", dúplex con
  "primer piso ... segundo piso") es ambiguo: no se adivina.
* cant_pisos en texto: "edificio de 12 pisos", "torre de 20 niveles", "12 pisos en el edificio",
  "casa de 3 pisos", "casa de un solo piso". Si cant_pisos es menor que el piso de la unidad, el dato es
  inconsistente y cant_pisos se descarta.

Los textos llegan normalizados (minúsculas, sin tildes: º -> o, ñ -> n).
"""
from __future__ import annotations

import re

NUM_PALABRA = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}
ORDINALES = {
    "primer": 1, "primero": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercer": 3, "tercero": 3,
    "tercera": 3, "cuarto": 4, "cuarta": 4, "quinto": 5, "quinta": 5, "sexto": 6, "sexta": 6,
    "septimo": 7, "septima": 7, "octavo": 8, "octava": 8, "noveno": 9, "novena": 9,
    "decimo": 10, "decima": 10, "undecimo": 11, "duodecimo": 12,
}
_ORD = "|".join(ORDINALES)
_NUM = r"(\d{1,2}|" + "|".join(NUM_PALABRA) + r")"
_UNIDADES = (r"m2|m²|mt|mts|metros?|dormitorios?|dorms?\b|hab\b|habitaciones?|banos?|soles|s/|\$|usd|"
             r"ambientes?|cuartos?|personas?|plazas?")

PISO_MAX = 60          # piso de una unidad
CANT_MAX_EDIFICIO = 80
CANT_MAX_CASA = 8

# --------------------------------------------------------------------- piso donde está la unidad
RE_PISO_ETIQUETA = re.compile(
    r"piso\s+en\s+el\s+que\s+se\s+encuentra\s*[:\-]?\s*(\d{1,2})\b"
    r"|piso\s+de\s+la\s+unidad\s*[:\-]?\s*(\d{1,2})\b"
    r"|piso\s+del\s+(?:departamento|inmueble)\s*[:\-]?\s*(\d{1,2})\b"
)
RE_PISO_TEXTO = [
    # 1er piso, 2do piso, 3° piso, 2.º piso  (la terminación va pegada al número)
    re.compile(r"(?<![a-z0-9])(\d{1,2})\.?(?:er|ro|do|to|vo|mo|no|ero|ra|da|ta|va|a|o|[°º])\.?\s*piso\b"),
    # primer piso, segundo piso ... / piso primero
    re.compile(rf"\b({_ORD})\s+piso\b"),
    re.compile(rf"\bpiso\s+({_ORD})\b"),
    # piso 5, piso: 13, piso N° 4, piso #3  (sin unidades detrás: "piso 2 dormitorios")
    re.compile(
        r"\bpiso\s*(?:(?:n[°ºo]?\.?|nro\.?|numero|num\.?|#)\s*)?[:\-]?\s*(\d{1,2})\b(?![.,]\d)"
        rf"(?!\s*(?:{_UNIDADES}))"
    ),
    # ubicado en el 5 piso, en 5 piso (con preposición: "de 1 piso" no cuenta)
    re.compile(r"\b(?:en|ubicado\s+en|ubicada\s+en|el|del|al)\s+(?:el\s+)?(\d{1,2})\s*piso\b"),
]
# Contexto que NO habla de la unidad: pisos de áreas comunes ("zonas comunes en el 1er piso", "gimnasio (piso 1)"),
# "departamentos por piso : 4" y "(piso 5)" entre paréntesis.
RE_AMENIDAD = (r"(?:comunes?|comerciales?|tiendas?|locales?|recepcion|lobby|hall|sum|gimnasio|piscina|parrillas?|"
               r"coworking|lavanderia|estacionamientos?|cafeteria|restaurante|spa|sauna|business\s+center)")
RE_AMENIDAD_ANTES = re.compile(rf"\b{RE_AMENIDAD}\b[^.;|]{{0,25}}$")
RE_AMENIDAD_DESPUES = re.compile(rf"^\s*(?:de\s+\w+\s+)?(?:(?:areas?|zonas?)\s+)?{RE_AMENIDAD}\b")
# "cochera ubicada en el primer piso", "cochera techada en primer piso": el piso es de OTRA cosa, no de la unidad
RE_OTRA_COSA = re.compile(
    r"\b(?:cocheras?|estacionamientos?|garajes?|parqueos?|depositos?|bodegas?|tiendas?|locales?|piscina|gimnasio|"
    r"lavanderia|sum|azotea|terraza)\s+(?:[a-z]+\s+){0,3}?(?:en|al)\s+(?:el\s+|la\s+)?$"
)
# El anuncio dice "el departamento está / se ubica / se encuentra en el ... piso": referencia a la unidad
RE_UBICACION = re.compile(
    r"\b(?:ubicad[oa]s?|situad[oa]s?|se\s+encuentra|se\s+ubica|queda|esta|encuentra|nivel)\s+"
    r"(?:[a-z]+\s+){0,2}?(?:en|al|a)\s+(?:el\s+|la\s+)?$"
)
# Enumeraciones: "2do y 3er piso", "primer o segundo piso" -> dos pisos distintos (ambiguo)
_SUFIJO = r"\.?(?:er|ro|do|to|vo|mo|no|ero|ra|da|ta|va|a|o|[°º])\.?"
RE_PISO_ENUM = [
    re.compile(rf"(?<![a-z0-9])(\d{{1,2}}){_SUFIJO}\s*(?:y|e|o|,|/|-)\s*(\d{{1,2}}){_SUFIJO}\s*piso\b"),
    re.compile(rf"\b({_ORD})\s*(?:y|e|o|,|/)\s*({_ORD})\s+piso\b"),
]
RE_ULTIMO_PISO = re.compile(r"\b(?:ubicad[oa]|se\s+(?:encuentra|ubica)|esta)\s+en\s+(?:el\s+)?ultimo\s+piso\b")

# ------------------------------------------------------------------ cantidad total de pisos
RE_CANT_ETIQUETA = re.compile(
    r"numero\s+de\s+pisos\s*[:\-]?\s*(\d{1,2})\b"
    r"|pisos?\s+totales\s*[:\-]\s*(\d{1,2})\b"
    r"|total\s+de\s+pisos\s*[:\-]?\s*(\d{1,2})\b"
    r"|cantidad\s+de\s+pisos\s*[:\-]?\s*(\d{1,2})\b"
    r"|pisos\s+(?:del\s+edificio|en\s+el\s+edificio|de\s+la\s+casa)\s*[:\-]?\s*(\d{1,2})\b"
    r"|numero\s+de\s+niveles\s*[:\-]?\s*(\d{1,2})\b"
)
RE_CANT_NIVELES_CASA = re.compile(r"niveles\s+construidos\s*[:\-]?\s*(\d{1,2})\b")
_EDIF = r"(?:edificio|torre|condominio|residencial|multifamiliar|proyecto|conjunto)"
RE_CANT_EDIFICIO = [
    re.compile(rf"\b{_EDIF}\s+(?:[a-z]+\s+){{0,3}}?(?:de|con|cuenta\s+con|tiene|posee)\s+{_NUM}\s+"
               r"(?:pisos|niveles|plantas)\b"),
    re.compile(rf"\b{_NUM}\s+(?:pisos|niveles|plantas)\s+(?:en\s+)?(?:el\s+)?{_EDIF}\b"),
]
RE_CANT_CASA = [
    re.compile(rf"\b(?:casa|vivienda|residencia|chalet)\s+(?:[a-z]+\s+){{0,3}}?de\s+{_NUM}\s+"
               r"(?:pisos|niveles|plantas)\b(?!\s+(?:de\s+)?altura)"),
    re.compile(rf"\b{_NUM}\s+(?:pisos|niveles|plantas)\b(?!\s+(?:de\s+)?altura)"),
    re.compile(r"\b(?:casa|vivienda|residencia|chalet)\s+(?:[a-z]+\s+){0,3}?de\s+(?:un|una|1)\s+"
               r"(?:solo\s+|sola\s+|unico\s+)?(?:piso|nivel|planta)\b()"),
    re.compile(r"\b(?:un|1)\s+(?:solo|unico)\s+(?:piso|nivel)\b()"),
]


# ------------------------------------------------------------------------------------ utilidades
def _numero(tok: str | None) -> int | None:
    if not tok:
        return None
    if tok.isdigit():
        return int(tok)
    return ORDINALES.get(tok, NUM_PALABRA.get(tok))


def _primer_grupo(m: re.Match) -> str | None:
    """Primer grupo de captura con valor; un grupo vacío ('') marca la regla 'un solo piso' (= 1)."""
    for g in m.groups():
        if g is not None:
            return g or "1"
    return None


def _prefijo(texto: str, pos: int, ancho: int = 50) -> str:
    """Texto de la misma cláusula que precede a `pos`."""
    previo = texto[max(0, pos - ancho):pos]
    corte = max((previo.rfind(c) for c in ".;|!?"), default=-1)
    return previo[corte + 1:] if corte >= 0 else previo


def _pisos_en(texto: str, regexes, es_titulo: bool = False) -> list[tuple[int, int, bool]]:
    """[(posición, piso, fuerte)] de las menciones válidas, ordenadas por posición.

    Una mención es "fuerte" si es una etiqueta ("piso: 13"), si el texto dice que la unidad "está / se ubica /
    se encuentra en ..." ese piso, o si viene del título. Se descartan las menciones de áreas comunes
    ("zonas comunes en el 1er piso", "gimnasio (piso 1)"), "departamentos por piso : 4" y "(piso 5)".
    """
    out = []
    for m in (m for regex in RE_PISO_ENUM for m in regex.finditer(texto)):
        for g in m.groups():                      # ambos pisos de la enumeración, como menciones débiles
            if _numero(g) is not None:
                out.append((m.start(), _numero(g), False))
    for regex in regexes:
        for m in regex.finditer(texto):
            v = _numero(_primer_grupo(m))
            if v is None or not 1 <= v <= PISO_MAX:
                continue
            antes = _prefijo(texto, m.start())
            despues = texto[m.end():m.end() + 40]
            entre_parentesis = antes.rstrip().endswith("(") and despues.lstrip().startswith(")")
            if antes.endswith("por ") or (entre_parentesis and m.group(0).startswith("piso")):
                continue
            if RE_OTRA_COSA.search(antes):
                continue
            if RE_AMENIDAD_ANTES.search(antes) and not RE_UBICACION.search(antes):
                continue
            if RE_AMENIDAD_DESPUES.match(re.split(r"[.;|]", despues)[0]):
                continue
            etiqueta = bool(re.match(r"piso\s*[:\-]", m.group(0)))
            fuerte = es_titulo or etiqueta or bool(RE_UBICACION.search(antes))
            out.append((m.start(), v, fuerte))
    return sorted(out)


def _decidir(hallazgos) -> tuple[int | None, bool]:
    """(piso, ambiguo): las menciones fuertes mandan; si hay varios pisos distintos no se adivina."""
    for grupo in ({v for _, v, f in hallazgos if f}, {v for _, v, _ in hallazgos}):
        if len(grupo) == 1:
            return next(iter(grupo)), False
        if len(grupo) > 1:
            return None, True
    return None, False


def _piso_unidad(t: str, e: str, d: str) -> tuple[int | None, str | None]:
    """Piso de la unidad. Ficha del portal > título > descripción; el texto libre ambiguo no se adivina."""
    # ficha del portal: etiqueta explícita
    m = RE_PISO_ETIQUETA.search(e)
    if m:
        v = _numero(_primer_grupo(m))
        if v is not None and 1 <= v <= PISO_MAX:
            return v, "estructurado"
    # ficha del portal: "piso : 3"
    hallados = _pisos_en(e, RE_PISO_TEXTO)
    if hallados:
        return hallados[0][1], "estructurado"
    # título y descripción
    for nombre, texto in (("titulo", t), ("descripcion", d)):
        piso, ambiguo = _decidir(_pisos_en(texto, RE_PISO_TEXTO, es_titulo=(nombre == "titulo")))
        if piso is not None:
            return piso, nombre
        if ambiguo:
            return None, "ambiguo"
    return None, None


def _cant_pisos(t: str, e: str, d: str, tipo: str | None) -> tuple[int | None, str | None]:
    """Pisos de la casa (niveles) o del edificio. Ficha del portal > título > descripción."""
    tope = CANT_MAX_CASA if tipo == "casa" else CANT_MAX_EDIFICIO

    def valido(v):
        return v if v is not None and 1 <= v <= tope else None

    for regex in (RE_CANT_ETIQUETA, RE_CANT_NIVELES_CASA) if tipo != "departamento" else (RE_CANT_ETIQUETA,):
        m = regex.search(e)
        if m and valido(_numero(_primer_grupo(m))):
            return _numero(_primer_grupo(m)), "estructurado"

    textos = (("titulo", t), ("descripcion", d))
    if tipo == "casa":
        reglas = RE_CANT_CASA + RE_CANT_EDIFICIO
    elif tipo == "cuarto":
        reglas = RE_CANT_EDIFICIO + RE_CANT_CASA[:1] + RE_CANT_CASA[2:3]    # "casa de N pisos" sí; "N pisos" suelto no
    else:
        reglas = RE_CANT_EDIFICIO
    for nombre, texto in textos:
        for regex in reglas:
            for m in regex.finditer(texto):
                v = valido(_numero(_primer_grupo(m)))
                if v:
                    return v, nombre
    return None, None


# ------------------------------------------------------------------------------- API pública
def extraer_pisos(titulo: str, estructurado: str, descripcion: str, tipo: str | None) -> dict:
    """Piso de la unidad y cantidad de pisos.

    tipo  'casa' | 'departamento' | 'cuarto' (habitación) | None. Debe venir de la categoría del portal o del
          título antes que de la descripción (ver extraccion.tipo_para_pisos).
    """
    t, e, d = titulo or "", estructurado or "", descripcion or ""
    out = {"piso_departamento": None, "cant_pisos": None, "piso_fuente": None, "cant_pisos_fuente": None}

    cant, cant_fuente = _cant_pisos(t, e, d, tipo)

    if tipo == "casa":
        out["piso_departamento"], out["piso_fuente"] = 0, "casa"
    else:
        piso, fuente = _piso_unidad(t, e, d)
        if piso is None and cant and any(RE_ULTIMO_PISO.search(x) for x in (t, d)):
            piso, fuente = cant, "ultimo_piso"
        out["piso_departamento"], out["piso_fuente"] = piso, fuente
        if piso and cant and cant < piso:     # el edificio no puede tener menos pisos que la unidad
            cant, cant_fuente = None, "inconsistente"

    out["cant_pisos"], out["cant_pisos_fuente"] = cant, cant_fuente
    return out
