
"""Extracción de campos estructurados desde el texto con reglas (regex).

Cada conteo (dormitorios, baños, estacionamientos) se busca por prioridad de fuente:
título > características > descripción. Se registra la fuente usada y si otra fuente
discrepa (conflicto), para contrastar el texto con los campos del portal.

Los pisos se separan en tres variables:
- n_pisos: niveles de la vivienda.
- piso_departamento: ubicación del departamento dentro del edificio.
- pisos_edificio: número total de pisos del edificio.
"""
from __future__ import annotations

import re

from .texto import normalizar, parse_numero


NUM_PALABRA = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3,
    "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10
}

_NUM = r"(\d{1,2}|" + "|".join(NUM_PALABRA) + r")"

PATRONES_CONTEO = {
    "dormitorios": re.compile(
        rf"\b{_NUM}\s*(?:dormitorios?|dorms?\b\.?|habitaciones|habitacion|hab\b\.?)"
    ),
    "banos": re.compile(
        rf"\b{_NUM}\s*(?:banos?|bano\s+completo)"
    ),
    "estacionamientos": re.compile(
        rf"\b{_NUM}\s*(?:estacionamientos?|cocheras?|garajes?|estac\b\.?)"
    ),
}

# Patrones para áreas
_AREA = r"(\d[\d.,]*)\s*m2"

RE_AREA_TERRENO = re.compile(
    rf"(?:\ba\.?\s*t\.?\s*[:\-]?|area\s*(?:de\s*)?terreno\s*[:\-]?|terreno\s*(?:de|:)?)\s*{_AREA}"
    rf"|{_AREA}\s*(?:de\s*)?(?:area\s*)?terreno\b"
)

RE_AREA_CONSTRUIDA = re.compile(
    rf"(?:\ba\.?\s*c\.?\s*[:\-]?|area\s*(?:de\s*)?construida\s*[:\-]?|construccion\s*(?:de|:)?)\s*{_AREA}"
    rf"|{_AREA}\s*(?:de\s*)?(?:area\s*)?construid"
)

RE_AREA_TECHADA = re.compile(
    rf"(?:area\s*(?:de\s*)?techada\s*[:\-]?)\s*{_AREA}"
    rf"|{_AREA}\s*(?:de\s*)?(?:area\s*)?techad"
)

RE_AREA_TOTAL = re.compile(
    rf"(?:area|superficie)\s*total\s*[:\-]?\s*{_AREA}"
    rf"|{_AREA}\s*tot\b"
    rf"|{_AREA}\s*(?:de\s*)?(?:area\s*)?total\b"
)

RE_AREA_TITULO = re.compile(_AREA)

# Patrones para pisos
# Viviendas: se utilizan principalmente características estructuradas.
RE_PISOS_VIVIENDA = re.compile(
    r"(?:numero de pisos|niveles construidos|pisos del edificio|pisos de la casa|numero de niveles)\s*:\s*(\d{1,2})",
    re.IGNORECASE
)

# "casa de 3 pisos", "de dos niveles", "2 plantas" (solo se usa para casas)
RE_PISOS_TEXTO = re.compile(rf"\b{_NUM}\s*(?:pisos|niveles|plantas)\b(?!\s+(?:de\s+)?altura)")

# Departamentos: piso específico donde se encuentra la unidad.

RE_PISO_DEPTO = re.compile(
    r"piso en el que se encuentra\s*:\s*(\d{1,2})"
    r"|piso de la unidad\s*:\s*(\d{1,2})"
    r"|(?:piso|en el piso)\s*(\d{1,2})\b"
    r"|(\d{1,2})\s*(?:to|ro|er|do|mo|vo|no|ero|mo)\.?\s*piso\b"
    r"|(\d{1,2})\s*[°º?]?\s*piso\b"
    r"|\b(primer|primero|segundo|tercer|tercero|cuarto|quinto|"
    r"sexto|septimo|octavo|noveno|decimo)\s+piso\b",
    re.IGNORECASE
)


# Número total de pisos del edificio.
RE_PISOS_EDIFICIO = re.compile(
    r"edificio\s+(?:cuenta\s+con|de|con)\s*(\d{1,2})\s+pisos\b"
    r"|pisos del edificio\s*:\s*(\d{1,2})"
    r"|(?:edificio|torre)\s+de\s+(\d{1,2})\s+(?:pisos|niveles)\b"
    r"|(\d{1,2})\s+pisos\s+(?:en\s+)?(?:el\s+)?edificio\b",
    re.IGNORECASE
)

# "Numero de pisos: N" en un departamento es ambiguo: casi siempre son los niveles de la unidad (1 = flat,
# 2 = duplex) y no los del edificio. Solo se acepta como pisos del edificio si N >= 3 y no es menor al piso
# donde esta la unidad.
RE_NUM_PISOS_AMBIGUO = re.compile(r"numero de pisos\s*:\s*(\d{1,2})", re.IGNORECASE)

ORDINALES_PISO = {
    "primer": 1,
    "primero": 1,
    "segundo": 2,
    "tercer": 3,
    "tercero": 3,
    "cuarto": 4,
    "quinto": 5,
    "sexto": 6,
    "septimo": 7,
    "octavo": 8,
    "noveno": 9,
    "decimo": 10,
}

# Otros patrones
RE_ANTIG = re.compile(
    r"(\d{1,2})\s*anos\s*(?:de\s*)?antiguedad"
    r"|antiguedad\s*[:\-]?\s*(\d{1,2})\s*anos"
)

RE_ANTIG2 = re.compile(
    r"construid[oa]\s+hace\s+(\d{1,2})\s*anos"
    r"|(\d{1,2})\s*anos\s+de\s+(?:construid[oa]|construccion)"
    r"|tiene\s+(\d{1,2})\s*anos\s+de\s+(?:antiguedad|construido|construccion)"
)

# Año de construccion explicito: "Año de construcción: 1996", "construido en 2011", "edificio del año 2015"
RE_ANIO_CONSTRUCCION = re.compile(
    r"ano\s+de\s+construccion\s*[:\-]?\s*((?:19|20)\d{2})"
    r"|construccion\s+(?:del\s+)?ano\s*[:\-]?\s*((?:19|20)\d{2})"
    r"|construid[oa]\s+(?:en\s+(?:el\s+)?(?:ano\s+)?|el\s+ano\s+)((?:19|20)\d{2})"
    r"|edificio\s+(?:del|de)\s+ano\s+((?:19|20)\d{2})"
)

# Urbania entrega la antigüedad suelta como una característica más: "... | 1 dorm. | 15 años".
RE_ANTIG_SUELTA = re.compile(r"(?:^|\|)\s*(\d{1,2})\s*anos\s*(?:\||$)")

TIPOS = {
    "casa": "casa",
    "departamento": "departamento",
    "depa": "departamento",
    "dpto": "departamento",
    "flat": "departamento",
    "terreno": "terreno",
    "lote": "terreno",
    "oficina": "oficina",
    "local": "local",
    "cuarto": "cuarto",
    "habitacion": "cuarto",
}


RE_SIN_COCHERA = re.compile(
    r"\b(?:sin|no\s+(?:incluye|tiene|cuenta\s+con|hay))\s+(?:estacionamientos?|cocheras?|garajes?|garages?|parqueos?)\b"
)
RE_COCHERA_MENCION = re.compile(r"\b(?:cocheras?|garajes?|garages?|estacionamientos?|parqueos?)\b")
RE_COCHERA_NO_PROPIA = re.compile(
    r"visitas?|invitados|aparte|adicional|opcional|se\s+alquila|alquilar|alquilable|por\s+separado|"
    r"publico|de\s+la\s+calle|en\s+la\s+calle|cerca\s+de|zona\s+de|a\s+\d+\s+(?:cuadras?|minutos?)"
)


def _extraer_cochera_sin_numero(fuentes: list[tuple[str, str]]) -> tuple[int | None, str | None]:
    """Cochera mencionada sin cantidad: 'sin cochera' -> 0; 'cochera techada' -> 1; opcional/visitas -> nada."""
    for _, texto in fuentes:
        if texto and RE_SIN_COCHERA.search(texto):
            return 0, "negacion"

    for _, texto in fuentes:
        if not texto:
            continue
        for m in RE_COCHERA_MENCION.finditer(texto):
            ventana = texto[max(0, m.start() - 35): m.end() + 35]
            if not RE_COCHERA_NO_PROPIA.search(ventana):
                return 1, "mencion"

    return None, None


# ---- banos por tipo: propios / compartidos / de visita
_BANO = r"banos?"
RE_BANO_VISITA = re.compile(
    rf"\b{_NUM}\s*(?:medios?\s+banos?|1\s*/\s*2\s*banos?)"
    rf"|\bmedios?\s+banos?\s*[:\-]?\s*(\d)\b"
    rf"|\b{_NUM}\s*{_BANO}\s+(?:de\s+|para\s+)?(?:visitas?|invitados|social(?:es)?)\b"
    rf"|\b{_BANO}\s+(?:de\s+|para\s+)?(?:visitas?|invitados|social(?:es)?|cortesia)\b"
    rf"|\bmedios?\s+banos?\b|\btoilet(?:te)?s?\b|\bhalf\s+baths?\b"
)
RE_BANO_COMPARTIDO = re.compile(
    rf"\b{_NUM}\s*{_BANO}\s+(?:compartid\w+|comunes?|en\s+comun|externos?)\b"
    rf"|\b{_BANO}\s+(?:compartid\w+|comunes?|en\s+comun|externos?)\b"
    rf"|\bcompart\w+\s+(?:el\s+|un\s+)?{_BANO}\b"
)
RE_BANO_SERVICIO = re.compile(rf"\b{_NUM}?\s*{_BANO}\s+(?:de\s+|del\s+)?(?:servicio|empleada|personal)\b")
RE_BANO_DECIMAL = re.compile(r"\b(\d{1,2})[.,]5\s*banos?\b")
RE_BANO_PROPIO = re.compile(
    rf"\b{_NUM}\s*(?:banos?(?:\s+completos?)?|duchas?)\b"
    rf"|\b{_BANO}\s*[:\-]\s*(\d{{1,2}})\b"
    rf"|\bbanos?\s+(?:propios?|privados?|independientes?|en\s+suite|incorporados?|dentro\s+de\s+(?:la\s+)?habitacion)\b"
)


def _n_de(m: re.Match) -> int:
    for g in m.groups():
        if g:
            v = _entero(g)
            if v is not None:
                return v
    return 1


def _contar(regex: re.Pattern, texto: str) -> int | None:
    vistos = [_n_de(m) for m in regex.finditer(texto)]
    return min(sum(vistos), 6) if vistos else None


def extraer_banos_detalle(fuentes: list[tuple[str, str]]) -> dict:
    """Baños propios, compartidos y de visita (medio baño), sin contar los de servicio.

    Se evita contar dos veces: primero se retiran del texto los baños de visita, compartidos y de
    servicio, y los que quedan (N banos, bano propio/privado, "banos: 2") son los propios.
    '3.5 banos' = 3 propios + 1 de visita.
    """
    out = {"banos_propios": None, "banos_compartidos": None, "banos_visita": None}

    for _, texto in fuentes:
        if not texto:
            continue

        visita = _contar(RE_BANO_VISITA, texto)
        compartido = _contar(RE_BANO_COMPARTIDO, texto)
        limpio = RE_BANO_VISITA.sub(" ", texto)
        limpio = RE_BANO_COMPARTIDO.sub(" ", limpio)
        limpio = RE_BANO_SERVICIO.sub(" ", limpio)

        decimal = RE_BANO_DECIMAL.search(limpio)
        if decimal:
            propios = int(decimal.group(1))
            visita = visita or 1
            limpio = RE_BANO_DECIMAL.sub(" ", limpio)
        else:
            m = RE_BANO_PROPIO.search(limpio)
            propios = _n_de(m) if m else None
            if propios is not None and propios > 15:
                propios = None

        if out["banos_propios"] is None and propios is not None:
            out["banos_propios"] = propios
        if out["banos_compartidos"] is None and compartido is not None:
            out["banos_compartidos"] = compartido
        if out["banos_visita"] is None and visita is not None:
            out["banos_visita"] = visita

    return out


def _entero(tok: str) -> int | None:
    return int(tok) if tok.isdigit() else NUM_PALABRA.get(tok)


def _extraer_conteo(
    nombre: str,
    fuentes: list[tuple[str, str]],
    max_valor: int
):
    """Devuelve (valor, fuente, conflicto)."""
    valores: dict[str, set[int]] = {}
    primero: dict[str, int] = {}

    for fuente, texto in fuentes:
        if not texto:
            continue

        for m in PATRONES_CONTEO[nombre].finditer(texto):
            v = _entero(m.group(1))

            if v is not None and 0 <= v <= max_valor:
                valores.setdefault(fuente, set()).add(v)
                primero.setdefault(fuente, v)

    if not primero:
        return None, None, False

    fuente = next(f for f, _ in fuentes if f in primero)
    valor = primero[fuente]

    estructuradas = [
        f for f in ("titulo", "caracteristicas")
        if f in valores
    ]

    conflicto = (
        len(estructuradas) > 1
        and any(valor not in valores[f] for f in estructuradas)
    )

    return valor, fuente, conflicto


def _primera_area(regex: re.Pattern, texto: str) -> float | None:
    m = regex.search(texto)

    if not m:
        return None

    for g in m.groups():
        if g:
            v = parse_numero(g.rstrip(".,"))
            if v:
                return v

    return None


def _primer_grupo(m: re.Match) -> str | None:
    """Devuelve el primer grupo de captura que contiene un valor."""
    return next((g for g in m.groups() if g is not None), None)


def _extraer_piso_departamento(texto: str) -> int | None:
    """Extrae el piso del departamento, incluyendo ordinales escritos."""
    m = RE_PISO_DEPTO.search(texto)

    if not m:
        return None

    valor = _primer_grupo(m)

    if valor is None:
        return None

    if valor.isdigit():
        return int(valor)

    return ORDINALES_PISO.get(valor)


def detectar_tipo(titulo_n: str, resto_n: str) -> str | None:
    """Tipo de inmueble: primero la palabra inicial del título; si no, la palabra más mencionada."""
    for tok in re.findall(r"[a-z]+", titulo_n)[:3]:
        if tok in TIPOS:
            return TIPOS[tok]

    conteo: dict[str, int] = {}

    for tok in re.findall(r"[a-z]+", resto_n):
        if tok in TIPOS:
            conteo[TIPOS[tok]] = conteo.get(TIPOS[tok], 0) + 1

    return max(conteo, key=conteo.get) if conteo else None


def extraer_campos(
    titulo: str | None,
    estructurado: str | None,
    descripcion: str | None,
    cfg: dict
) -> dict:
    """Aplica todas las reglas de extracción a un anuncio (textos ya limpios y anonimizados)."""

    t = normalizar(titulo)
    e = normalizar(estructurado)
    d = normalizar(descripcion)

    fuentes = [
        ("titulo", t),
        ("caracteristicas", e),
        ("descripcion", d)
    ]

    out: dict = {}

    # 1. Conteos
    maximos = {
        "dormitorios": cfg["max_dormitorios"],
        "banos": cfg["max_banos"],
        "estacionamientos": cfg["max_estacionamientos"]
    }

    for nombre, mx in maximos.items():
        v, f, c = _extraer_conteo(nombre, fuentes, mx)
        out[nombre] = v
        out[f"{nombre}_fuente"] = f
        out[f"{nombre}_conflicto"] = c

    # 1b. Estacionamientos mencionados sin cantidad ("cochera techada", "sin cochera")
    if out["estacionamientos"] is None:
        v, f = _extraer_cochera_sin_numero(fuentes)
        out["estacionamientos"], out["estacionamientos_fuente"] = v, f

    # 1c. Baños propios / compartidos / de visita
    out.update(extraer_banos_detalle(fuentes))

    # 2. Áreas
    unido = " | ".join(x for x in (e, d) if x)

    out["area_titulo_m2"] = _primera_area(RE_AREA_TITULO, t)
    out["area_terreno_m2"] = _primera_area(RE_AREA_TERRENO, unido)
    out["area_construida_m2"] = _primera_area(RE_AREA_CONSTRUIDA, unido)
    out["area_techada_m2"] = _primera_area(RE_AREA_TECHADA, unido)
    out["area_total_m2"] = _primera_area(RE_AREA_TOTAL, unido)

    # 3. Tipo de inmueble
    tipo = detectar_tipo(t, unido)
    out["tipo_inmueble"] = tipo

    # "Baño compartido" solo tiene sentido al alquilar una habitacion/cuarto suelto. En una casa o
    # departamento completo ("dos dormitorios comparten un baño") el baño sigue siendo del inquilino.
    if tipo != "cuarto":
        out["banos_compartidos"] = None

    # 4. Pisos: variables diferenciadas
    out["n_pisos"] = None
    out["piso_departamento"] = None
    out["pisos_edificio"] = None

    if tipo == "casa":
        m = RE_PISOS_VIVIENDA.search(e)

        if m:
            valor = int(m.group(1))
            out["n_pisos"] = valor if valor > 0 else None
        else:
            for texto_p in (t, d):
                mp = RE_PISOS_TEXTO.search(texto_p)
                if mp:
                    valor = _entero(mp.group(1))
                    out["n_pisos"] = valor if valor and 0 < valor <= 8 else None
                    break

    elif tipo == "departamento":
        # Piso donde se encuentra la unidad.
        out["piso_departamento"] = _extraer_piso_departamento(e)

        if out["piso_departamento"] is None:
            out["piso_departamento"] = _extraer_piso_departamento(d)

        # Número total de pisos del edificio.
        m = RE_PISOS_EDIFICIO.search(d)

        if not m:
            m = RE_PISOS_EDIFICIO.search(e)

        if m:
            valor = int(_primer_grupo(m))
            out["pisos_edificio"] = valor if valor > 0 else None

    # "Numero de pisos: N" en departamento: solo si es plausible como pisos del edificio
    if tipo == "departamento" and out["pisos_edificio"] is None:
        for texto_p in (e, d):
            mp = RE_NUM_PISOS_AMBIGUO.search(texto_p)
            if mp:
                valor = int(mp.group(1))
                piso = out["piso_departamento"] or 0
                if 3 <= valor <= 80 and valor >= piso:
                    out["pisos_edificio"] = valor
                break

    # Numero de pisos del edificio declarado de forma explicita (tambien en casas: "Pisos del edificio: 3")
    if out["pisos_edificio"] is None:
        for texto_p in (e, d):
            m = RE_PISOS_EDIFICIO.search(texto_p)
            if m:
                valor = int(_primer_grupo(m))
                out["pisos_edificio"] = valor if 0 < valor <= 80 else None
                break

    # 5. Año de construcción y antigüedad
    out["anio_construccion_texto"] = None
    for texto_a in (e, d, t):
        ma = RE_ANIO_CONSTRUCCION.search(texto_a)
        if ma:
            anio = int(_primer_grupo(ma))
            out["anio_construccion_texto"] = anio if 1900 <= anio <= 2027 else None
            break

    if re.search(r"a estrenar|estreno\b", unido):
        out["antiguedad_anios"] = 0
    else:
        ma = RE_ANTIG.search(unido) or RE_ANTIG_SUELTA.search(e) or RE_ANTIG2.search(unido)
        out["antiguedad_anios"] = (
            int(_primer_grupo(ma)) if ma else None
        )

    return out
