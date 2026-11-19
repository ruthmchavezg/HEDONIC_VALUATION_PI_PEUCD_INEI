"""Construye la base final de alquileres (Lima Metropolitana) y la guarda en datafinal/.

Fuentes:
  * Portales: Adondevivir, Urbania (departamentos y casas) y Babilonia -> pipeline NLP (pi_nlp).
  * Redes sociales (Facebook Marketplace y TikTok):
      - silver de tu amiga (ya filtrado y estructurado, sin texto) -> pi_nlp/silver.py
      - crudo de descartados (con texto) -> pipeline NLP con el adaptador "social"; solo se rescatan
        las filas descartadas por "sin precio" a las que el pipeline SI les encuentra precio en
        Lima Metropolitana (el resto de descartados era correcto: venta, fuera de Lima, sin precio).

Pasos:
  1. Agrega fecha_captura a los CSV de Urbania (copias en data/interim; los originales no se tocan).
  2. Corre el pipeline NLP en los portales y en el crudo de redes sociales; carga el silver.
  3. Une las fuentes y convierte a soles los precios que solo vienen en dolares.
  4. Agrupa los anuncios repetidos del mismo inmueble (dentro de una fuente y entre fuentes)
     y conserva uno por grupo.
  5. Filtra: Lima Metropolitana, alquiler mensual, tipos de inmueble elegidos y precio < 1.000.000 de
     soles; marca apto_modelo.
  6. Arma la tabla final con SOLO las 40 variables de tu hoja (m_, e_, ec_, cf_, cc_; nombres y orden
     exactos) y guarda Excel y CSV en datafinal/, con diccionario de variables (valores y cobertura por
     fuente), definicion de los valores categoricos, ranking por distrito, depuracion y resumen por origen.
     Se eliminan los anuncios con flag_sin_precio = True y las columnas de COLUMNAS_A_BORRAR.

Uso (desde la raiz del repositorio, con el parche de pi_nlp ya copiado):
    python scripts/construir_base_final.py
"""
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.simplefilter("ignore", category=FutureWarning)

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

# ============================== CONFIGURACION (edita aqui) ==============================
ENTRADAS = [
    # (portal, ruta del CSV, fecha_captura  |  None si el CSV ya la trae)
    ("adondevivir", "data/raw/portals/bronce_alquileres_adondevivir.csv", None),
    ("urbania", "data/raw/portals/bronce_alquileres_urbania_casas.csv", "2026-11-08"),
    ("urbania", "data/raw/portals/bronce_alquileres_urbania_departamentos.csv", "2026-11-11"),
    ("babilonia", "data/raw/portals/bronce_alquileres_babilonia.csv", None),
]
# Redes sociales (si un archivo no existe, se omite con un aviso y el resto sigue igual)
SOCIAL_SILVER = "data/interim/social_clean/alquileres_social_silver.csv"
SOCIAL_DESCARTADOS = "data/interim/social_clean/alquileres_social_descartados.csv"
RESCATAR_DESCARTADOS = False
# Del crudo de descartados solo se rescata el motivo "3. Sin precio" (el pipeline encuentra el precio
# en la cabecera o en el texto). Los motivos 2 (venta), 4 y 5 (ubicacion dudosa / fuera de Lima) no
# se rescatan: van a la hoja descartados_revision para revisarlos a mano.
MOTIVOS_RESCATABLES = ("3",)

CARPETA_INTERMEDIA = RAIZ / "data" / "interim"
CARPETA_PROCESADA = RAIZ / "data" / "processed"
CARPETA_FINAL = RAIZ / "data/interim"
NOMBRE_FINAL = "silver_alquileres_scraping_nlp"

AMBITO = "lima_metropolitana"
# Para el modelo principal deja solo departamentos: TIPOS_INCLUIDOS = ("departamento",)
TIPOS_INCLUIDOS = ("departamento", "casa", "cuarto")

# Precios solo en dolares -> soles. None = se calcula con la mediana de precio_pen / precio_usd de los
# anuncios que traen ambos precios (asi queda el mismo tipo de cambio que usan los portales).
TIPO_CAMBIO_USD_PEN = None

# Valores altos: se eliminan de la base final los anuncios con precio >= este tope (en soles). Un alquiler
# mensual de 1 millon o mas es casi siempre un precio de venta o un error de digitacion.
PRECIO_TOPE_PEN = 1_000_000

# Rangos razonables para apto_modelo (precio mensual en soles y area en m2)
PRECIO_MIN, PRECIO_MAX = 500, 30000
# Una habitacion se alquila mucho mas barata que un departamento: minimo propio para tipo "cuarto".
PRECIO_MIN_CUARTO = 150
AREA_MIN, AREA_MAX = 15, 1000
# True = no apto si la coordenada es aproximada (ZONE: centro de zona/distrito, no del inmueble).
# Para asignar estrato INEI por manzana conviene True; para un efecto fijo de distrito basta False.
EXIGIR_COORD_CONFIABLE = False
# False = la tabla final trae todos los anuncios de la base (apto_modelo y motivo_no_apto solo se ven en
# base_final_alquileres_completa.csv; se cruzan por m_id_anuncio). True = la tabla final solo trae los aptos.
SOLO_APTOS_EN_BASE_FINAL = False

# Criterio de duplicados (mismo inmueble)
TOL_PRECIO, TOL_AREA = 0.03, 0.03                  # tolerancia estandar
UMBRAL_TEXTO_MISMO_DISTRITO = 0.50                 # similitud de texto minima si el distrito coincide (o falta)
UMBRAL_TEXTO_DISTRITO_DISTINTO = 0.85              # si los distritos difieren, se exige casi el mismo texto
UMBRAL_TEXTO_AJUSTE = 0.90                         # mismo texto con precio/area algo editados
TOL_PRECIO_AJUSTE, TOL_AREA_AJUSTE = 0.08, 0.10
# Anuncios SIN texto (silver): mismo inmueble si la coordenada precisa esta a <= 40 m, el precio
# difiere <= 1 %, coinciden los dormitorios y (banos iguales o area dentro de 3 %).
DIST_ESTRUCTURAL_M, TOL_PRECIO_ESTRUCTURAL = 40, 0.01
# =========================================================================================

PRIORIDAD_PORTAL = {"urbania": 0, "adondevivir": 1, "babilonia": 2, "tiktok": 3,
                    "facebook_marketplace": 4, "social": 5}
PRECISION_BUENA = ("EXACT", "DIRECCION")
COLS_COMPLETITUD = [
    "distrito", "precio_pen_pub", "dormitorios", "banos", "area_total_m2", "area_techada_m2",
    "area_construida_m2", "area_terreno_m2", "piso_departamento", "antiguedad_anios",
    "estacionamientos",
]
COLS_AL_INICIO = [
    "grupo_inmueble", "n_anuncios_grupo", "id_anuncio", "portal", "canal", "origen_dato",
    "fecha_captura", "distrito", "ambito", "tipo_inmueble", "tipo_alquiler", "precio_pen_pub",
    "precio_usd_pub", "precio_convertido_usd", "dormitorios", "banos", "estacionamientos",
    "area_total_m2", "latitud", "longitud", "precision_coord", "apto_modelo", "motivo_no_apto",
]


def _buscar(ruta):
    """Ruta absoluta del CSV; si el nombre no coincide exacto busca uno parecido en la misma carpeta."""
    origen = RAIZ / ruta
    if origen.exists():
        return origen
    palabras = Path(ruta).stem.split("_")[:4]
    carpeta = RAIZ / Path(ruta).parent
    candidatos = [p for p in carpeta.glob("*.csv") if all(w in p.stem for w in palabras)] \
        if carpeta.exists() else []
    if len(candidatos) == 1:
        print(f"Uso {candidatos[0].name} (no estaba exacto {Path(ruta).name})")
        return candidatos[0]
    return None


# ------------------------------ 1-2. Entradas y pipeline ------------------------------


def preparar_entradas():
    from cleaning.cleaning_silver.pipeline import Entrada

    CARPETA_INTERMEDIA.mkdir(parents=True, exist_ok=True)
    entradas = []
    for portal, ruta, fecha in ENTRADAS:
        origen = _buscar(ruta)
        if origen is None:
            raise SystemExit(f"No encuentro {RAIZ / ruta}. Revisa ENTRADAS al inicio del script.")
        if fecha:
            df = pd.read_csv(origen, encoding="utf-8-sig", dtype=str,
                             keep_default_na=False, na_values=[""])
            df["fecha_captura"] = fecha
            destino = origen.parent / f"{origen.stem}_con_fecha.csv"
            df.to_csv(destino, index=False, encoding="utf-8-sig")
            origen = destino
        entradas.append(Entrada(portal, origen, "alquiler"))
    return entradas


def correr_pipeline(entradas, carpeta, exigir_coordenadas=True):
    from cleaning.cleaning_silver.pipeline import ejecutar

    df = ejecutar(entradas, carpeta)
    if df.empty:
        raise SystemExit("El pipeline no devolvio filas.")
    if exigir_coordenadas and "latitud" not in df.columns:
        raise SystemExit(
            "El pipeline no trae las coordenadas: falta copiar los archivos del parche "
            "(parche_pi_nlp.zip) sobre src/pi_nlp y volver a ejecutar."
        )
    reporte = json.loads((carpeta / "reporte_calidad.json").read_text(encoding="utf-8"))
    df = df.rename(columns={"id_grupo_dup": "id_grupo_dup_pipeline",
                            "es_duplicado": "es_duplicado_pipeline"})
    return df.reset_index(drop=True), reporte


# ------------------------------ 2b. Redes sociales ------------------------------


def procesar_descartados():
    """Crudo de descartados -> pipeline NLP. Devuelve (df, reporte, n_filas_crudo) o None."""
    from cleaning.cleaning_silver.pipeline import Entrada

    ruta = _buscar(SOCIAL_DESCARTADOS)
    if ruta is None:
        print(f"AVISO: no encuentro {SOCIAL_DESCARTADOS}; se omite el crudo de descartados.")
        return None
    df, reporte = correr_pipeline([Entrada("social", ruta, "alquiler")],
                                  CARPETA_PROCESADA / "descartados", exigir_coordenadas=False)
    crudo = pd.read_csv(ruta, encoding="utf-8-sig", dtype=str, keep_default_na=False, na_values=[""])
    crudo["id_anuncio"] = crudo["portal"].fillna("social").str.strip() + "-" + crudo["id_contenido"].str.strip()
    extra = (crudo[["id_anuncio", "motivo_descarte", "url"]].drop_duplicates("id_anuncio")
             .rename(columns={"motivo_descarte": "motivo_descarte_original"}))
    df = df.merge(extra, on="id_anuncio", how="left")
    return df, reporte, len(crudo)


def separar_descartados(desc):
    """(rescatados, para_revision). Candidatas: con precio, Lima Metropolitana, alquiler mensual, no venta."""
    precio = pd.to_numeric(desc["precio_pen_pub"], errors="coerce")
    usd = pd.to_numeric(desc["precio_usd_pub"], errors="coerce")
    mixta = desc["flag_modalidad_mixta"].fillna(False).astype(bool)
    candidata = ((precio.notna() | usd.notna()) & (desc["ambito"] == AMBITO)
                 & (desc["tipo_alquiler"] == "mensual") & ~mixta)
    motivo = desc["motivo_descarte_original"].fillna("").str.strip().str[:1]
    rescatada = candidata & motivo.isin(MOTIVOS_RESCATABLES) & RESCATAR_DESCARTADOS
    return desc[rescatada].copy(), desc[candidata & ~rescatada].copy()


def cargar_silver():
    from pi_nlp.silver import cargar_silver as _cargar

    ruta = _buscar(SOCIAL_SILVER)
    if ruta is None:
        print(f"AVISO: no encuentro {SOCIAL_SILVER}; se omite el silver de redes sociales.")
        return None
    return _cargar(ruta)


# ------------------------------ 3. Union de fuentes ------------------------------


def unir_fuentes(portales, rescatados, silver):
    partes = [portales.assign(origen_dato="portal", canal="portal")]
    if rescatados is not None and len(rescatados):
        r = rescatados.copy()
        r["id_grupo_dup_pipeline"] = np.nan      # los ids de grupo de otra corrida no son comparables
        r["es_duplicado_pipeline"] = np.nan
        partes.append(r.assign(origen_dato="descartado_rescatado", canal="red_social"))
    if silver is not None and len(silver):
        partes.append(silver.assign(origen_dato="silver_amiga", canal="red_social"))
    out = pd.concat(partes, ignore_index=True, sort=False)
    out["fecha_captura"] = out["fecha_captura"].astype("string").str[:10]
    return out


def convertir_usd(df):
    """Precio solo en dolares -> soles (precio_convertido_usd = True). Devuelve (df, tipo_de_cambio, n)."""
    pen = pd.to_numeric(df["precio_pen_pub"], errors="coerce")
    usd = pd.to_numeric(df["precio_usd_pub"], errors="coerce")
    ambos = pen.notna() & usd.notna() & usd.gt(0)
    tc = TIPO_CAMBIO_USD_PEN or float((pen[ambos] / usd[ambos]).median())
    solo_usd = pen.isna() & usd.gt(0)
    df = df.copy()
    df["precio_pen_pub"] = pen.where(~solo_usd, (usd * tc).round(0))
    df["precio_convertido_usd"] = solo_usd
    # el mantenimiento que solo viene en dolares tambien se pasa a soles (mismo tipo de cambio)
    m_pen = pd.to_numeric(df["mantenimiento_pen"], errors="coerce")
    m_usd = pd.to_numeric(df["mantenimiento_usd"], errors="coerce")
    m_solo_usd = m_pen.isna() & m_usd.notna()
    df["mantenimiento_pen"] = m_pen.where(~m_solo_usd, (m_usd * tc).round(0))
    df["mantenimiento_convertido_usd"] = m_solo_usd
    return df, tc, int(solo_usd.sum())


# ------------------------------ 4. Duplicados (mismo inmueble) ------------------------------

RE_COD_CORCHETE = re.compile(r"\{\[([^\]]{3,20})\]\}")
RE_COD_PALABRA = re.compile(r"cod(?:igo)?\.?\s*:?\s*([a-z0-9][a-z0-9\- ]{2,14}\d)")
RE_COD_SUELTO = re.compile(r"\b([a-z]{2,6}-?\d{3,5})\b")


def _plano(texto):
    t = unicodedata.normalize("NFKD", str(texto).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _shingles(texto):
    t = re.sub(r"<[a-z_]+>", " ", _plano(texto))
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    w = t.split()
    return set(zip(w, w[1:], w[2:])) if len(w) >= 3 else set()


def _codigos(texto):
    """Codigos de unidad escritos en el anuncio (HEL2909, Cod. DS-SIVS174...). Dos anuncios con
    codigos distintos son unidades distintas aunque el resto del texto sea la misma plantilla."""
    t = _plano(texto)
    out = set()
    for rx in (RE_COD_CORCHETE, RE_COD_PALABRA, RE_COD_SUELTO):
        for m in rx.finditer(t):
            c = re.sub(r"[^a-z0-9]", "", m.group(1))
            if len(c) >= 5 and any(ch.isdigit() for ch in c):
                out.add(c)
    return out


def _similitud(a, b):
    if not a or not b:
        return 0.0, 0.0
    inter = len(a & b)
    return inter / len(a | b), inter / min(len(a), len(b))   # (jaccard, contencion)


def agrupar_duplicados(df):
    """Devuelve (grupos, n_aristas_estructurales): cada grupo es una lista de posiciones de fila
    que corresponden al mismo inmueble."""
    n = len(df)

    def num(c):
        return pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)

    pen = num("precio_pen_pub").tolist()
    area_np = num("area_total_m2")
    for c in ("area_techada_m2", "area_construida_m2"):
        area_np = np.where(np.isnan(area_np), num(c), area_np)
    area = area_np.tolist()
    dor, ban, piso = num("dormitorios").tolist(), num("banos").tolist(), num("piso_departamento").tolist()
    lat, lon = num("latitud").tolist(), num("longitud").tolist()
    tipo = df["tipo_inmueble"].fillna("").astype(str).tolist()
    dist = df["distrito"].fillna("").astype(str).tolist()
    prec = df["precision_coord"].fillna("").astype(str).tolist()

    desc = df["descripcion_anon"].fillna("").astype(str)
    titu = df["titulo_anon"].fillna("").astype(str)
    ubic = df["ubicacion_texto"].fillna("").astype(str)
    shing = [_shingles(d + " " + u) for d, u in zip(desc, ubic)]
    codigos = [_codigos(t + " " + d) for t, d in zip(titu, desc)]
    # Un anuncio "sin texto" (silver) solo trae la direccion: compararla como si fuera el texto seria
    # tomar cualquier anuncio que la mencione como duplicado, por eso se tratan aparte.
    sin_texto = [len(d.strip()) < 40 for d in desc]
    ubic_norm = [" ".join(re.sub(r"[^a-z0-9 ]+", " ", _plano(u)).split()) for u in ubic]

    def nulo(x):
        return x != x

    def rel(x, y):
        return abs(x - y) / max(abs(x), abs(y))

    def difieren(v, a, b):
        return not nulo(v[a]) and not nulo(v[b]) and v[a] != v[b]

    def metros(a, b):
        dy = (lat[a] - lat[b]) * 110540
        dx = (lon[a] - lon[b]) * 111320 * math.cos(math.radians((lat[a] + lat[b]) / 2))
        return math.hypot(dx, dy)

    def choque_basico(a, b):
        return tipo[a] != tipo[b] or difieren(dor, a, b) or difieren(ban, a, b) or difieren(piso, a, b)

    def choque(a, b):
        """Contradicciones duras: impiden unir dos grupos aunque otro anuncio los conecte."""
        if choque_basico(a, b):
            return True
        if codigos[a] and codigos[b] and codigos[a].isdisjoint(codigos[b]):
            return True
        if not nulo(area[a]) and not nulo(area[b]) and rel(area[a], area[b]) > TOL_AREA_AJUSTE:
            return True
        if not nulo(pen[a]) and not nulo(pen[b]) and rel(pen[a], pen[b]) > TOL_PRECIO_AJUSTE:
            return True
        return False

    def mismo_inmueble_sin_texto(a, b, pr, ar_conocida, ar):
        """Anuncios sin texto: se exige coordenada precisa muy cercana y datos estructurales iguales."""
        if pr > TOL_PRECIO_ESTRUCTURAL:
            return False
        if nulo(dor[a]) or nulo(dor[b]):
            return False
        if dist[a] != "" and dist[b] != "" and dist[a] != dist[b]:
            return False
        coords = (prec[a] in PRECISION_BUENA and prec[b] in PRECISION_BUENA
                  and not (nulo(lat[a]) or nulo(lat[b]) or nulo(lon[a]) or nulo(lon[b])))
        if coords:
            if metros(a, b) > DIST_ESTRUCTURAL_M:
                return False
        else:
            # coordenada aproximada o ausente: se exige la misma direccion escrita (con numero o referencia)
            if len(ubic_norm[a]) < 12 or ubic_norm[a] != ubic_norm[b]:
                return False
        banos_iguales = not nulo(ban[a]) and not nulo(ban[b]) and ban[a] == ban[b]
        area_igual = ar_conocida and ar <= TOL_AREA
        return banos_iguales or area_igual

    # --- pares candidatos: se comparan precios cercanos (ventana deslizante sobre precio ordenado)
    orden = sorted((i for i in range(n) if not nulo(pen[i])), key=lambda i: pen[i])
    aristas = []
    n_estructurales = 0
    for i, a in enumerate(orden):
        tope = pen[a] / (1 - TOL_PRECIO_AJUSTE)
        for j in range(i + 1, len(orden)):
            b = orden[j]
            if pen[b] > tope:
                break
            if choque_basico(a, b):
                continue
            pr = rel(pen[a], pen[b])
            ar_conocida = not (nulo(area[a]) or nulo(area[b]))
            ar = rel(area[a], area[b]) if ar_conocida else 0.0
            if ar > TOL_AREA_AJUSTE:
                continue
            if sin_texto[a] or sin_texto[b]:
                if mismo_inmueble_sin_texto(a, b, pr, ar_conocida, ar):
                    aristas.append((0.55, a, b))
                    n_estructurales += 1
                continue
            mismo = dist[a] == "" or dist[b] == "" or dist[a] == dist[b]
            if pr <= TOL_PRECIO and ar <= TOL_AREA:
                _, cont = _similitud(shing[a], shing[b])
                umbral = UMBRAL_TEXTO_MISMO_DISTRITO if mismo else UMBRAL_TEXTO_DISTRITO_DISTINTO
                if cont >= umbral:
                    aristas.append((cont, a, b))
            elif dist[a] != "" and dist[a] == dist[b]:
                jac, cont = _similitud(shing[a], shing[b])
                if cont >= UMBRAL_TEXTO_AJUSTE and jac >= 0.75:
                    aristas.append((cont, a, b))

    # --- union de grupos, de la evidencia mas fuerte a la mas debil, sin permitir contradicciones
    aristas.sort(key=lambda t: -t[0])
    miembros = {i: [i] for i in range(n)}
    raiz = list(range(n))

    def buscar(x):
        while raiz[x] != x:
            raiz[x] = raiz[raiz[x]]
            x = raiz[x]
        return x

    for _, a, b in aristas:
        ra, rb = buscar(a), buscar(b)
        if ra == rb:
            continue
        if any(choque(x, y) for x in miembros[ra] for y in miembros[rb]):
            continue
        if len(miembros[ra]) < len(miembros[rb]):
            ra, rb = rb, ra
        raiz[rb] = ra
        miembros[ra] += miembros.pop(rb)
    return list(miembros.values()), n_estructurales


# Datos que, si al anuncio representante le faltan, se toman de otro anuncio del MISMO inmueble
COLS_COMPLETAR = [
    "dormitorios", "banos", "banos_propios", "banos_compartidos", "banos_visita", "estacionamientos",
    "area_total_m2", "area_construida_m2", "area_techada_m2", "area_terreno_m2", "antiguedad_anios",
    "anio_construccion", "cant_pisos", "piso_departamento", "mantenimiento_pen",
    "mantenimiento_usd",
]


def completar_desde_duplicados(todo, unicos):
    """Un inmueble publicado en varios portales rara vez trae los mismos datos en todos (uno trae el
    mantenimiento, otro el ano de construccion). El representante conserva SUS valores y solo se le
    completa lo que le falta con el primer valor disponible de otro anuncio del grupo (por prioridad de
    portal). Los atributos 0/1 y "mantenimiento incluido" valen 1 si algun anuncio del grupo lo afirma."""
    unicos = unicos.copy()
    orden = todo.assign(_prio=todo["portal"].map(lambda p: PRIORIDAD_PORTAL.get(p, 9)))
    orden = orden.sort_values(["grupo_inmueble", "_prio"], kind="stable")
    g = orden["grupo_inmueble"]
    n = pd.Series(0, index=unicos.index)
    for c in COLS_COMPLETAR:
        if c not in unicos.columns:
            continue
        primero = pd.to_numeric(orden[c], errors="coerce").groupby(g).first()
        actual = pd.to_numeric(unicos[c], errors="coerce")
        candidato = unicos["grupo_inmueble"].map(primero)
        lleno = actual.isna() & candidato.notna()
        unicos[c] = actual.where(~lleno, candidato)
        n += lleno.astype(int)
    for c in [c for c in unicos.columns if c.startswith("attr_")]:
        mx = pd.to_numeric(orden[c], errors="coerce").groupby(g).max()
        actual = pd.to_numeric(unicos[c], errors="coerce")
        union = pd.concat([actual, unicos["grupo_inmueble"].map(mx)], axis=1).max(axis=1)
        unicos[c] = union
    if "mantenimiento_incluido" in unicos.columns:
        inc = orden["mantenimiento_incluido"].fillna(False).astype(bool).groupby(g).any()
        unicos["mantenimiento_incluido"] = (unicos["mantenimiento_incluido"].fillna(False).astype(bool)
                                            | unicos["grupo_inmueble"].map(inc).fillna(False).astype(bool))
    if "banos_tipo" in unicos.columns:   # una habitacion "sin_dato" que gano su tipo de bano desde un duplicado
        p = pd.to_numeric(unicos["banos_propios"], errors="coerce")
        c = pd.to_numeric(unicos["banos_compartidos"], errors="coerce")
        sin = unicos["banos_tipo"].eq("sin_dato")
        unicos.loc[sin & p.gt(0), "banos_tipo"] = "propio"
        unicos.loc[sin & c.gt(0), "banos_tipo"] = "compartido"
    unicos["campos_completados_de_duplicados"] = n
    return unicos


def banos_por_defecto(unicos):
    """Tipo de baño cuando el texto no lo dice (se aplica DESPUES de unir duplicados: si otro anuncio del
    mismo inmueble si lo decia, ya se le completo y no entra aqui).
      * Habitacion / cuarto (banos_tipo = "sin_dato") con n >= 1 baños en la ficha: se toma COMPARTIDO
        (banos_compartidos = n, banos_propios = 0). Sin dato de baños (o 0) queda vacio.
      * Casa / departamento / minidepartamento: el baño es PROPIO. Si aun no hay cantidad de propios y la ficha
        trae el total, banos_propios = total (sin el medio baño); y banos_compartidos = 0.
    El caso "mixto" (el anuncio ofrece habitaciones con baños distintos) no se decide."""
    unicos = unicos.copy()
    total = pd.to_numeric(unicos["banos"], errors="coerce")
    n = np.floor(total)
    tipo = unicos["banos_tipo"]
    if "es_habitacion" in unicos.columns:
        es_hab = unicos["es_habitacion"].fillna(False).astype(bool)
    else:
        es_hab = tipo.notna()
    hab = es_hab & tipo.eq("sin_dato") & n.ge(1)
    unicos.loc[hab, "banos_compartidos"] = n[hab]
    unicos.loc[hab, "banos_propios"] = 0
    unicos.loc[hab, "banos_evidencia"] = [f"por defecto: la ficha indica {int(v)} bano(s) y el texto no dice de quien es"
                                          for v in n[hab]]
    unicos.loc[hab, "banos_tipo"] = "compartido"
    propios = pd.to_numeric(unicos["banos_propios"], errors="coerce")
    resto = ~es_hab & propios.isna() & n.ge(0)
    unicos.loc[resto, "banos_propios"] = n[resto]
    propios = pd.to_numeric(unicos["banos_propios"], errors="coerce")
    unicos.loc[~es_hab & propios.notna(), "banos_compartidos"] = 0       # baño propio => 0 compartidos
    return unicos, int(hab.sum()), int(resto.sum())


def marcar_grupos(df):
    """Agrega grupo_inmueble / es_representante a todas las filas y devuelve (df_todo, df_unicos)."""
    grupos, n_estructurales = agrupar_duplicados(df)

    # Se fusionan ademas los grupos que comparten id_anuncio (misma URL: es el mismo inmueble aunque el
    # texto haya cambiado entre capturas) o que el pipeline marco como duplicados (dedup.py), salvo que
    # los codigos de unidad escritos en el anuncio demuestren que son unidades distintas.
    cods = [_codigos(str(t) + " " + str(d)) for t, d in
            zip(df["titulo_anon"].fillna(""), df["descripcion_anon"].fillna(""))]
    sets_grupo = [[cods[i] for i in g if cods[i]] for g in grupos]
    padre = list(range(len(grupos)))

    def raiz_g(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def unidades_distintas(ka, kb):
        return any(x.isdisjoint(y) for x in sets_grupo[ka] for y in sets_grupo[kb])

    por_id, por_pipeline = {}, {}
    pip_col = df["id_grupo_dup_pipeline"].tolist() if "id_grupo_dup_pipeline" in df.columns else None
    for k, g in enumerate(grupos):
        for i in g:
            por_id.setdefault(df["id_anuncio"].iat[i], set()).add(k)
            if pip_col is not None and pip_col[i] == pip_col[i] and pip_col[i] is not None:
                por_pipeline.setdefault(pip_col[i], set()).add(k)
    for clave, vecinos in ((por_id, False), (por_pipeline, True)):
        for ks in clave.values():
            ks = sorted(ks)
            for otro in ks[1:]:
                a, b = raiz_g(ks[0]), raiz_g(otro)
                if a == b:
                    continue
                if vecinos and unidades_distintas(ks[0], otro):
                    continue
                padre[b] = a
    fusion = {}
    for k, g in enumerate(grupos):
        fusion.setdefault(raiz_g(k), []).extend(g)
    grupos = sorted(fusion.values(), key=min)

    completitud = df[[c for c in COLS_COMPLETITUD if c in df.columns]].notna().sum(axis=1).tolist()
    tiene_dist = (df["distrito"].fillna("").astype(str) != "").astype(int).tolist()
    tiene_coord = df["latitud"].notna().astype(int).tolist()
    precisa = df["precision_coord"].isin(PRECISION_BUENA).astype(int).tolist()
    prio = df["portal"].map(lambda p: PRIORIDAD_PORTAL.get(p, 9)).tolist()
    # a igual completitud se prefiere el anuncio con texto (rinde mas atributos NLP)
    con_texto = df["descripcion_anon"].notna().astype(int).tolist()

    def puntaje(i):
        return (tiene_dist[i], tiene_coord[i], precisa[i], completitud[i], con_texto[i], -prio[i], -i)

    gid = [None] * len(df)
    rep = [False] * len(df)
    for k, g in enumerate(grupos, 1):
        for i in g:
            gid[i] = f"G{k:05d}"
        rep[max(g, key=puntaje)] = True

    todo = df.copy()
    todo["grupo_inmueble"] = gid
    todo["es_representante"] = rep

    precio = pd.to_numeric(todo["precio_pen_pub"], errors="coerce")
    g = todo.assign(_p=precio).groupby("grupo_inmueble")
    meta = pd.DataFrame({
        "n_anuncios_grupo": g.size(),
        "ids_anuncios_grupo": g["id_anuncio"].agg(lambda s: ";".join(sorted(s.astype(str)))),
        "portales_grupo": g["portal"].agg(lambda s: ";".join(sorted(set(s.astype(str))))),
        "precio_pen_min_grupo": g["_p"].min(),
        "precio_pen_max_grupo": g["_p"].max(),
    })
    unicos = todo[todo["es_representante"]].merge(meta, left_on="grupo_inmueble", right_index=True)
    todo = todo.merge(meta[["n_anuncios_grupo"]], left_on="grupo_inmueble", right_index=True)
    unicos = completar_desde_duplicados(todo, unicos.reset_index(drop=True))
    return todo, unicos, n_estructurales


# ------------------------------ 5. Filtros y resumen ------------------------------


def filtrar(unicos):
    """Aplica los filtros en cadena y devuelve (base_final, pasos_de_depuracion)."""
    pasos = []
    base = unicos
    por_ambito = base["ambito"].value_counts()
    base = base[base["ambito"] == AMBITO]
    for nombre, cant in por_ambito.items():
        if nombre != AMBITO:
            pasos.append((f"Fuera de Lima Metropolitana (ambito: {nombre})", -int(cant)))

    temporada = base["flag_alquiler_temporada"].fillna(False).astype(bool)
    no_mensual = (base["tipo_alquiler"] != "mensual") | temporada
    pasos.append(("Alquiler no mensual o de temporada", -int(no_mensual.sum())))
    base = base[~no_mensual]

    # El tipo interno pasa a ser el mismo de la tabla final (habitacion / cuarto = "cuarto"), asi el filtro, el
    # precio minimo de habitaciones y el tipo de baño usan el mismo criterio. Solo entran tipos validos.
    cf_tipo, _ = tipos_usuario(base)
    tipo_final = cf_tipo.map(MAPA_TIPO_INTERNO_INV).fillna(base["tipo_inmueble"])
    tipo_ok = base["tipo_inmueble"].isin(("departamento", "casa", "cuarto")) & tipo_final.isin(TIPOS_INCLUIDOS)
    pasos.append((f"Tipo de inmueble fuera de {list(TIPOS_INCLUIDOS)}", -int((~tipo_ok).sum())))
    base = base[tipo_ok].copy()
    base["tipo_inmueble"] = tipo_final[tipo_ok]

    # flag_sin_precio = True (sin precio en soles ni en dolares): se elimina la fila; la columna se borra al
    # guardar. El silver no calcula la flag: alli se usa "sin ningun precio".
    sin_precio = base["flag_sin_precio"].fillna(False).astype(bool) if "flag_sin_precio" in base.columns \
        else pd.Series(False, index=base.index)
    sin_precio = sin_precio | (pd.to_numeric(base["precio_pen_pub"], errors="coerce").isna()
                               & pd.to_numeric(base["precio_usd_pub"], errors="coerce").isna())
    pasos.append(("Sin precio (flag_sin_precio = True): se elimina la fila", -int(sin_precio.sum())))
    base = base[~sin_precio].copy()

    # Valores altos: precio >= PRECIO_TOPE_PEN (en soles; los de dolares se comparan ya convertidos)
    p_pen = pd.to_numeric(base["precio_pen_pub"], errors="coerce")
    p_usd = pd.to_numeric(base["precio_usd_pub"], errors="coerce")
    tc = (p_pen / p_usd)[p_pen.notna() & p_usd.gt(0)].median()
    muy_alto = p_pen.ge(PRECIO_TOPE_PEN) | (p_pen.isna() & (p_usd * tc).ge(PRECIO_TOPE_PEN))
    pasos.append((f"Precio de {PRECIO_TOPE_PEN:,} soles o mas (valor atipico)".replace(",", "."),
                  -int(muy_alto.sum())))
    base = base[~muy_alto].copy()

    precio = pd.to_numeric(base["precio_pen_pub"], errors="coerce")
    base["precio_pen_pub"] = precio
    area = pd.to_numeric(base["area_total_m2"], errors="coerce")
    for c in ("area_techada_m2", "area_construida_m2"):
        area = area.fillna(pd.to_numeric(base[c], errors="coerce"))
    precio_min = np.where(base["tipo_inmueble"].eq("cuarto"), PRECIO_MIN_CUARTO, PRECIO_MIN)
    fuera_lima = base["flag_coord_fuera_lima"].fillna(False).astype(bool)
    ratio_mon = base["flag_ratio_moneda"].fillna(False).astype(bool)
    mixta = base["flag_modalidad_mixta"].fillna(False).astype(bool)
    # apto_modelo: datos completos Y valores razonables. motivo_no_apto explica cada exclusion
    # (si una fila falla en varios, aparece el primero de esta lista).
    reglas = [
        ("sin precio", precio.isna() | precio.le(0)),
        (f"precio fuera de rango ({PRECIO_MIN_CUARTO} cuartos / {PRECIO_MIN} resto - {PRECIO_MAX})",
         precio.lt(precio_min) | precio.gt(PRECIO_MAX)),
        ("sin area", area.isna()),
        (f"area fuera de {AREA_MIN}-{AREA_MAX} m2", area.lt(AREA_MIN) | area.gt(AREA_MAX)),
        ("sin dormitorios o banos", base["dormitorios"].isna() | base["banos"].isna()),
        ("sin coordenadas o fuera de Lima", base["latitud"].isna() | fuera_lima),
    ]
    if EXIGIR_COORD_CONFIABLE:
        reglas.append(("coordenada aproximada (ZONE)", base["precision_coord"].eq("ZONE")))
    reglas += [
        ("moneda inconsistente (soles vs dolares)", ratio_mon),
        ("posible venta o modalidad mixta", mixta),
    ]
    motivo = pd.Series("", index=base.index)
    for nombre, falla in reglas:
        motivo = motivo.mask((motivo == "") & falla, nombre)
    base["motivo_no_apto"] = motivo
    base["apto_modelo"] = motivo == ""
    primeras = [c for c in COLS_AL_INICIO if c in base.columns]
    base = base[primeras + [c for c in base.columns if c not in primeras]]
    return base.reset_index(drop=True), pasos


def ranking_distritos(base):
    d = base["distrito"].fillna("(sin distrito)")
    t = pd.crosstab(d, base["tipo_inmueble"])
    t.insert(0, "anuncios_unicos", t.sum(axis=1))
    t["aptos_modelo"] = base.groupby(d)["apto_modelo"].sum().astype(int)
    t["pct_del_total"] = (100 * t["anuncios_unicos"] / t["anuncios_unicos"].sum()).round(1)
    t["nivel_muestra"] = pd.cut(t["anuncios_unicos"], [-1, 29, 49, 99, 10 ** 9],
                                labels=["menos de 30", "30-49", "50-99", "100 o mas"]).astype(str)
    t = t.sort_values("anuncios_unicos", ascending=False)
    t.insert(0, "ranking", t["anuncios_unicos"].rank(method="min", ascending=False).astype(int))
    return t.reset_index().rename(columns={t.index.name or "index": "distrito"})


def tabla_depuracion(info, n_unicos, pasos, n_final):
    filas = [(f"Leidos de {k}", v["anuncios_esquema"]) for k, v in info["reporte_portales"]["fuentes"].items()]
    filas.append(("Excluidos por no ser alquiler (venta) en portales",
                  -sum(v["excluidos_por_modalidad"] for v in info["reporte_portales"]["fuentes"].values())))
    if info["n_silver"]:
        filas.append(("Silver de redes sociales (leidos)", info["n_silver"]))
    if info["n_desc_crudo"]:
        filas.append(("Crudo de descartados de redes sociales (leidos)", info["n_desc_crudo"]))
        filas.append(("  - excluidos por venta o no alquiler",
                      -sum(v["excluidos_por_modalidad"] for v in info["reporte_desc"]["fuentes"].values())))
        filas.append(("  - siguen descartados (sin precio, fuera de Lima, venta...)",
                      -(info["n_desc_proc"] - info["n_rescatados"])))
    filas.append(("Anuncios a depurar (portales + silver + rescatados)", info["n_union"]))
    filas.append(("Duplicados eliminados (mismo inmueble)", -(info["n_union"] - n_unicos)))
    filas.append(("Inmuebles unicos", n_unicos))
    filas += pasos
    filas.append(("BASE FINAL", n_final))
    return pd.DataFrame(filas, columns=["paso", "anuncios"])


def resumen_por_origen(base):
    """Cuantos anuncios de la base final vienen de cada fuente y por que no son aptos."""
    motivo = base["motivo_no_apto"].replace("", "APTO PARA MODELO")
    t = pd.crosstab(motivo, base["origen_dato"], margins=True, margins_name="TOTAL")
    orden = ["APTO PARA MODELO"] + [m for m in t.index if m not in ("APTO PARA MODELO", "TOTAL")] + ["TOTAL"]
    return t.loc[orden].reset_index().rename(columns={"motivo_no_apto": "motivo"})


def hoja_revision(revision):
    if revision is None or revision.empty:
        return pd.DataFrame(columns=["id_anuncio", "motivo_descarte_original"])
    cols = ["id_anuncio", "portal", "motivo_descarte_original", "distrito", "tipo_inmueble",
            "precio_pen_pub", "precio_usd_pub", "dormitorios", "banos", "area_total_m2", "url"]
    out = revision[[c for c in cols if c in revision.columns]].copy()
    out["texto_inicio"] = revision["descripcion_anon"].fillna("").str.slice(0, 300)
    return out.sort_values(["motivo_descarte_original", "id_anuncio"]).reset_index(drop=True)


# ------------------------------ 5b. Tabla final: SOLO las variables de tu hoja ------------------------------

# Orden y nombres EXACTOS de tu hoja (columna NOMBRE). La tabla final no lleva ninguna otra columna.
COLUMNAS_FINALES = [
    "m_timestamp", "m_portal", "m_id_anuncio",
    "e_distrito", "e_direccion", "e_latitud", "e_longitud",
    "ec_precio_usd", "ec_precio_pen", "ec_mantenimiento_usd", "ec_mantenimiento_pen",
    "ec_tipo_alquiler", "ec_servicios_basicos",
    "cf_tipo_inmueble", "cf_tipo_inmueble_homologado", "cf_area_total_m2", "cf_area_construida_m2",
    "cf_dormitorios_num", "cf_banos_compartido_num", "cf_banos_propios_num", "cf_banos_visita_num",
    "cf_estacionamientos_num", "cf_anio_construccion", "cf_pisos_edificio", "cf_cant_pisos",
    "cc_amoblado", "cc_linea_blanca", "cc_agua_caliente", "cc_walk_in_closet", "cc_ascensor", "cc_piscina",
    "cc_gimnasio", "cc_lavanderia", "cc_seguridad", "cc_pet_friendly", "cc_vista_mar", "cc_coworking",
    "cc_zona_parrilla", "cc_jardin", "cc_terraza",
]

# Interpretacion de las dos variables de piso de tu hoja:
#   cf_pisos_edificio = piso donde se encuentra el departamento o la habitacion (casa = 0)
#   cf_cant_pisos     = cantidad TOTAL de pisos de la casa o del edificio que contiene la unidad
# Si en tu modelo van al reves, pon True: los nombres se intercambian (y tambien el diccionario).
PISOS_INTERCAMBIADOS = False

# Columnas que se QUITAN de base_final_alquileres_completa.csv (lista de tu segunda imagen). Se usan
# durante el proceso (filtros, duplicados, tipos) y se borran recien al guardar. Los archivos
# intermedios de data/processed/ conservan todas las columnas para poder trazar cualquier fila.
COLUMNAS_A_BORRAR = [
    "flag_fuga_precio", "flag_ratio_moneda", "n_palabras", "flag_contacto_en_texto", "flag_precio_ambiguo",
    "flag_area_atipica", "flag_area_sospechosamente_pequena", "flag_area_construida_techada_igual",
    "flag_area_total_menor_techada", "flag_area_total_menor_terreno", "flag_texto_corto",
    "flag_contradiccion", "flag_modalidad_mixta", "flag_alquiler_temporada", "flag_ambito",
    "flag_sin_coordenadas", "flag_coord_fuera_lima", "id_grupo_dup_pipeline", "es_duplicado_pipeline",
    "tipo_inmueble_detalle", "servicios_basicos_pen", "attr_alarma", "attr_vista_calle", "attr_vista_golf",
    "attr_cerca_universidad", "flag_area_pies_corregida", "mantenimiento_convertido_usd",
    "es_representante", "portales_grupo", "precio_pen_min_grupo", "precio_pen_max_grupo",
    "campos_completados_de_duplicados",
    "flag_sin_precio",      # ademas se eliminan las FILAS con flag_sin_precio = True (ver filtrar)
]

# Atributos cualitativos del proyecto -> nombres posibles del atributo en la base (lexicon.yaml / silver)
ATRIBUTOS_ESTANDAR = [
    ("cc_amoblado", ["amoblado"]),
    ("cc_linea_blanca", ["linea_blanca"]),
    ("cc_agua_caliente", ["agua_caliente"]),
    ("cc_walk_in_closet", ["walk_in_closet"]),
    ("cc_ascensor", ["ascensor"]),
    ("cc_piscina", ["piscina"]),
    ("cc_gimnasio", ["gimnasio"]),
    ("cc_lavanderia", ["lavanderia"]),
    ("cc_seguridad", ["seguridad"]),
    ("cc_pet_friendly", ["mascotas", "pet_friendly"]),
    ("cc_vista_mar", ["vista_mar"]),
    ("cc_coworking", ["coworking"]),
    ("cc_zona_parrilla", ["zona_parrilla", "parrilla"]),
    ("cc_jardin", ["jardin"]),
    ("cc_terraza", ["terraza"]),
]
MAPA_TIPO_FUENTE = {"casa": "casa", "departamento": "departamento", "habitacion": "habitación",
                    "cuarto": "habitación", "mini departamento": "departamento",
                    "minidepartamento": "departamento"}
MAPA_TIPO_INTERNO = {"departamento": "departamento", "casa": "casa", "cuarto": "habitación"}
MAPA_TIPO_INTERNO_INV = {"departamento": "departamento", "casa": "casa", "habitación": "cuarto"}
MAPA_HOMOLOGADO_SILVER = {"departamento": "departamento", "mini departamento": "minidepartamento",
                          "minidepartamento": "minidepartamento", "casa": "casa",
                          "habitacion": "habitación", "cuarto": "cuarto"}
# cf_tipo_inmueble = cf_tipo_inmueble_homologado agrupado en 3 tipos
AGRUPA_TIPO = {"casa": "casa", "departamento": "departamento", "minidepartamento": "departamento",
               "habitación": "habitación", "cuarto": "habitación"}
RE_MINIDEPA = re.compile(
    r"\bmini\s*-?\s*(?:departamentos?|depas?|dptos?)\b|\bminidepa\w*|\bmonoambientes?\b"
    r"|\bmono\s+ambientes?\b|\bloft\b|\bstudio\b"
)
RE_CUARTO = re.compile(r"\bcuartos?\b")
RE_HABITACION = re.compile(r"\bhabitacion(?:es)?\b")


def _entero(serie):
    """Numero entero con vacios (Int64); si el valor trae decimales se deja como esta."""
    x = pd.to_numeric(serie, errors="coerce")
    return x.round().astype("Int64") if (x.dropna() % 1 == 0).all() else x


def tipos_usuario(base):
    """(cf_tipo_inmueble, cf_tipo_inmueble_homologado).

    homologado = lo que es cada anuncio, sin reducir categorias:
        casa | departamento | minidepartamento | habitación | cuarto
    cf_tipo_inmueble = el mismo dato agrupado: casa | departamento (+ minidepartamento) | habitación (+ cuarto).

    * habitación / cuarto: lo que el pipeline marco como es_habitacion (categoria del portal "habitacion" o
      "cuarto", o titulo que lo dice). Es "cuarto" si la categoria es cuarto o el titulo / inicio de la descripcion
      dicen "cuarto" y no "habitación"; si no, "habitación".
    * casa / departamento: categoria de la fuente (si falta, tipo detectado en el texto). Es "minidepartamento" si
      el titulo o el inicio de la descripcion dicen mini departamento, minidepa, monoambiente, loft o studio.
    * silver (Facebook / TikTok): se respeta la homologacion de tu amiga (los 5 valores).
    """
    fuente = base["tipo_inmueble_fuente"].map(lambda v: _plano(v).strip() if isinstance(v, str) else None)
    por_fuente = fuente.map(MAPA_TIPO_FUENTE)
    interno = base["tipo_inmueble"].map(MAPA_TIPO_INTERNO)
    if "es_habitacion" in base.columns:
        hab = base["es_habitacion"].fillna(False).astype(bool)
    else:
        hab = por_fuente.eq("habitación") | interno.eq("habitación")
    texto = (base["titulo_anon"].fillna("") + " " + base["descripcion_anon"].fillna("").str.slice(0, 250)).map(_plano)

    hom = por_fuente.where(por_fuente.isin(["casa", "departamento"]))
    hom = hom.fillna(interno.where(interno.isin(["casa", "departamento"])))
    hom = hom.mask(hab, "habitación")
    hom = hom.mask(hom.eq("departamento") & texto.map(lambda t: bool(RE_MINIDEPA.search(t))), "minidepartamento")
    solo_cuarto = texto.map(lambda t: bool(RE_CUARTO.search(t)) and not RE_HABITACION.search(t))
    hom = hom.mask(hom.eq("habitación") & (fuente.eq("cuarto") | solo_cuarto), "cuarto")
    # silver: se respeta la homologacion de tu amiga
    detalle = base["tipo_inmueble_detalle"].map(
        lambda v: MAPA_HOMOLOGADO_SILVER.get(_plano(v).strip()) if isinstance(v, str) else None)
    hom = hom.mask(base["origen_dato"].eq("silver_amiga") & detalle.notna(), detalle)
    return hom.map(AGRUPA_TIPO), hom


def a_esquema_usuario(base):
    """Tabla final: exactamente COLUMNAS_FINALES (nombres y orden de tu hoja), nada mas."""
    num = lambda c: pd.to_numeric(base[c], errors="coerce") if c in base.columns else pd.Series(np.nan, index=base.index)
    cf_tipo, cf_hom = tipos_usuario(base)
    mixto = base["ofrece_temporal"].fillna(False).astype(bool) & base["tipo_alquiler"].eq("mensual") \
        if "ofrece_temporal" in base.columns else pd.Series(False, index=base.index)

    out = pd.DataFrame(index=base.index)
    # Metadatos
    out["m_timestamp"] = base["fecha_captura"]
    out["m_portal"] = base["portal"]
    out["m_id_anuncio"] = base["id_anuncio"]
    # Espaciales
    out["e_distrito"] = base["distrito"]
    out["e_direccion"] = base["ubicacion_texto"]
    out["e_latitud"] = num("latitud")
    out["e_longitud"] = num("longitud")
    # Economicas
    out["ec_precio_usd"] = num("precio_usd_pub")
    out["ec_precio_pen"] = num("precio_pen_pub")
    out["ec_mantenimiento_usd"] = num("mantenimiento_usd")
    out["ec_mantenimiento_pen"] = num("mantenimiento_pen")
    out["ec_tipo_alquiler"] = np.where(mixto, "temporal/mensual", "mensual")
    out["ec_servicios_basicos"] = _entero(num("attr_servicios_basicos"))
    # Fisicas
    out["cf_tipo_inmueble"] = cf_tipo
    out["cf_tipo_inmueble_homologado"] = cf_hom
    out["cf_area_total_m2"] = num("area_total_m2")
    out["cf_area_construida_m2"] = num("area_construida_m2").fillna(num("area_techada_m2"))
    out["cf_dormitorios_num"] = _entero(num("dormitorios"))
    out["cf_banos_compartido_num"] = _entero(num("banos_compartidos"))
    out["cf_banos_propios_num"] = _entero(num("banos_propios"))
    out["cf_banos_visita_num"] = _entero(num("banos_visita"))
    out["cf_estacionamientos_num"] = _entero(num("estacionamientos"))
    out["cf_anio_construccion"] = _entero(num("anio_construccion"))
    # Pisos: de la unidad (casa = 0) y total de la casa o del edificio
    piso_un = num("piso_departamento").where(lambda x: x <= 60).mask(cf_tipo.eq("casa"), 0)
    cant = num("cant_pisos")
    cant = cant.mask(cant < piso_un)                    # el edificio no puede tener menos pisos que la unidad
    unidad, total = _entero(piso_un), _entero(cant)
    if PISOS_INTERCAMBIADOS:
        unidad, total = total, unidad
    out["cf_pisos_edificio"] = unidad
    out["cf_cant_pisos"] = total
    # Cualitativas (0/1): si hay varios nombres posibles del atributo se toma el maximo
    for destino, nombres in ATRIBUTOS_ESTANDAR:
        cols = [f"attr_{n}" for n in nombres if f"attr_{n}" in base.columns]
        out[destino] = _entero(pd.concat([num(c) for c in cols], axis=1).max(axis=1)) if cols else pd.NA
    return out[COLUMNAS_FINALES]


# ------------------------------ Diccionario: una fila por variable de tu hoja ------------------------------

GRUPO_META = "Metadatos"
GRUPO_ESP = "Variables espaciales/localización"
GRUPO_ECO = "Target Economico"
GRUPO_FIS = "Características físicas"
GRUPO_CUAL = "Variables cualitativas"

_DUMMY = ("0/1 (dummy)\n1 = el anuncio lo indica (texto o ficha del portal; en redes sociales, el dato "
          "estructurado de tu amiga)\n0 = no lo indica o lo niega (\"sin ...\"). No se distingue \"no tiene\" "
          "de \"no lo dice\".")


def _piso_desc():
    """(valores, descripcion, como_se_obtiene) de las dos variables de piso, segun PISOS_INTERCAMBIADOS."""
    unidad = ("Entero >= 0, vacío si el anuncio no lo dice.\nCasa = 0.\nDepartamento / habitación: 1, 2, 3...",
              "Piso donde se encuentra el departamento o la habitación (1 = primer piso). Casa = 0.",
              "Ficha ('Piso en el que se encuentra') > título > descripción: '1er piso', '2.o piso', 'tercer piso', "
              "'piso 5'. Si el texto nombra varios pisos distintos queda vacío (pisos.py).")
    total = ("Entero >= 1, vacío si no se informa.\nSiempre >= al piso de la unidad (si no, se descarta).",
             "Cantidad TOTAL de pisos de la casa o del edificio que contiene el departamento o la habitación.",
             "Ficha ('Número de pisos', 0 = no informado) o texto: 'edificio de 12 pisos', 'casa de 3 pisos' (pisos.py).")
    return (total, unidad) if PISOS_INTERCAMBIADOS else (unidad, total)


# (grupo, nombre, valores, descripcion, como se obtiene) en el orden de COLUMNAS_FINALES
def especificacion_variables():
    piso_a, piso_b = _piso_desc()
    return [
        (GRUPO_META, "m_timestamp", "(fecha de captura)\nFormato AAAA-MM-DD",
         "Fecha en que se capturó (scrapeó) el anuncio",
         "Columna del CSV o la fecha indicada en ENTRADAS"),
        (GRUPO_META, "m_portal", "urbania\nadondevivir\nbabilonia\nfacebook_marketplace\ntiktok",
         "Fuente donde se publicó el anuncio", "Adaptador de cada fuente; en redes sociales, la columna del silver"),
        (GRUPO_META, "m_id_anuncio", "Texto único: <portal>-<id del anuncio>",
         "Identificador del anuncio. Un inmueble repetido en varias fuentes aparece UNA sola vez (se conserva el "
         "anuncio de la fuente con más datos)",
         "Detección de duplicados"),
        (GRUPO_ESP, "e_distrito", "Nombre del distrito en minúsculas (solo Lima Metropolitana)",
         "Distrito del inmueble", "Texto de ubicación + distrito de la fuente (geografia.py)"),
        (GRUPO_ESP, "e_direccion", "Texto libre",
         "Dirección o ubicación tal como la publica el anuncio (a veces solo urbanización o zona)",
         "Campo de ubicación de la fuente"),
        (GRUPO_ESP, "e_latitud", "Grados decimales (WGS84)",
         "Latitud del anuncio. Puede ser exacta, de la dirección o el centro de una zona; esa calidad "
         "(precision_coord) solo está en base_final_alquileres_completa.csv",
         "Coordenada de la fuente"),
        (GRUPO_ESP, "e_longitud", "Grados decimales (WGS84)", "Longitud del anuncio (misma advertencia que la latitud)",
         "Coordenada de la fuente"),
        (GRUPO_ECO, "ec_precio_usd", "Dólares por mes\nVacío = el anuncio solo publicó soles",
         "Precio de alquiler mensual publicado en dólares", "Precio publicado por la fuente"),
        (GRUPO_ECO, "ec_precio_pen", "Soles por mes (siempre < 1 000 000)",
         "Precio de alquiler mensual en soles. Si solo venía en dólares se convierte con el tipo de cambio mediano "
         "de los anuncios que traen ambos precios",
         "Precio publicado; conversión con TIPO_CAMBIO_USD_PEN / mediana"),
        (GRUPO_ECO, "ec_mantenimiento_usd", "Dólares por mes\nVacío = no informado (el anuncio puede incluirlo en el precio)",
         "Cuota de mantenimiento mensual publicada en dólares", "Campo del portal o texto del anuncio (costos.py)"),
        (GRUPO_ECO, "ec_mantenimiento_pen", "Soles por mes\nVacío = no informado\n0 = informado como incluido o sin cuota",
         "Cuota de mantenimiento mensual en soles (si venía en dólares se convierte con el mismo tipo de cambio)",
         "Campo del portal o texto del anuncio (costos.py); en redes sociales, el monto del silver"),
        (GRUPO_ECO, "ec_tipo_alquiler",
         "mensual\ntemporal/mensual\n\nmensual = solo tarifa mensual\ntemporal/mensual = tarifa mensual y además "
         "ofrece alquiler por temporada. Los anuncios solo de temporada o por noche se eliminaron.",
         "Modalidad de alquiler", "temporalidad.py"),
        (GRUPO_ECO, "ec_servicios_basicos",
         "(dummy)\n0/1\n1 = agua/luz INCLUIDOS en el alquiler (\"incluye agua y luz\", \"servicios incluidos\", "
         "\"todo incluido\"; en redes sociales, monto de servicios = 0)\n0 = no se indica que estén incluidos.\n"
         "La casilla \"Servicios básicos (agua/luz)\" de los portales NO cuenta: solo dice que hay conexión.",
         "Los servicios básicos están incluidos en la renta mensual",
         "Léxico (lexicon_extra.yaml, atributo servicios_basicos); silver: servicios_basicos_pen == 0"),
        (GRUPO_FIS, "cf_tipo_inmueble",
         "casa\ndepartamento\nhabitación\n\nEs cf_tipo_inmueble_homologado agrupado:\ncasa = casa\n"
         "departamento = departamento + minidepartamento\nhabitación = habitación + cuarto",
         "Tipo de inmueble en 3 categorías",
         "Agrupación de cf_tipo_inmueble_homologado"),
        (GRUPO_FIS, "cf_tipo_inmueble_homologado",
         "casa\ndepartamento\nhabitación\ncuarto\nminidepartamento\n\nCada anuncio queda como lo que es, sin reducir "
         "categorías. La definición de cada valor está en la hoja valores_categoricos.",
         "Tipo de inmueble: casa, departamento, minidepartamento, habitación o cuarto",
         "Redes sociales: homologación de tu amiga. Portales: categoría del portal + título y primeros 250 caracteres "
         "de la descripción (mini departamento, monoambiente, loft, studio, cuarto, habitación)"),
        (GRUPO_FIS, "cf_area_total_m2", "m²\nVacío = no informada",
         "Área total publicada del inmueble", "Campo del portal o texto ('N m2 área total')"),
        (GRUPO_FIS, "cf_area_construida_m2", "m²\nVacío = no informada",
         "Área construida (si no hay, el área techada)", "Campo del portal o texto"),
        (GRUPO_FIS, "cf_dormitorios_num", "Entero >= 1\nVacío = no informado",
         "Número de dormitorios", "Título > características > descripción (extraccion.py)"),
        (GRUPO_FIS, "cf_banos_compartido_num",
         "Entero\nSolo habitaciones y cuartos:\nn = el texto dice que el baño se comparte, o el texto no dice de "
         "quién es y la ficha trae n baños (por defecto se toma compartido)\n0 = el texto dice que el baño es propio\n"
         "Vacío = casas y departamentos (no aplica), anuncio mixto (habitaciones con baños distintos) o sin dato de baños",
         "Baños compartidos con otros ocupantes",
         "Texto (banos.py): 'baño compartido', 'se comparte el baño', 'comparten cocina, sala y baño', 'sin baño propio'...; "
         "si el texto no dice nada y la ficha trae baños: compartido (construir_base_final.py, banos_por_defecto)"),
        (GRUPO_FIS, "cf_banos_propios_num",
         "Entero\nCasas y departamentos: n baños de las características (sin visita ni servicio); por defecto se toma "
         "propio\nHabitaciones: n si el texto dice que es propio, 0 si es compartido (o si no lo dice y hay baño)\n"
         "Vacío = sin dato de baños o anuncio mixto",
         "Baños completos de uso propio (no cuenta el baño de servicio ni el de visita)",
         "Casas y departamentos: 'Baños : n' de la ficha (si falta, título o descripción); '2.5' = 2 propios + 1 de visita. "
         "Habitaciones: texto ('baño propio/privado/en suite', 'habitación con baño') (banos.py)"),
        (GRUPO_FIS, "cf_banos_visita_num", "(baño de visita o medio baño)\nEntero >= 0\nVacío = no informado",
         "Baños de visita o medios baños", "Texto: 'medio baño', '1/2 baño', 'baño de visita', 'toilette'"),
        (GRUPO_FIS, "cf_estacionamientos_num",
         "Entero >= 0\n'cochera' sin número = 1\n'sin cochera' = 0\nVacío = no informado",
         "Estacionamientos o cocheras propias (no cuentan los de visitas)", "Campo del portal o texto ('2 cocheras')"),
        (GRUPO_FIS, "cf_anio_construccion", "AAAA\nVacío = no informado",
         "Año de construcción del inmueble",
         "Texto ('Año de construcción: 1996'); si solo hay antigüedad: año de captura - antigüedad"),
        (GRUPO_FIS, "cf_pisos_edificio", *piso_a),
        (GRUPO_FIS, "cf_cant_pisos", *piso_b),
    ] + [
        (GRUPO_CUAL, nombre, valores, desc, como) for nombre, valores, desc, como in [
            ("cc_amoblado", _DUMMY + "\nSolo cuenta completamente amoblado ('semi amoblado' = 0).",
             "Amoblado", "Léxico con sinónimos y negaciones (lexicon.yaml + lexicon_extra.yaml)"),
            ("cc_linea_blanca",
             "(Equipado con utensilios de cocina)\n" + _DUMMY,
             "Línea blanca / cocina equipada con utensilios",
             "Léxico: 'línea blanca', refrigeradora, microondas, 'cocina equipada', 'utensilios de cocina', menaje, "
             "'totalmente equipado'... ('equipado' a secas no cuenta)"),
            ("cc_agua_caliente", _DUMMY, "Agua caliente (terma, calentador)", "Léxico"),
            ("cc_walk_in_closet",
             "(Roperos empotrados o similares)\n" + _DUMMY,
             "Walk-in closet, closet, vestidor o ropero empotrado",
             "Léxico: 'walk in closet', closet, vestidor, placard, 'ropero empotrado', 'armario empotrado'. "
             "Un 'ropero' suelto (mueble) no cuenta."),
            ("cc_ascensor", _DUMMY, "Ascensor ('sin ascensor' = 0)", "Léxico"),
            ("cc_piscina", _DUMMY, "Piscina", "Léxico"),
            ("cc_gimnasio", _DUMMY, "Gimnasio / sala de ejercicios", "Léxico"),
            ("cc_lavanderia", _DUMMY, "Lavandería / zona de lavado", "Léxico"),
            ("cc_seguridad",
             "(vigilancia 24h, alarma,etc)\n" + _DUMMY,
             "Seguridad: vigilancia, alarma, cámaras, conserje, control de acceso",
             "Léxico. La alarma contra incendios o de humo NO cuenta."),
            ("cc_pet_friendly", _DUMMY, "Acepta mascotas ('no se aceptan mascotas' = 0)", "Léxico y ficha 'Permite mascotas'"),
            ("cc_vista_mar", _DUMMY, "Vista al mar", "Léxico ('vista panorámica al mar', 'frente al mar'...)"),
            ("cc_coworking", _DUMMY, "Coworking / business center", "Léxico"),
            ("cc_zona_parrilla", _DUMMY, "Zona de parrilla / BBQ", "Léxico"),
            ("cc_jardin", _DUMMY, "Jardín ('jardín de infancia' no cuenta)", "Léxico"),
            ("cc_terraza", _DUMMY, "Terraza / rooftop / azotea", "Léxico"),
        ]
    ]


DEFINICION_TIPOS = [
    # (variable, valor, criterio)
    ("cf_tipo_inmueble", "casa", "Casa (= homologado casa)."),
    ("cf_tipo_inmueble", "departamento", "Departamento o minidepartamento (homologado departamento + minidepartamento)."),
    ("cf_tipo_inmueble", "habitación", "Habitación o cuarto (homologado habitación + cuarto)."),
    ("cf_tipo_inmueble_homologado", "casa",
     "Vivienda independiente: categoría 'Casa' del portal o 'casa' del silver. Su piso es 0 y el baño se toma propio."),
    ("cf_tipo_inmueble_homologado", "departamento",
     "Departamento completo en un edificio o condominio: categoría 'Departamento' del portal (o tipo detectado en el "
     "texto) cuyo título y primeros 250 caracteres de la descripción NO dicen mini departamento, minidepa, "
     "monoambiente, loft ni studio. Silver: 'departamento' de tu amiga. El baño se toma propio."),
    ("cf_tipo_inmueble_homologado", "minidepartamento",
     "Departamento pequeño: el título o el inicio de la descripción dicen mini departamento / minidepa / monoambiente "
     "/ loft / studio. Silver: 'mini departamento' de tu amiga. El baño se toma propio."),
    ("cf_tipo_inmueble_homologado", "habitación",
     "Habitación alquilada por separado dentro de una vivienda: categoría 'Habitación' del portal, o título que lo "
     "dice, y el anuncio la llama 'habitación'. Silver: 'habitación' de tu amiga. Si el texto no dice de quién es "
     "el baño, se toma compartido."),
    ("cf_tipo_inmueble_homologado", "cuarto",
     "Igual que habitación pero el anuncio la llama 'cuarto' (categoría 'cuarto', o el título / inicio de la "
     "descripción dicen 'cuarto' y no 'habitación'). Silver: 'cuarto' de tu amiga. La diferencia con habitación es "
     "solo el vocabulario del anuncio; el baño se toma compartido si el texto no lo aclara."),
    ("ec_tipo_alquiler", "mensual", "Solo tarifa mensual."),
    ("ec_tipo_alquiler", "temporal/mensual", "Tarifa mensual y además ofrece alquiler por temporada."),
]


def hoja_valores_categoricos(final):
    """Que significa cada valor de las variables categoricas + cuantos anuncios tiene (total y por fuente)."""
    portales = sorted(final["m_portal"].dropna().unique())
    filas = []
    for var, valor, criterio in DEFINICION_TIPOS:
        sub = final[final[var] == valor]
        fila = {"variable": var, "valor": valor, "criterio": criterio, "anuncios": len(sub),
                "% del total": round(100 * len(sub) / len(final), 1) if len(final) else None,
                "mediana_precio_pen": round(float(sub["ec_precio_pen"].median()), 0) if len(sub) else None,
                "mediana_area_total_m2": round(float(sub["cf_area_total_m2"].median()), 0)
                if sub["cf_area_total_m2"].notna().any() else None}
        for p in portales:
            fila[f"anuncios ({p})"] = int((sub["m_portal"] == p).sum())
        filas.append(fila)
    return pd.DataFrame(filas)


def diccionario_variables(final):
    """Tu hoja (TIPO DE | NOMBRE | VALORES | CODIGO) + descripcion, como se obtiene y cobertura por fuente."""
    espec = especificacion_variables()
    assert [e[1] for e in espec] == COLUMNAS_FINALES, "el diccionario no coincide con COLUMNAS_FINALES"
    grupos = [("total", final.index)] + [(p, final.index[final["m_portal"] == p])
                                         for p in sorted(final["m_portal"].dropna().unique())]
    filas = []
    for tipo, var, valores, desc, como in espec:
        fila = {"tipo_de": tipo, "nombre": var, "valores": valores, "codigo": "", "descripcion": desc,
                "como_se_obtiene": como}
        binaria = var.startswith("cc_") or var == "ec_servicios_basicos"
        for nombre, idx in grupos:
            col = final.loc[idx, var]
            fila[f"con_dato_% ({nombre})"] = round(float(100 * col.notna().mean()), 1) if len(idx) else None
            if binaria:
                x = pd.to_numeric(col, errors="coerce").astype("float64")
                fila[f"pct_si_% ({nombre})"] = round(float(100 * (x == 1).mean()), 1) if len(idx) else None
        filas.append(fila)
    return pd.DataFrame(filas)


# ------------------------------ 6. Guardado ------------------------------

ILEGAL_EXCEL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _para_excel(df):
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_object_dtype(out[c]) or pd.api.types.is_string_dtype(out[c]):
            out[c] = out[c].map(lambda v: ILEGAL_EXCEL.sub("", v)[:32000] if isinstance(v, str) else v)
    return out


def guardar(base, hojas, completa=None):
    CARPETA_FINAL.mkdir(parents=True, exist_ok=True)
    ruta_csv = CARPETA_FINAL / f"{NOMBRE_FINAL}.csv"
    ruta_xlsx = CARPETA_FINAL / f"{NOMBRE_FINAL}.xlsx"
    base.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    if completa is not None:   # columnas del pipeline (incluye el texto limpio) para auditar, sin COLUMNAS_A_BORRAR
        completa = completa.drop(columns=[c for c in COLUMNAS_A_BORRAR if c in completa.columns])
        completa.to_csv(CARPETA_FINAL / f"{NOMBRE_FINAL}_completa.csv", index=False, encoding="utf-8-sig")
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("Falta openpyxl (pip install openpyxl): guarde solo el CSV.")
        return ruta_csv, None
    try:
        with pd.ExcelWriter(ruta_xlsx, engine="openpyxl") as xw:
            _para_excel(base).to_excel(xw, sheet_name="base_final", index=False)
            for nombre, hoja in hojas.items():
                _para_excel(hoja).to_excel(xw, sheet_name=nombre, index=False)
            from openpyxl.styles import Alignment, Font
            for ws in xw.book.worksheets:
                ws.freeze_panes = "A2"
                ws.auto_filter.ref = ws.dimensions
                largas = ws.title in ("diccionario_variables", "valores_categoricos")   # textos con varias lineas
                for col in ws.columns:
                    largo = max((len(str(c.value)) for c in col[:200] if c.value is not None), default=8)
                    tope = 70 if largas else 45
                    ws.column_dimensions[col[0].column_letter].width = min(max(10, largo + 2), tope)
                for c in ws[1]:
                    c.font = Font(bold=True)
                if largas:
                    for fila in ws.iter_rows(min_row=1):
                        for c in fila:
                            c.alignment = Alignment(wrap_text=True, vertical="top")
    except PermissionError:
        raise SystemExit(f"No pude escribir {ruta_xlsx}: cierralo en Excel y vuelve a ejecutar.")
    return ruta_csv, ruta_xlsx


def main():
    CARPETA_PROCESADA.mkdir(parents=True, exist_ok=True)

    # --- portales
    portales, rep_portales = correr_pipeline(preparar_entradas(), CARPETA_PROCESADA)
    print(f"\nPortales: {len(portales)} anuncios de alquiler.")

    # --- redes sociales
    desc = procesar_descartados()
    rescatados = revision = None
    info = {"reporte_portales": rep_portales, "n_silver": 0, "n_desc_crudo": 0, "n_desc_proc": 0,
            "n_rescatados": 0, "reporte_desc": None}
    if desc is not None:
        df_desc, rep_desc, n_crudo = desc
        rescatados, revision = separar_descartados(df_desc)
        info.update(n_desc_crudo=n_crudo, n_desc_proc=len(df_desc), n_rescatados=len(rescatados),
                    reporte_desc=rep_desc)
        print(f"Descartados (crudo): {n_crudo} filas -> {len(rescatados)} rescatadas, "
              f"{len(revision)} para revision manual.")
    silver = cargar_silver()
    if silver is not None:
        info["n_silver"] = len(silver)
        print(f"Silver de redes sociales: {len(silver)} anuncios.")

    # --- union, moneda y duplicados
    union = unir_fuentes(portales, rescatados, silver)
    union, tc, n_conv = convertir_usd(union)
    info["n_union"] = len(union)
    print(f"\nUnion: {len(union)} anuncios. Precios solo en USD convertidos a soles: {n_conv} (TC {tc:.3f}).")
    print("Buscando duplicados...")
    todo, unicos, n_est = marcar_grupos(union)
    print(f"Duplicados: {len(union)} anuncios -> {len(unicos)} inmuebles unicos "
          f"({len(union) - len(unicos)} repetidos; {n_est} pares unidos por coordenada en anuncios sin texto).")
    unicos, n_hab_comp, n_dep_prop = banos_por_defecto(unicos)
    print(f"Baños por defecto: {n_hab_comp} habitaciones sin tipo legible -> compartido; "
          f"{n_dep_prop} casas/departamentos sin cantidad de propios -> total de la ficha.")

    # --- filtros y salida
    base, pasos = filtrar(unicos)
    final = a_esquema_usuario(base)
    n_compl = int(base["campos_completados_de_duplicados"].gt(0).sum())
    if SOLO_APTOS_EN_BASE_FINAL:
        pasos.append(("No aptos para el modelo (SOLO_APTOS_EN_BASE_FINAL = True)", -int((~base["apto_modelo"]).sum())))
        final = final.loc[base["apto_modelo"]].reset_index(drop=True)
    hojas = {
        "diccionario_variables": diccionario_variables(final),
        "valores_categoricos": hoja_valores_categoricos(final),
        "ranking_distritos": ranking_distritos(base),
        "depuracion": tabla_depuracion(info, len(unicos), pasos, len(final)),
        "por_origen": resumen_por_origen(base),
    }
    if revision is not None:
        hojas["descartados_revision"] = hoja_revision(revision)

    todo.to_csv(CARPETA_PROCESADA / "base_con_grupos.csv", index=False, encoding="utf-8-sig")
    ruta_csv, ruta_xlsx = guardar(final, hojas, completa=base)

    print("\n" + hojas["depuracion"].to_string(index=False))
    print("\nPor origen y motivo:")
    print(hojas["por_origen"].to_string(index=False))
    print(f"\nInmuebles a los que se les completo algun dato desde un duplicado: {n_compl}")
    print("\nTop 10 distritos:")
    print(hojas["ranking_distritos"].head(10)[["ranking", "distrito", "anuncios_unicos", "aptos_modelo"]]
          .to_string(index=False))
    print(f"\nListo. Archivos en {CARPETA_FINAL}:")
    for ruta in (ruta_xlsx, ruta_csv, CARPETA_FINAL / f"{NOMBRE_FINAL}_completa.csv"):
        if ruta:
            print("  -", ruta.name)
    print(f"Trazabilidad (todas las filas con su grupo): {CARPETA_PROCESADA / 'base_con_grupos.csv'}")


if __name__ == "__main__":
    main()
