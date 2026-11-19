
"""Extracción de campos estructurados desde el texto con reglas (regex).

Cada conteo (dormitorios, baños, estacionamientos) se busca por prioridad de fuente:
título > características > descripción. Se registra la fuente usada y si otra fuente
discrepa (conflicto), para contrastar el texto con los campos del portal.

Los pisos (pisos.py) se separan en dos variables:
- piso_departamento: piso donde está el departamento o la habitación (casa = 0).
- cant_pisos: pisos totales de la casa o del edificio que contiene el departamento/habitación.
"""
from __future__ import annotations

import re

from .banos import extraer_banos
from .pisos import extraer_pisos
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
    # "2.5 baños" cuenta 2 (el medio baño va aparte); sin el lookbehind se leia "5 baños"
    "banos": re.compile(
        rf"(?<![\d.,])\b{_NUM}(?:[.,]5)?\s*(?:banos?|bano\s+completo)"
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


def _tipo_en_titulo(titulo_n: str, n_palabras: int = 6) -> str | None:
    """Primer tipo de inmueble que nombra el título (acepta plurales: habitaciones, cuartos, deptos).

    Una palabra precedida por un número ("4 habitaciones", "dos habitaciones") cuenta dormitorios, no
    nombra el tipo: "Dúplex remodelado 4 habitaciones 2.5 baños" es un departamento.
    """
    toks = re.findall(r"[a-z0-9]+", titulo_n)[:n_palabras]
    for i, tok in enumerate(toks):
        if tok.isdigit():
            continue
        previo = toks[i - 1] if i else ""
        if previo.isdigit() or previo in NUM_PALABRA:
            continue
        for forma in (tok, tok[:-1] if tok.endswith("s") else "", tok[:-2] if tok.endswith("es") else ""):
            if forma in TIPOS:
                return TIPOS[forma]
    return None


def es_habitacion(tipo: str | None, tipo_fuente: str | None, titulo_n: str) -> bool:
    """¿El anuncio alquila una habitación/cuarto suelto? (único caso donde se distingue el tipo de baño).

    Prioridad: la categoría del portal o el título dicen "habitación" -> sí. Si la categoría o el título
    nombran otro tipo (departamento, casa...) -> no, aunque la descripción mencione "cuarto de servicio" o
    "habitaciones". Si no hay ninguna de las dos pistas, se usa el tipo detectado en el texto.
    """
    fuente = (tipo_fuente or "").strip()
    if fuente in ("habitacion", "cuarto"):
        return True
    en_titulo = _tipo_en_titulo(titulo_n)
    if en_titulo == "cuarto":
        return True
    if fuente in ("casa", "departamento") or en_titulo:
        return False
    return tipo == "cuarto"


def tipo_para_pisos(tipo: str | None, tipo_fuente: str | None, titulo_n: str) -> str | None:
    """'casa' | 'departamento' | 'cuarto' | None para decidir cómo se leen los pisos.

    Misma prioridad que el tipo final de la tabla: habitación (categoría o título) > categoría del portal
    (casa / departamento) > tipo detectado en el texto.
    """
    if es_habitacion(tipo, tipo_fuente, titulo_n):
        return "cuarto"
    fuente = (tipo_fuente or "").strip()
    if fuente in ("casa", "departamento"):
        return fuente
    return tipo if tipo in ("casa", "departamento") else None


def extraer_campos(
    titulo: str | None,
    estructurado: str | None,
    descripcion: str | None,
    cfg: dict,
    tipo_fuente: str | None = None,
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

    # Baños propios / compartidos / de visita (banos.py). El tipo de baño solo se discute en habitaciones o
    # cuartos (por el texto o por la categoria del portal); en una casa o departamento completo
    # ("dos dormitorios comparten un baño") el baño sigue siendo del inquilino.
    habitacion = es_habitacion(tipo, tipo_fuente, t)
    out.update(extraer_banos(fuentes, es_habitacion=habitacion, total=out["banos"]))
    out["es_habitacion"] = habitacion      # la tabla final usa este mismo criterio para habitacion / cuarto

    # 4. Pisos (pisos.py): piso donde está la unidad (casa = 0) y cantidad total de pisos
    out.update(extraer_pisos(t, e, d, tipo_para_pisos(tipo, tipo_fuente, t)))

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
