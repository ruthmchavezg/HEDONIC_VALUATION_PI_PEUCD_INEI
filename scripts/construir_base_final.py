"""Construye la base final de alquileres (Lima Metropolitana) y la guarda en datafinal/.

Fuentes:
  * Portales: Adondevivir y Urbania (departamentos y casas) -> pipeline NLP (pi_nlp).
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
  5. Filtra: Lima Metropolitana, alquiler mensual y los tipos de inmueble elegidos; marca apto_modelo.
  6. Guarda Excel y CSV en datafinal/, con ranking por distrito, depuracion y resumen por origen.

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
    ("adondevivir", "mydata/alquileres_lima_metropolitana_a_donde_vivir.csv", None),
    ("urbania", "mydata/dataset_hedonico_urbania_departamentos.csv", "2026-11-08"),
    ("urbania", "mydata/dataset_hedonico_urbania_casas.csv", "2026-11-11"),
]
# Redes sociales (si un archivo no existe, se omite con un aviso y el resto sigue igual)
SOCIAL_SILVER = "mydata/alquileres_social_silver.csv"
SOCIAL_DESCARTADOS = "mydata/alquileres_social_descartados.csv"
RESCATAR_DESCARTADOS = False
# Del crudo de descartados solo se rescata el motivo "3. Sin precio" (el pipeline encuentra el precio
# en la cabecera o en el texto). Los motivos 2 (venta), 4 y 5 (ubicacion dudosa / fuera de Lima) no
# se rescatan: van a la hoja descartados_revision para revisarlos a mano.
MOTIVOS_RESCATABLES = ("3",)

CARPETA_INTERMEDIA = RAIZ / "data" / "interim"
CARPETA_PROCESADA = RAIZ / "data" / "processed"
CARPETA_FINAL = RAIZ / "datafinal"
NOMBRE_FINAL = "base_final_alquileres"

AMBITO = "lima_metropolitana"
# Para el modelo principal deja solo departamentos: TIPOS_INCLUIDOS = ("departamento",)
TIPOS_INCLUIDOS = ("departamento", "casa", "cuarto")

# Precios solo en dolares -> soles. None = se calcula con la mediana de precio_pen / precio_usd de los
# anuncios que traen ambos precios (asi queda el mismo tipo de cambio que usan los portales).
TIPO_CAMBIO_USD_PEN = None

# Rangos razonables para apto_modelo (precio mensual en soles y area en m2)
PRECIO_MIN, PRECIO_MAX = 500, 30000
# Una habitacion se alquila mucho mas barata que un departamento: minimo propio para tipo "cuarto".
PRECIO_MIN_CUARTO = 150
AREA_MIN, AREA_MAX = 15, 1000
# True = no apto si la coordenada es aproximada (ZONE: centro de zona/distrito, no del inmueble).
# Para asignar estrato INEI por manzana conviene True; para un efecto fijo de distrito basta False.
EXIGIR_COORD_CONFIABLE = False

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
    from pi_nlp.pipeline import Entrada

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
            destino = CARPETA_INTERMEDIA / f"{origen.stem}_con_fecha.csv"
            df.to_csv(destino, index=False, encoding="utf-8-sig")
            origen = destino
        entradas.append(Entrada(portal, origen, "alquiler"))
    return entradas


def correr_pipeline(entradas, carpeta, exigir_coordenadas=True):
    from pi_nlp.pipeline import ejecutar

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
    from pi_nlp.pipeline import Entrada

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
    return todo, unicos.reset_index(drop=True), n_estructurales


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

    tipo_ok = base["tipo_inmueble"].isin(TIPOS_INCLUIDOS)
    pasos.append((f"Tipo de inmueble fuera de {list(TIPOS_INCLUIDOS)}", -int((~tipo_ok).sum())))
    base = base[tipo_ok].copy()

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


# ------------------------------ 6. Guardado ------------------------------

ILEGAL_EXCEL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _para_excel(df):
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_object_dtype(out[c]) or pd.api.types.is_string_dtype(out[c]):
            out[c] = out[c].map(lambda v: ILEGAL_EXCEL.sub("", v)[:32000] if isinstance(v, str) else v)
    return out


def guardar(base, hojas):
    CARPETA_FINAL.mkdir(parents=True, exist_ok=True)
    ruta_csv = CARPETA_FINAL / f"{NOMBRE_FINAL}.csv"
    ruta_xlsx = CARPETA_FINAL / f"{NOMBRE_FINAL}.xlsx"
    base.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
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
            for ws in xw.book.worksheets:
                ws.freeze_panes = "A2"
                ws.auto_filter.ref = ws.dimensions
                for col in ws.columns:
                    largo = max((len(str(c.value)) for c in col[:200] if c.value is not None), default=8)
                    ws.column_dimensions[col[0].column_letter].width = min(max(10, largo + 2), 45)
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

    # --- filtros y salida
    base, pasos = filtrar(unicos)
    hojas = {
        "ranking_distritos": ranking_distritos(base),
        "depuracion": tabla_depuracion(info, len(unicos), pasos, len(base)),
        "por_origen": resumen_por_origen(base),
    }
    if revision is not None:
        hojas["descartados_revision"] = hoja_revision(revision)

    todo.to_csv(CARPETA_PROCESADA / "base_con_grupos.csv", index=False, encoding="utf-8-sig")
    ruta_csv, ruta_xlsx = guardar(base, hojas)

    print("\n" + hojas["depuracion"].to_string(index=False))
    print("\nPor origen y motivo:")
    print(hojas["por_origen"].to_string(index=False))
    print("\nTop 10 distritos:")
    print(hojas["ranking_distritos"].head(10)[["ranking", "distrito", "anuncios_unicos", "aptos_modelo"]]
          .to_string(index=False))
    print(f"\nListo. Archivos en {CARPETA_FINAL}:")
    for ruta in (ruta_xlsx, ruta_csv):
        if ruta:
            print("  -", ruta.name)
    print(f"Trazabilidad (todas las filas con su grupo): {CARPETA_PROCESADA / 'base_con_grupos.csv'}")


if __name__ == "__main__":
    main()
