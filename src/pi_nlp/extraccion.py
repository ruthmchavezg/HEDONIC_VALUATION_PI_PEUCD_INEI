
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
)

RE_AREA_CONSTRUIDA = re.compile(
    rf"(?:\ba\.?\s*c\.?\s*[:\-]?|area\s*(?:de\s*)?(?:construida|techada)\s*[:\-]?|construccion\s*(?:de|:)?)\s*{_AREA}"
    rf"|{_AREA}\s*(?:de\s*)?(?:area\s*)?(?:construid|techad|cub\b)"
)

RE_AREA_TOTAL = re.compile(
    rf"(?:area|superficie)\s*total\s*[:\-]?\s*{_AREA}|{_AREA}\s*tot\b"
)

RE_AREA_TITULO = re.compile(_AREA)

# Patrones para pisos
# Viviendas: se utilizan principalmente características estructuradas.
RE_PISOS_VIVIENDA = re.compile(
    r"(?:numero de pisos|niveles construidos)\s*:\s*(\d{1,2})",
    re.IGNORECASE
)

# Departamentos: piso específico donde se encuentra la unidad.

RE_PISO_DEPTO = re.compile(
    r"piso en el que se encuentra\s*:\s*(\d{1,2})"
    r"|(?:piso|en el piso)\s*(\d{1,2})\b"
    r"|(\d{1,2})\s*[°º?]?\s*piso\b"
    r"|\b(primer|primero|segundo|tercer|tercero|cuarto|quinto|"
    r"sexto|septimo|octavo|noveno|decimo)\s+piso\b",
    re.IGNORECASE
)


# Número total de pisos del edificio.
RE_PISOS_EDIFICIO = re.compile(
    r"edificio\s+(?:cuenta\s+con|de|con)\s*(\d{1,2})\s+pisos\b"
    r"|numero de pisos\s*:\s*(\d{1,2})",
    re.IGNORECASE
)

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

    # 2. Áreas
    unido = " | ".join(x for x in (e, d) if x)

    out["area_titulo_m2"] = _primera_area(RE_AREA_TITULO, t)
    out["area_terreno_m2"] = _primera_area(RE_AREA_TERRENO, unido)
    out["area_construida_m2"] = _primera_area(RE_AREA_CONSTRUIDA, unido)
    out["area_total_m2"] = _primera_area(RE_AREA_TOTAL, unido)

    # 3. Tipo de inmueble
    tipo = detectar_tipo(t, unido)
    out["tipo_inmueble"] = tipo

    # 4. Pisos: variables diferenciadas
    out["n_pisos"] = None
    out["piso_departamento"] = None
    out["pisos_edificio"] = None

    if tipo == "casa":
        m = RE_PISOS_VIVIENDA.search(e)

        if m:
            valor = int(m.group(1))
            out["n_pisos"] = valor if valor > 0 else None

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

    # 5. Antigüedad
    if re.search(r"a estrenar|estreno\b", unido):
        out["antiguedad_anios"] = 0
    else:
        ma = RE_ANTIG.search(unido)
        out["antiguedad_anios"] = (
            int(_primer_grupo(ma)) if ma else None
        )

    return out
