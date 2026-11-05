"""Orquestador: crudo -> esquema común -> limpieza -> anonimización -> extracción -> lexicón
-> banderas de calidad -> deduplicación -> base analítica + reporte.

Cada paso es una función pura de módulo propio, por lo que se puede probar y documentar por separado
(N1 limpieza, N2 reglas, N3 lexicón, N5 dedup/calidad).
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .adaptadores import ADAPTADORES
from .anonimizar import anonimizar
from .calidad import banderas, fuga_precio, reporte_cobertura
from .config import settings
from .dedup import marcar_duplicados
from .extraccion import extraer_campos
from .geografia import clasificar_distrito
from .lexicon import extraer_atributos
from .logging_utils import get_logger
from .precio import parsear_precio
from .texto import limpiar_texto

log = get_logger()


@dataclass
class Entrada:
    fuente: str          # clave de ADAPTADORES (urbania, adondevivir, ...)
    ruta: Path
    modalidad: str       # modalidad que el equipo declara para ese archivo (alquiler/venta)


def _procesar_fila(r: pd.Series, cfg_cal: dict, cfg_ext: dict) -> dict:
    """Procesa un anuncio (ya en esquema común) y devuelve la fila de la base analítica."""
    titulo = limpiar_texto(r["titulo"])
    descr = limpiar_texto(r["descripcion"])
    caract = limpiar_texto(r["caracteristicas_texto"])
    ubic = limpiar_texto(r["ubicacion_texto"])
    precio_txt = limpiar_texto(r["precio_texto"])

    a_tit, a_des, a_car = anonimizar(titulo), anonimizar(descr), anonimizar(caract)
    contacto = a_des.n_telefonos + a_des.n_correos + a_des.n_contactos + a_car.n_telefonos + a_car.n_contactos

    fila: dict = {
        "id_anuncio": r["id_anuncio"], "portal": r["portal"], "fecha_captura": r["fecha_captura"],
        "modalidad": r["modalidad_url"] or r["modalidad_esperada"],
        "titulo_anon": a_tit.texto, "descripcion_anon": a_des.texto, "ubicacion_texto": ubic,
    }
    fila.update(parsear_precio(precio_txt))
    fila["distrito"], fila["ambito"] = clasificar_distrito(ubic, limpiar_texto(r["distrito_fuente"]))
    fila.update(extraer_campos(a_tit.texto, a_car.texto, a_des.texto, cfg_ext))
    fila.update(extraer_atributos(" | ".join(x for x in (a_car.texto, a_des.texto) if x)))
    fila["n_palabras"] = len((a_des.texto or "").split())
    fila["flag_contacto_en_texto"] = contacto > 0
    fila["flag_fuga_precio"] = fuga_precio(
        a_des.montos + a_tit.montos, fila["precio_pen_pub"], fila["precio_usd_pub"], cfg_cal["tolerancia_fuga"]
    )
    fila.update(banderas(fila, cfg_cal))
    return fila


def ejecutar(entradas: list[Entrada], dir_salida: Path, fecha_captura: str | None = None,
             modalidad_objetivo: str | None = None) -> pd.DataFrame:
    """Corre el pipeline completo sobre una o varias fuentes y escribe la base analítica y el reporte."""
    cfg = settings()
    random.seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    objetivo = modalidad_objetivo or cfg["modalidad_objetivo"]
    dir_salida.mkdir(parents=True, exist_ok=True)
    reporte: dict = {"modalidad_objetivo": objetivo, "fuentes": {}}

    partes = []
    for e in entradas:
        log.info("Fuente %s (modalidad declarada: %s) <- %s", e.fuente, e.modalidad, e.ruta)
        adaptador = ADAPTADORES[e.fuente](e.modalidad, fecha_captura)
        esquema = adaptador.a_esquema(adaptador.leer(e.ruta))
        n_in = len(esquema)
        modal = esquema["modalidad_url"].fillna(esquema["modalidad_esperada"])
        excluidas = int((modal != objetivo).sum())
        esquema = esquema[modal == objetivo]
        log.info("  %d anuncios en esquema; %d excluidos por modalidad distinta de '%s'", n_in, excluidas, objetivo)
        reporte["fuentes"][e.fuente] = {"anuncios_esquema": n_in, "excluidos_por_modalidad": excluidas}
        partes.append(esquema)

    esquema_total = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if esquema_total.empty:
        log.warning("No quedaron anuncios de modalidad '%s'; no se genera base analítica.", objetivo)
        reporte["filas_salida"] = 0
        (dir_salida / "reporte_calidad.json").write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
        return pd.DataFrame()

    cfg_cal = {**cfg["calidad"], "incluir_callao": cfg.get("incluir_callao", False)}
    filas = []
    for _, r in esquema_total.iterrows():
        try:
            filas.append(_procesar_fila(r, cfg_cal, cfg["calidad"]))
        except Exception:  # un anuncio defectuoso no debe detener el lote
            log.exception("Error procesando %s; se omite", r.get("url"))
    df = pd.DataFrame(filas)
    df = marcar_duplicados(df, cfg["dedup"])

    cols_cobertura = ["precio_pen_pub", "precio_usd_pub", "distrito", "tipo_inmueble", "dormitorios", "banos",
                      "estacionamientos", "area_titulo_m2", "area_terreno_m2", "area_construida_m2",
                      "area_total_m2", "n_pisos", "antiguedad_anios", "descripcion_anon"]
    reporte.update({
        "filas_salida": len(df),
        "por_portal": df["portal"].value_counts().to_dict(),
        "cobertura_pct": reporte_cobertura(df, cols_cobertura),
        "banderas": {c: int(df[c].sum()) for c in df.columns if c.startswith("flag_")},
        "duplicados": int(df["es_duplicado"].sum()),
        "ambito": df["ambito"].value_counts().to_dict(),
        "fecha_captura_disponible": bool(df["fecha_captura"].notna().any()),
    })
    df.to_csv(dir_salida / "base_analitica.csv", index=False, encoding="utf-8-sig")
    (dir_salida / "reporte_calidad.json").write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Listo: %d filas -> %s", len(df), dir_salida)
    return df
