"""Anonimización y enmascarado de montos.

Dos objetivos distintos:
1. Privacidad: quitar teléfonos, correos, URLs y nombres de contacto (Ley 29733).
2. Fuga de información: los montos escritos en el texto pueden revelar la renta (variable objetivo),
   así que se enmascaran antes de cualquier representación del texto. Se conservan aparte
   (``montos``) solo para auditar la fuga, nunca como insumo del modelo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .texto import normalizar, parse_numero

RE_EMAIL = re.compile(r"[\w.\-+]+@[\w\-]+(?:\.[\w\-]+)+")
RE_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
# Celular peruano (9 dígitos que empiezan en 9) con separadores variados: 9.2.7.8..., 987 654 321, +51 987-654-321
RE_TEL = re.compile(r"(?<![\d.,])(?:\+?51[\s.\-]?)?9(?:[\s.\-]?\d){8}(?![\d])")
RE_CONTACTO_DOS_PUNTOS = re.compile(
    r"(?P<pre>\b(?:contacto|contactar a|contactarse con|asesor(?:a)?(?: comercial)?|informes?|atiende|llamar a|ver con)\s*:\s*)(?P<resto>.+)$",
    re.I,
)
RE_CONTACTO_SOLO = re.compile(r"\W*(?:contacto|asesor(?:a)?(?: comercial)?|informes?)\W*", re.I)

# Nombre de una persona después de expresiones explícitas de contacto.
RE_NOMBRE_TRAS_CONTACTO = re.compile(
    r"(?i:\b(?:comunicate|comunícate|comuníquese|"
    r"comunicarse|contacta|contactar)\s+con\s+)"
    r"(?P<nombre>[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+"
    r"\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+)"
    r"(?=\s|[,.;]|$)"
)

# Nombre seguido de un cargo inmobiliario.
RE_NOMBRE_ANTES_CARGO = re.compile(
    r"(?P<nombre>\b[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+"
    r"(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+){1,2})"
    r"(?=\s*[-,]\s*(?i:asesor|asesora|agente|"
    r"corredor|corredora)\b)"
)

RE_MONTO = re.compile(
    r"(?P<mon>US\$|USD|\$|S/\.?|PEN)\s*(?P<v>\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d{3,}(?:[.,]\d{1,2})?)"
    r"|(?P<v2>\d{1,3}(?:[.,]\d{3})+|\d{3,})\s*(?P<mon2>US\$|USD|dolares|dólares|soles)\b",
    re.I,
)
CTX_GARANTIA = re.compile(r"garant|deposito|adelanto|mes de adelanto")
CTX_MANTENIMIENTO = re.compile(r"mantenim|gastos comunes|arbitrios|cuota|mensualidad de mant")


@dataclass
class ResultadoAnonimizacion:
    texto: str | None
    n_telefonos: int = 0
    n_correos: int = 0
    n_urls: int = 0
    n_contactos: int = 0
    montos: list[dict] = field(default_factory=list)  # solo para auditoría de fuga


def _moneda(tok: str) -> str:
    t = tok.upper().replace(".", "")
    if t in ("US$", "USD", "$", "DOLARES", "DÓLARES"):
        return "USD"
    return "PEN"



def _enmascarar_contactos(texto: str) -> tuple[str, int]:
    """Enmascara datos de contacto sin eliminar características inmobiliarias."""
    segs = texto.split(" | ")
    n = 0

    for i, seg in enumerate(segs):

        # Caso 1: Contacto: Juan Pérez
        m = RE_CONTACTO_DOS_PUNTOS.search(seg) if len(seg) <= 160 else None

        if m and m.group("resto").strip() != "<CONTACTO>":
            segs[i] = seg[:m.start("resto")] + "<CONTACTO>"
            n += 1
            continue

        # Caso 2: Comunícate con Juan Pérez
        seg, encontrados = RE_NOMBRE_TRAS_CONTACTO.subn(
            "<CONTACTO>", seg
        )
        n += encontrados

        # Caso 3: María López - Asesora inmobiliaria
        seg, encontrados = RE_NOMBRE_ANTES_CARGO.subn(
            "<CONTACTO>", seg
        )
        n += encontrados

        segs[i] = seg

        # Caso 4: Contacto aparece solo y los datos están
        # en el siguiente segmento.
        if (
            RE_CONTACTO_SOLO.fullmatch(segs[i])
            and i + 1 < len(segs)
            and len(segs[i + 1]) <= 60
        ):
            segs[i + 1] = "<CONTACTO>"
            n += 1

    return " | ".join(segs), n



def anonimizar(texto: str | None) -> ResultadoAnonimizacion:
    """Anonimiza datos personales y enmascara montos. Devuelve el texto y conteos de lo hallado."""
    if not texto:
        return ResultadoAnonimizacion(texto=texto)
    t = texto
    t, n_mail = RE_EMAIL.subn("<CORREO>", t)
    t, n_url = RE_URL.subn("<URL>", t)
    t, n_tel = RE_TEL.subn("<TELEFONO>", t)
    t, n_cont = _enmascarar_contactos(t)

    montos: list[dict] = []

    def _sub_monto(m: re.Match) -> str:
        valor = parse_numero(m.group("v") or m.group("v2"))
        mon = _moneda(m.group("mon") or m.group("mon2"))
        # El contexto se limita a la cláusula actual (no cruza '.', ';' ni '|') para no heredar la etiqueta del monto anterior.
        ctx = normalizar(re.split(r"[.;|]\s", t[max(0, m.start() - 40): m.start()])[-1])
        if CTX_GARANTIA.search(ctx):
            tipo, tag = "garantia", "<MONTO_GARANTIA>"
        elif CTX_MANTENIMIENTO.search(ctx):
            tipo, tag = "mantenimiento", "<MONTO_MANTENIMIENTO>"
        else:
            tipo, tag = "otro", "<MONTO>"
        montos.append({"valor": valor, "moneda": mon, "tipo": tipo})
        return tag

    t = RE_MONTO.sub(_sub_monto, t)
    return ResultadoAnonimizacion(t, n_tel, n_mail, n_url, n_cont, montos)

# Módulo NLP integrado al repositorio del Proyecto Integrador.
