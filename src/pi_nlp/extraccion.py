"""Extracción de campos estructurados desde el texto con reglas (regex).

Cada conteo (dormitorios, baños, estacionamientos) se busca por prioridad de fuente:
título > características > descripción. Se registra la fuente usada y si otra fuente
discrepa (``*_conflicto``), para contrastar el texto con los campos del portal.
"""
from __future__ import annotations

import re

from .texto import normalizar, parse_numero

NUM_PALABRA = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
               "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}
_NUM = r"(\d{1,2}|" + "|".join(NUM_PALABRA) + r")"

PATRONES_CONTEO = {
    "dormitorios": re.compile(rf"\b{_NUM}\s*(?:dormitorios?|dorms?\b\.?|habitaciones|habitacion|hab\b\.?)"),
    "banos": re.compile(rf"\b{_NUM}\s*(?:banos?|bano\s+completo)"),
    "estacionamientos": re.compile(rf"\b{_NUM}\s*(?:estacionamientos?|cocheras?|garajes?|estac\b\.?)"),
}

_AREA = r"(\d[\d.,]*)\s*m2"
RE_AREA_TERRENO = re.compile(rf"(?:\ba\.?\s?t\.?\s*[:\-]?|area\s*(?:de\s*)?terreno\s*[:\-]?|terreno\s*(?:de|:)?)\s*{_AREA}")
RE_AREA_CONSTRUIDA = re.compile(
    rf"(?:\ba\.?\s?c\.?\s*[:\-]?|area\s*(?:de\s*)?(?:construida|techada)\s*[:\-]?|construccion\s*(?:de|:)?)\s*{_AREA}"
    rf"|{_AREA}\s*(?:de\s*)?(?:area\s*)?(?:construid|techad|cub\b)"
)
RE_AREA_TOTAL = re.compile(rf"area\s*total\s*[:\-]?\s*{_AREA}|{_AREA}\s*tot\b")
RE_AREA_TITULO = re.compile(_AREA)
RE_PISOS = re.compile(r"numero de pisos\s*:\s*(\d{1,2})|\b(\d{1,2})\s*(?:pisos|niveles)\b")
RE_ANTIG = re.compile(r"(\d{1,2})\s*anos\s*(?:de\s*)?antiguedad|antiguedad\s*[:\-]?\s*(\d{1,2})\s*anos")
RE_PISO_DEPTO = re.compile(r"\bpiso\s*(\d{1,2})\b")

TIPOS = {"casa": "casa", "departamento": "departamento", "depa": "departamento", "dpto": "departamento",
         "flat": "departamento", "terreno": "terreno", "lote": "terreno", "oficina": "oficina",
         "local": "local", "cuarto": "cuarto", "habitacion": "cuarto"}


def _entero(tok: str) -> int | None:
    return int(tok) if tok.isdigit() else NUM_PALABRA.get(tok)


def _extraer_conteo(nombre: str, fuentes: list[tuple[str, str]], max_valor: int):
    """Devuelve (valor, fuente, conflicto). `fuentes` = [(nombre_fuente, texto_normalizado)] por prioridad.

    El valor sale de la primera fuente que lo trae. El conflicto se evalúa SOLO entre fuentes
    estructuradas (título y características): la descripción es narrativa y enumera ambientes sueltos
    ("1 baño" en un cuarto), así que contrastar contra ella da falsos positivos hasta medirlo en N6.
    """
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
    estructuradas = [f for f in ("titulo", "caracteristicas") if f in valores]
    conflicto = len(estructuradas) > 1 and any(valor not in valores[f] for f in estructuradas)
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


def extraer_campos(titulo: str | None, estructurado: str | None, descripcion: str | None, cfg: dict) -> dict:
    """Aplica todas las reglas de extracción a un anuncio (textos ya limpios y anonimizados)."""
    t, e, d = normalizar(titulo), normalizar(estructurado), normalizar(descripcion)
    fuentes = [("titulo", t), ("caracteristicas", e), ("descripcion", d)]
    out: dict = {}

    maximos = {"dormitorios": cfg["max_dormitorios"], "banos": cfg["max_banos"],
               "estacionamientos": cfg["max_estacionamientos"]}
    for nombre, mx in maximos.items():
        v, f, c = _extraer_conteo(nombre, fuentes, mx)
        out[nombre], out[f"{nombre}_fuente"], out[f"{nombre}_conflicto"] = v, f, c

    unido = " | ".join(x for x in (e, d) if x)
    out["area_titulo_m2"] = _primera_area(RE_AREA_TITULO, t)
    out["area_terreno_m2"] = _primera_area(RE_AREA_TERRENO, unido)
    out["area_construida_m2"] = _primera_area(RE_AREA_CONSTRUIDA, unido)
    out["area_total_m2"] = _primera_area(RE_AREA_TOTAL, unido)

    m = RE_PISOS.search(unido)
    out["n_pisos"] = int(next(g for g in m.groups() if g)) if m else None
    tipo = detectar_tipo(t, unido)
    out["tipo_inmueble"] = tipo
    mp = RE_PISO_DEPTO.search(unido)
    out["piso_departamento"] = int(mp.group(1)) if (mp and tipo == "departamento") else None

    if re.search(r"a estrenar|estreno\b", unido):
        out["antiguedad_anios"] = 0
    else:
        ma = RE_ANTIG.search(unido)
        out["antiguedad_anios"] = int(next(g for g in ma.groups() if g)) if ma else None
    return out
