
"""Anonimización y enmascarado de montos.

Dos objetivos distintos:
1. Privacidad: quitar teléfonos, correos, URLs y nombres de contacto (Ley 29733).
2. Fuga de información: los montos escritos en el texto pueden revelar la renta
   (variable objetivo), así que se enmascaran antes de cualquier representación
   del texto. Se conservan aparte (montos) solo para auditar la fuga, nunca como
   insumo del modelo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .texto import normalizar, parse_numero

RE_EMAIL = re.compile(r"[\w.\-+]+@[\w\-]+(?:\.[\w\-]+)+")
RE_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)

# Celular peruano (9 dígitos que empiezan en 9) con separadores variados.
RE_TEL = re.compile(r"(?<![\d.,])(?:\+?51[\s.\-]?)?9(?:[\s.\-]?\d){8}(?![\d])")

# Redes sociales: celulares escritos con simbolos entre digitos ("9*9*7*5*2*6*7*6*7", "#979//584//412")
# y el marcador "[hidden information]" que deja Facebook donde habia un dato de contacto.
RE_TEL_OFUSCADO = re.compile(r"(?<![\d.,])9(?:[\s*./\-_]{1,3}\d){8}(?![\d])")
RE_TEL_SEPARADORES_RAROS = re.compile(r"#?\b9\d{2}[\s/*.\-]{1,3}\d{3}[\s/*.\-]{1,3}\d{3}\b")
RE_HIDDEN = re.compile(r"\[hidden information\]", re.I)

RE_CONTACTO_DOS_PUNTOS = re.compile(
    r"(?P<pre>\b(?:contacto|contactar a|contactarse con|asesor(?:a)?(?: comercial)?|informes?|atiende|llamar a|ver con)\s*:\s*)(?P<resto>.+)$",
    re.I,
)

RE_CONTACTO_SOLO = re.compile(
    r"\b(?:contacto|asesor(?:a)?(?: comercial)?|informes?)\b",
    re.I,
)

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
    r"(?P<mon>US\$|USD|\$|S/\.?|PEN)\s*"
    r"(?P<v>\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?"
    r"|\d+(?:[.,]\d+)?)(?:\s*(?P<mult1>k|mil))?"
    r"|(?P<v2>\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
    r"\s*(?P<mult2>k|mil)?\s*"
    r"(?P<mon2>US\$|USD|dolares|dólares|soles)\b",
    re.I,
)

CTX_GARANTIA = re.compile(
    r"garant|deposito|adelanto|mes de adelanto"
)

CTX_MANTENIMIENTO = re.compile(
    r"mantenim|gastos comunes|arbitrios|cuota|mensualidad de mant"
)

CTX_VENTA = re.compile(
    r"\b(?:venta|vendo|vender|se vende)\b"
)

CTX_ALQUILER = re.compile(
    r"\b(?:alquiler|alquilo|alquilar|alquila|alquilan|"
    r"alquilamos|arrendamiento|arrendar|renta|rentamos)\b"
    r"|renta\s+mensual"
)


@dataclass
class ResultadoAnonimizacion:
    texto: str | None
    n_telefonos: int = 0
    n_correos: int = 0
    n_urls: int = 0
    n_contactos: int = 0
    montos: list[dict] = field(default_factory=list)


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
    """Anonimiza datos personales y enmascara montos."""
    if not texto:
        return ResultadoAnonimizacion(texto=texto)

    t = texto
    t, n_mail = RE_EMAIL.subn("<CORREO>", t)
    t, n_url = RE_URL.subn("<URL>", t)
    t, n_tel = RE_TEL.subn("<TELEFONO>", t)
    t, n_tel2 = RE_TEL_OFUSCADO.subn("<TELEFONO>", t)
    t, n_tel3 = RE_TEL_SEPARADORES_RAROS.subn("<TELEFONO>", t)
    t, n_hid = RE_HIDDEN.subn("<CONTACTO>", t)
    n_tel += n_tel2 + n_tel3
    t, n_cont = _enmascarar_contactos(t)
    n_cont += n_hid

    montos: list[dict] = []

    def _sub_monto(m: re.Match) -> str:
        numero = m.group("v") or m.group("v2")
        multiplicador = m.group("mult1") or m.group("mult2")

        valor = parse_numero(numero)

        if valor is not None and multiplicador:
            valor *= 1000
            valor = float(valor)

        mon = _moneda(m.group("mon") or m.group("mon2"))

        # Se analiza el contexto anterior y posterior al monto
        # dentro de su propia cláusula.
        inicio = max(
            t.rfind(sep, 0, m.start())
            for sep in (",", ";", "|", ".")
        ) + 1

        fin_candidatos = [
            pos
            for sep in (",", ";", "|", ".")
            if (pos := t.find(sep, m.end())) != -1
        ]
        fin = min(fin_candidatos) if fin_candidatos else len(t)

        clausula = t[inicio:fin]

        prefijo = normalizar(clausula[:m.start() - inicio])
        sufijo = normalizar(clausula[m.end() - inicio:])

        contexto = f"{prefijo} {sufijo}"

        if CTX_GARANTIA.search(contexto):
            tipo, tag = "garantia", "<MONTO_GARANTIA>"

        elif CTX_MANTENIMIENTO.search(contexto):
            tipo, tag = "mantenimiento", "<MONTO_MANTENIMIENTO>"

        elif CTX_VENTA.search(contexto):
            tipo, tag = "venta", "<MONTO_VENTA>"

        elif CTX_ALQUILER.search(contexto):
            tipo, tag = "alquiler", "<MONTO_ALQUILER>"

        elif re.search(r"\bprecio\b", prefijo):
            tipo, tag = "alquiler", "<MONTO_ALQUILER>"


        else:
            tipo, tag = "otro", "<MONTO>"

        montos.append({
            "valor": valor,
            "moneda": mon,
            "tipo": tipo,
            "texto_original": m.group(0),
            "etiqueta": tag,
            "enmascarado": True,
        })

        return tag

    t = RE_MONTO.sub(_sub_monto, t)

    return ResultadoAnonimizacion(
        t, n_tel, n_mail, n_url, n_cont, montos
    )


# Módulo NLP integrado al repositorio del Proyecto Integrador.
