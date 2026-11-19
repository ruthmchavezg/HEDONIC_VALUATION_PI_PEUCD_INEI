"""
ADONDEVIVIR: ALQUILERES DE DEPARTAMENTOS, CASAS Y HABITACIONES
Python 3.10+. Lima y Callao; --solo-lima excluye Callao. Se filtran proyectos.

INSTALACIÓN:
    python -m pip install playwright
    python -m playwright install chromium
PRUEBA (conservar este nombre o cambiarlo por el nombre real de su archivo):
    python "alquileres_adondevivir_lima(0).py" --navegador --pausa 5 --limite 10 --salida prueba_fichas.csv
RECORRIDO COMPLETO:
    python "alquileres_adondevivir_lima(0).py" --navegador --pausa 5 --salida alquileres_fichas.csv

QUÉ SE HACE Y POR QUÉ:
1. Los listados descubren los enlaces; cada ficha aporta la información completa.
2. La galería se guarda como una lista JSON de URLs originales en una sola celda.
3. Precio y mantenimiento se separan para no confundir sus importes.
4. datos_principales_generales recoge área, baños, dormitorios, antigüedad y otros
   atributos publicados en la ficha, incluidos sus nombres y unidades.
5. Se amplía Descripción y se conserva íntegra, sin repetir el título.
6. Se pulsa cada pestaña presente y se comprueba cuál está activa antes de leer.
   Características generales, Servicios, Ambientes y Exteriores tienen columnas
   independientes. Una pestaña ausente queda vacía, nunca se copia otra en su lugar.
7. Se extraen dirección y punto público del mapa de Adondevivir. No se usa OCR ni
   geocodificación de direcciones. El punto puede ser aproximado. Se conserva su
   fuente y precisión declarada; coordenadas_geograficas siempre es la última columna.
8. Se sustituyen saltos de línea internos por espacios: un anuncio = una fila.

El formato predeterminado urbania es sólo el nombre del esquema CSV; la fuente
sigue siendo Adondevivir. --formato analitico conserva variables individuales.
NAVEGACIÓN: se conserva el transporte del script 0, incluidos la sesión temporal,
las opciones de inicio, las pausas y el tratamiento de HTTP 403/429. No se agrega
perfil persistente ni modo asistido. Sólo después de cargar la ficha se ejecuta
la extracción mejorada. Use --navegador para pulsar las pestañas en pantalla.
--solo-listados y --html son modos parciales: no hacen clic ni completan fichas.

FICHAS INCOMPLETAS:
Si una ficha no publica galería/datos principales o clasifica otro tipo, se
registra en la tabla revision del mismo .avance.sqlite (ID, URL, motivo, tarjeta).
Se continúa con la siguiente y no se añade una fila incompleta al CSV. Al
reanudar no se reintentan automáticamente estas incidencias. Los errores de
conexión y HTTP 403/429 siguen deteniendo el recorrido para conservar el avance.

REANUDACIÓN AUTOMÁTICA:
Cada anuncio completo se confirma en <salida>.avance.sqlite y se exporta al CSV.
Ante un corte de Internet o Ctrl+C, repita exactamente el mismo comando y salida.
Se reutiliza el listado pendiente y se omiten los IDs ya guardados. Si el equipo
se apaga durante la exportación, el CSV se reconstruye desde SQLite al reiniciar.
Conserve CSV, .avance.sqlite y .lock; no ejecute dos procesos sobre la misma salida.
--limite cuenta anuncios totales, incluidos los anteriores; quítelo para seguir.
Al crear el avance se importa el CSV existente y los <salida>_parcial_*.csv de su
carpeta. Para otro nombre use --importar-parcial "archivo_parcial.csv".
Los parciales antiguos carecen de cursor: se revisan listados desde el principio,
pero NO se reabren sus fichas ni se duplican sus registros. Una fila mal formada
se rechaza explícitamente; no se inventan los datos perdidos en un cierre abrupto.
Use otra --salida para una captura nueva. El portal puede reordenar anuncios;
reanudar no garantiza detectar nuevos avisos insertados en páginas ya terminadas.
La fecha usa el día local del equipo. Cierre el CSV en Excel antes de ejecutar.
"""
import argparse
import sqlite3
import ast
import base64
import binascii
import math
import csv
import json
import logging
import os
import re
import time
import unicodedata
from collections import Counter, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

# =============================================
# 1. CONFIGURACIÓN GENERAL Y COLUMNAS DEL CSV
# =============================================
BASE = "https://www.adondevivir.com"
CATEGORIAS = {"habitacion": "Habitación", "departamentos": "Departamento", "casas": "Casa"}
TIPOS = {"habitacion": "Habitación", "habitaciones": "Habitación",
         "departamento": "Departamento", "departamentos": "Departamento",
         "casa": "Casa", "casas": "Casa"}
DISTRITOS = {
    "Lima": """Ancón|Ate|Barranco|Breña|Carabayllo|Chaclacayo|Chorrillos|Cieneguilla|
Comas|El Agustino|Independencia|Jesús María|La Molina|La Victoria|Lima|Lince|
Los Olivos|Lurigancho|Lurín|Magdalena del Mar|Miraflores|Pachacámac|Pucusana|
Pueblo Libre|Puente Piedra|Punta Hermosa|Punta Negra|Rímac|San Bartolo|San Borja|
San Isidro|San Juan de Lurigancho|San Juan de Miraflores|San Luis|San Martín de Porres|
San Miguel|Santa Anita|Santa María del Mar|Santa Rosa|Santiago de Surco|Surquillo|
Villa El Salvador|Villa María del Triunfo""",
    "Callao": "Bellavista|Callao|Carmen de la Legua Reynoso|La Perla|La Punta|Mi Perú|Ventanilla",
}
CARACTERISTICAS = {"area_total_m2": "CFT100", "area_techada_m2": "CFT101",
                   "dormitorios": "CFT2", "banos": "CFT3", "medios_banos": "CFT4",
                   "estacionamientos": "CFT7", "antiguedad_publicada": "CFT5"}
COLUMNAS = ["id_anuncio", "tipo_inmueble", "provincia", "distrito", "urbanizacion",
            "direccion", "latitud", "longitud", "precio_pen", "precio_usd",
            "mantenimiento_importe", "mantenimiento_moneda", *CARACTERISTICAS,
            "titulo", "descripcion", "url", "fecha_captura_utc", "fecha_scrapeo", "coordenadas_geograficas"]


# =============================================
# 2. CONFIGURACIÓN Y EXTRACCIÓN DE COORDENADAS
# =============================================
# Adondevivir publica el punto del mapa en la ficha. Algunas versiones usan
# mapLatOf/mapLngOf codificados en Base64. Se decodifican como números, sin
# ejecutar JavaScript ni usar OCR, Tesseract o geocodificación de direcciones.
# Se prioriza el mapa de la ficha y después el punto del listado. No se inventan
# coordenadas: una pareja ausente/incorrecta queda vacía y se registra un aviso.
# El punto publicado puede ser aproximado; no garantiza una dirección exacta.

def coordenada(valor, maximo):
    """Valida un decimal público o su representación Base64."""
    if valor in (None, "") or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        try:
            numero = float(base64.b64decode(str(valor), validate=True).decode("utf-8"))
        except (ValueError, UnicodeError, binascii.Error):
            return None
    return numero if math.isfinite(numero) and abs(numero) <= maximo else None


def punto_valido(lat, lon):
    lat, lon = coordenada(lat, 90), coordenada(lon, 180)
    return (lat, lon) if lat is not None and lon is not None and (lat, lon) != (0, 0) else None




def completar_coordenadas(fila, detalle):
    """Usa una pareja de la misma fuente y prepara la última celda del CSV."""
    punto = (punto_valido(detalle.get("latitud"), detalle.get("longitud")) or
             punto_valido(fila.get("latitud"), fila.get("longitud")))
    fila["latitud"], fila["longitud"] = punto or (None, None)
    fila["coordenadas_geograficas"] = f"{punto[0]}, {punto[1]}" if punto else ""
    if not punto:
        logging.warning("Coordenadas no disponibles en los datos leídos: %s", fila["url"])


def una_linea(fila):
    """Conserva el texto completo y sustituye saltos internos por espacios."""
    return {k: re.sub(r"[\r\n\v\f\x85\u2028\u2029]+", " ", v)
            if isinstance(v, str) else v for k, v in fila.items()}


# =============================================
# 3. NORMALIZACIÓN DE TEXTOS Y DISTRITOS
# =============================================
def clave(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "").casefold())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).replace("-", " ").split())


def indice_distritos(provincias):
    indice = {clave(nombre): (provincia, nombre.strip()) for provincia in provincias
              for nombre in DISTRITOS[provincia].split("|")}
    alias = {"Cercado de Lima": "Lima", "Lima Cercado": "Lima", "Cercado": "Lima",
             "Lurigancho Chosica": "Lurigancho", "Chosica": "Lurigancho",
             "Santiago de Surco (Surco)": "Santiago de Surco", "Surco": "Santiago de Surco",
             "Ate Vitarte": "Ate", "Magdalena": "Magdalena del Mar",
             "Cercado del Callao": "Callao", "Callao Cercado": "Callao"}
    for origen, destino in alias.items():
        if clave(destino) in indice:
            indice[clave(origen)] = indice[clave(destino)]
    return indice


# =============================================
# 4. ACCESO AL PORTAL Y NAVEGADOR
# =============================================
class AccesoLimitado(RuntimeError):
    """El servidor pidió detener las peticiones."""


def comprobar_acceso(estado, url, espera):
    if estado in (403, 429):
        plazo = f" Retry-After del portal: {espera}." if espera else ""
        raise AccesoLimitado(f"HTTP {estado} en {url}. Recorrido detenido.{plazo}")


def descargar(url):
    """Reintenta errores transitorios. Un bloqueo explícito se comunica al usuario."""
    peticion = Request(url, headers={"User-Agent": "AlquileresLimaResearch/1.0",
                                     "Accept": "text/html"})
    for intento in range(3):
        try:
            with urlopen(peticion, timeout=35) as respuesta:
                return respuesta.read().decode(respuesta.headers.get_content_charset() or "utf-8")
        except HTTPError as exc:
            comprobar_acceso(exc.code, url, exc.headers.get("Retry-After"))
            if exc.code not in (500, 502, 503, 504) or intento == 2:
                raise RuntimeError(f"HTTP {exc.code} en {url}") from exc
        except (URLError, TimeoutError) as exc:
            if intento == 2:
                raise RuntimeError(f"Error de conexión en {url}: {exc}") from exc
        time.sleep(2 ** (intento + 1))








@contextmanager
def transporte(navegador):
    """Mantiene una sola sesión visible para listados y fichas."""
    if not navegador:
        yield descargar
        return
    try:
        from playwright.sync_api import Error as ErrorNavegador, TimeoutError as TiempoAgotado, sync_playwright
    except ImportError as exc:
        raise RuntimeError("Instale Playwright con python -m pip install playwright "
                           "y luego python -m playwright install chromium") from exc
    try:
        with sync_playwright() as motor:
            browser = motor.chromium.launch(
                headless=False,
                ignore_default_args=["--enable-automation"],
                args=["--disable-blink-features=AutomationControlled"],
            )
            pagina = browser.new_page(locale="es-PE")

            # Comprobar la señal en la ventana local antes de visitar el portal.
            if pagina.evaluate("() => navigator.webdriver === true"):
                logging.warning("Este Chromium todavía expone navigator.webdriver=true.")

            def visitar(url):
                try:
                    respuesta = pagina.goto(url, wait_until="domcontentloaded", timeout=60000)
                    if respuesta and not respuesta.ok:
                        comprobar_acceso(respuesta.status, url, respuesta.headers.get("retry-after"))
                    if not respuesta or not respuesta.ok:
                        estado = respuesta.status if respuesta else "sin respuesta"
                        raise RuntimeError(f"El navegador recibió {estado} en {url}")
                    if "/propiedades/" not in urlsplit(url).path:
                        return listado_en_navegador(pagina, url, TiempoAgotado)
                    return capturar_ficha_navegador(pagina)
                except ErrorNavegador as exc:
                    raise RuntimeError(f"No se pudo cargar {url}: {exc}") from exc

            try:
                yield visitar
            finally:
                browser.close()
    except ErrorNavegador as exc:
        raise RuntimeError(f"Error al usar Chromium: {exc}") from exc



def listado_en_navegador(pagina, url, timeout_error):
    """Acepta el HTML inicial o los datos ya cargados en la ventana."""
    html = pagina.content()
    try:
        return leer_listado(html, url)
    except (ValueError, KeyError, TypeError):
        pass

    # Devolver sólo el listado evita copiar información de sesión del navegador.
    script = """() => {
        const lista = window.__PRELOADED_STATE__?.listStore;
        return Array.isArray(lista?.listPostings) && lista.paging
            ? {listPostings: lista.listPostings, paging: lista.paging} : false;
    }"""
    logging.info("Esperando hasta 25 segundos a que carguen los datos del listado…")
    try:
        handle = pagina.wait_for_function(script, timeout=25000)
        try:
            lista = handle.json_value()
        finally:
            handle.dispose()
        return "window.__PRELOADED_STATE__ = " + json.dumps({"listStore": lista})
    except timeout_error:
        html = pagina.content()
        try:
            return leer_listado(html, url)
        except (ValueError, KeyError, TypeError):
            pass
    titulo = " ".join(pagina.title().split())[:160]
    tarjetas = pagina.locator('[data-qa="posting PROPERTY"][data-to-posting]').count()
    logging.error("Diagnóstico | título=%r | ruta=%s | tarjetas detectadas=%d",
                  titulo, urlsplit(pagina.url).path, tarjetas)
    if tarjetas:
        motivo = "Se encontraron tarjetas, pero falta el formato de datos que reconoce el lector."
    elif any(t in clave(titulo) for t in ("just a moment", "un momento", "access denied", "acceso denegado", "security verification")):
        motivo = "El título indica una pantalla de verificación o acceso denegado."
    else:
        motivo = "No se reconocieron tarjetas ni datos de paginación."
    raise RuntimeError(f"{motivo} URL solicitada: {url}")


# =============================================
# 5. LECTURA DE TARJETAS Y LISTADOS
# =============================================
class TarjetasHTML(HTMLParser):
    """Lee sólo campos identificados de tarjetas de propiedad y enlaces de paginación."""

    VACIOS = set("area base br col embed hr img input link meta param source track wbr".split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pila = []
        self.tarjeta = None
        self.tarjetas = []
        self.siguiente = None
        self.actual = None
        self.sin_oferta = False
        self.canonica = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        qa = a.get("data-qa", "")
        clases = a.get("class", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonica = a.get("href", "")
        if tag == "a" and qa.startswith("PAGING_"):
            if qa == "PAGING_NEXT":
                self.siguiente = a.get("href")
            if "page-item-current" in clases and qa[7:].isdigit():
                self.actual = int(qa[7:])
        raiz = qa == "posting PROPERTY" and bool(a.get("data-to-posting"))
        if raiz:
            self.tarjeta = dict(id=a.get("data-id"), url=a["data-to-posting"], campos={})
            self.tarjetas.append(self.tarjeta)
        campo = qa or (self.pila[-1][1] if self.pila else "")
        if "location-address" in clases:
            campo = "direccion"
        if self.tarjeta is not None and tag == "img" and campo == "POSTING_CARD_GALLERY":
            self.tarjeta.setdefault("foto", a.get("src"))
            self.tarjeta.setdefault("alt", a.get("alt") or "")
        if tag not in self.VACIOS:
            self.pila.append((tag, campo, raiz))

    def handle_endtag(self, tag):
        if tag in self.VACIOS:
            return
        for i in range(len(self.pila)-1, -1, -1):
            if self.pila[i][0] == tag:
                if any(item[2] for item in self.pila[i:]):
                    self.tarjeta = None
                del self.pila[i:]
                return

    def handle_data(self, data):
        if not self.pila or self.pila[-1][0] in ("style", "script"):
            return
        valor = " ".join(data.split())
        if "en este momento no hay inmuebles como el que buscas" in valor.casefold():
            self.sin_oferta = True
        if self.tarjeta is not None and valor:
            self.tarjeta["campos"].setdefault(self.pila[-1][1], []).append(valor)


def importes_tarjeta(texto):
    precios = []
    for moneda, importe in re.findall(r"(S/\.?|USD|US\$)\s*([\d,]+(?:\.\d+)?)", texto, re.I):
        valor = float(importe.replace(",", ""))
        precios.append({"currency": "S/" if moneda.startswith("S/") else "USD",
                        "amount": int(valor) if valor.is_integer() else valor})
    return precios


def aviso_tarjeta(tarjeta, tipo, provincia):
    campos = tarjeta["campos"]
    url = urlsplit(tarjeta["url"]).path
    alt = tarjeta.get("alt", "")
    # Los listados pueden incluir sugerencias de otras categorías u operaciones.
    codigo = re.search(r"/clasificado/alcl(ha|ap|ca)", url)
    if not codigo:
        return None
    tipo_real = {"ha": "Habitación", "ap": "Departamento", "ca": "Casa"}[codigo[1]]
    if tipo_real != tipo:
        return None
    partes = [v.strip() for v in " ".join(campos.get("POSTING_CARD_LOCATION", [])).split(",") if v.strip()]
    indice = indice_distritos(["Lima", "Callao"])
    distrito = next((indice[clave(v)][1] for v in reversed(partes)
                     if clave(v) not in ("lima", "callao") and clave(v) in indice), None)
    if not distrito and partes and clave(partes[0]) in indice:
        distrito = indice[clave(partes[0])][1]
    if not distrito and len(partes) >= 2 and clave(partes[-1]) in indice:
        distrito = indice[clave(partes[-1])][1]
    zona = {"label": "ZONA", "name": distrito, "parent": {"label": "CIUDAD", "name": provincia}}
    gastos = importes_tarjeta(" ".join(campos.get("expensas", [])))
    rasgos = {}
    etiquetas = {"tot": ("CFT100", "Superficie total"), "cub": ("CFT101", "Superficie techada"),
                 "dorm": ("CFT2", "Dormitorios"), "baño": ("CFT3", "Baños"),
                 "estac": ("CFT7", "Estacionamientos"), "año": ("CFT5", "Antigüedad")}
    for texto in campos.get("POSTING_CARD_FEATURES", []):
        for prefijo, (codigo, etiqueta) in etiquetas.items():
            numero = re.match(r"(\d+(?:[.,]\d+)?)\s", texto)
            if prefijo in texto.casefold() and numero:
                rasgos[codigo] = {"label": etiqueta, "value": numero[1],
                                  "measure": "m²" if "m²" in texto else ""}
                break
    return {"postingId": tarjeta["id"], "url": url, "realEstateType": {"name": tipo},
            "title": alt.partition("·")[2].strip(), "generatedTitle": " · ".join([tipo, *campos.get("POSTING_CARD_FEATURES", [])]),
            "descriptionNormalized": " ".join(campos.get("POSTING_CARD_DESCRIPTION", [])),
            "priceOperationTypes": [{"operationType": {"name": "Alquiler"},
                                     "prices": importes_tarjeta(" ".join(campos.get("POSTING_CARD_PRICE", [])))}],
            "expenses": gastos[0] if gastos else {}, "mainFeatures": rasgos,
            "postingLocation": {"location": zona, "address": {"name": " ".join(campos.get("direccion", []))}},
            "visiblePictures": {"pictures": [{"url360x266": tarjeta.get("foto")}]}}


def listado_tarjetas(html, url):
    lector = TarjetasHTML()
    lector.feed(html)
    lector.close()
    ruta = urlsplit(url or lector.canonica).path
    m = re.fullmatch(r"/(habitacion|departamentos|casas)-en-alquiler-en-(lima|callao)-provincia(?:-pagina-(\d+))?\.html", ruta)
    if not m or not (lector.tarjetas or lector.sin_oferta):
        raise ValueError("No se reconocieron tarjetas ni un listado vacío del ámbito solicitado.")
    avisos = [aviso for t in lector.tarjetas
              if (aviso := aviso_tarjeta(t, CATEGORIAS[m[1]], m[2].title())) is not None]
    pagina = lector.actual or int(m[3] or 1)
    logging.info("Lectura por tarjetas: %d detectadas; %d del tipo solicitado.", len(lector.tarjetas), len(avisos))
    return avisos, {"total": len(lector.tarjetas), "currentPage": pagina,
                    "totalPages": pagina + int(bool(lector.siguiente)),
                    "pagesUrl": {"nextPage": lector.siguiente}, "tarjetas": True}


def leer_listado(html, url=None):
    try:
        return listado_estado(html)
    except (ValueError, KeyError, TypeError):
        return listado_tarjetas(html, url)


def listado_estado(html):
    marca = re.search(r"window\.__PRELOADED_STATE__\s*=\s*", html)
    if not marca:
        raise ValueError("El portal no entregó el listado estructurado. Revise si aparece un bloqueo.")
    estado, _ = json.JSONDecoder().raw_decode(html, marca.end())
    lista = estado["listStore"]
    if not isinstance(lista.get("listPostings"), list) or not isinstance(lista.get("paging"), dict):
        raise ValueError("Cambió la estructura de los resultados del portal.")
    return lista["listPostings"], lista["paging"]


def niveles_ubicacion(ubicacion):
    nodo = ubicacion.get("location")
    niveles = {}
    while nodo:
        niveles[nodo.get("label")] = nodo.get("name") or ""
        nodo = nodo.get("parent")
    return niveles


# =============================================
# 6. NORMALIZACIÓN DE ANUNCIOS
# =============================================
def es_proyecto(fila):
    ruta = urlsplit(fila.get("url") or "").path.casefold()
    estado = clave(fila.get("estado_proyecto") or fila.get("developmentStatus"))
    return "/proyecto/" in ruta or any(
        fase in estado for fase in ("en planos", "en construccion", "preventa"))

def normalizar(aviso, categoria, distritos, captura, descartes):
    if aviso.get("postingType") in ("DEVELOPMENT", "UNIT") or es_proyecto(aviso):
        descartes["proyecto o inmueble sin terminar"] += 1
        return None
    tipo = TIPOS.get(clave((aviso.get("realEstateType") or {}).get("name")))
    if tipo != categoria:
        descartes["otro tipo"] += 1
        return None
    alquiler = next((op for op in aviso.get("priceOperationTypes") or []
                     if clave((op.get("operationType") or {}).get("name")) == "alquiler"), None)
    if alquiler is None:
        descartes["sin operación alquiler"] += 1
        return None
    ubicacion = aviso.get("postingLocation") or {}
    niveles = niveles_ubicacion(ubicacion)
    lugar = distritos.get(clave(niveles.get("ZONA")))
    if not lugar or clave(niveles.get("CIUDAD")) not in ("lima", "callao"):
        descartes["ubicación fuera de ámbito o sin confirmar"] += 1
        return None
    if not aviso.get("postingId") or not aviso.get("url"):
        descartes["sin identificación"] += 1
        return None
    geo = (ubicacion.get("postingGeolocation") or {}).get("geolocation") or {}
    precios = {p.get("currency"): p.get("amount") for p in alquiler.get("prices") or []}
    gastos = aviso.get("expenses") or {}
    rasgos = aviso.get("mainFeatures") or {}
    return {
        "id_anuncio": str(aviso["postingId"]), "tipo_inmueble": tipo,
        "provincia": lugar[0], "distrito": lugar[1], "urbanizacion": niveles.get("SUBZONA"),
        "direccion": (ubicacion.get("address") or {}).get("name"),
        "latitud": geo.get("latitude"), "longitud": geo.get("longitude"),
        "precio_pen": precios.get("S/", precios.get("PEN")), "precio_usd": precios.get("USD"),
        "mantenimiento_importe": gastos.get("amount"), "mantenimiento_moneda": gastos.get("currency"),
        **{campo: (rasgos.get(codigo) or {}).get("value") for campo, codigo in CARACTERISTICAS.items()},
        "titulo": unescape(aviso.get("title") or ""),
        "descripcion": unescape(aviso.get("descriptionNormalized") or ""),
        "url": urljoin(BASE, aviso["url"]), "fecha_captura_utc": captura,
        "fecha_scrapeo": datetime.now().astimezone().date().isoformat(),
    }


# =============================================
# 7. PAGINACIÓN Y RECORRIDO
# =============================================
def recorrer(slug, provincia, max_paginas, pausa, obtener, avance=None):
    """Conserva el listado pendiente para que cambios de orden no pierdan sus IDs."""
    ruta = f"/{slug}-en-alquiler-en-{provincia.lower()}-provincia"
    estado = avance.fuente(ruta) if avance else None
    pagina, url, cache = estado or (1, BASE + ruta + ".html", None)
    while pagina:
        if max_paginas is not None and pagina > max_paginas:
            return  # Un límite de prueba no marca toda la fuente como terminada.
        if cache is None:
            time.sleep(pausa)
            logging.info("Leyendo %s", url)
            respuesta = obtener(url)
            avisos, paginacion = respuesta if isinstance(respuesta, tuple) else leer_listado(respuesta, url)
            if int(paginacion["currentPage"]) != pagina:
                raise ValueError(f"Paginación inconsistente en {url}")
            if not avisos and not (paginacion.get("total") == 0 or paginacion.get("tarjetas")):
                raise ValueError(f"Listado incompleto en {url}")
            siguiente = None
            if pagina < int(paginacion["totalPages"]):
                esperada = f"{ruta}-pagina-{pagina+1}.html"
                enlace = (paginacion.get("pagesUrl") or {}).get("nextPage")
                if not enlace or urlsplit(urljoin(BASE, enlace)).path != esperada:
                    raise ValueError(f"No se pudo validar la siguiente página de {url}")
                siguiente = BASE + esperada
            cache = {"avisos": avisos, "siguiente": siguiente}
            if avance:
                avance.guardar_fuente(ruta, pagina, url, cache)
        # El cursor sólo cambia tras consumir la página. Un error en una ficha
        # mantiene este listado; las filas confirmadas se omiten por ID al volver.
        yield from cache["avisos"]
        url = cache["siguiente"]
        pagina = pagina + 1 if url else 0
        cache = None
        if avance:
            avance.guardar_fuente(ruta, pagina, url, None)



def candidatos(provincias, max_paginas, pausa, alternar, obtener, avance=None):
    fuentes = deque((tipo, recorrer(slug, provincia, max_paginas, pausa, obtener, avance))
                    for provincia in provincias for slug, tipo in CATEGORIAS.items())
    while fuentes:
        tipo, fuente = fuentes.popleft()
        if alternar:
            aviso = next(fuente, None)
            if aviso is not None:
                yield tipo, aviso
                fuentes.append((tipo, fuente))
        else:
            for aviso in fuente:
                yield tipo, aviso


# =============================================
# 8. FICHA COMPLETA: FOTOS, DATOS, DESCRIPCIÓN, PESTAÑAS Y MAPA
# =============================================
APARTADOS = {
    "Características generales": "caracteristicas_generales",
    "Servicios": "servicios", "Ambientes": "ambientes", "Exteriores": "exteriores",
}
# Secuencia de lectura: enlace -> galería -> precio -> características principales
# -> descripción -> pestañas -> ubicación y coordenadas. Los campos de proyectos
# y el bloque repetido caracteristicas_dinamicas se retiran para no duplicar datos.
COLUMNAS_URBANIA = (
    "url", "imagenes", "tipo_inmueble", "titulo", "precio_general", "mantenimiento",
    "datos_principales_generales", "descripcion", *APARTADOS.values(), "otros_apartados",
    "ubicacion", "fecha_scrapeo", "estado_extraccion", "fuente_coordenadas",
    "precision_ubicacion", "coordenadas_geograficas",
)
# El formato analítico conserva las variables numéricas individuales y agrega
# también las pestañas separadas, la galería y el estado de extracción.
COLUMNAS = [c for c in COLUMNAS if c != "coordenadas_geograficas"] + [
    "imagenes", "datos_principales_generales", *APARTADOS.values(), "otros_apartados",
    "estado_extraccion", "fuente_coordenadas", "precision_ubicacion", "coordenadas_geograficas",
]
AUSENTE = "No especificado"


def texto_unido(valores, separador=" | "):
    return separador.join(dict.fromkeys(unescape(str(v)).strip() for v in valores if v)) or AUSENTE


def valor_publicado(html, campo):
    """Lee sólo literales públicos; jamás evalúa código JavaScript del portal."""
    patron = r"""['"]""" + re.escape(campo) + r"""['"]\s*:\s*"""
    for marca in re.finditer(patron, html):
        try:
            return json.JSONDecoder().raw_decode(html, marca.end())[0]
        except ValueError:
            # Algunas propiedades del portal usan comillas simples.
            literal = re.match(r"'((?:\\.|[^'\\])*)'", html[marca.end():])
            if literal:
                try:
                    return ast.literal_eval(literal[0])
                except (ValueError, SyntaxError):
                    pass
    return None

def coordenada_publicada(valor, maximo):
    """Decodifica el punto público del mapa y valida su rango geográfico."""
    if valor in (None, ""):
        return None
    try:
        numero = float(valor)
    except (ValueError, TypeError):
        try:
            numero = float(base64.b64decode(str(valor), validate=True).decode("utf-8"))
        except (ValueError, UnicodeError, binascii.Error):
            return None
    return numero if math.isfinite(numero) and abs(numero) <= maximo else None

class ComplementosHTML(HTMLParser):
    """Lee el mantenimiento visible sin deducir su moneda a partir del alquiler."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pila = []
        self.gastos = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        activo = (self.pila[-1][1] if self.pila else False) or "price-expenses" in a.get("class", "")
        if tag not in TarjetasHTML.VACIOS:
            self.pila.append((tag, activo))

    def handle_endtag(self, tag):
        if tag in TarjetasHTML.VACIOS:
            return
        for i in range(len(self.pila)-1, -1, -1):
            if self.pila[i][0] == tag:
                del self.pila[i:]
                return

    def handle_data(self, texto):
        if self.pila and self.pila[-1][1]:
            self.gastos.append(texto)

def ampliar_datos_ficha(html, detalle):
    visible = ComplementosHTML()
    visible.feed(html)
    detalle["mantenimiento_visible"] = " ".join("".join(visible.gastos).split())
    marca = re.search(r"\b(?:const|let|var)\s+avisoInfo\s*=\s*\{", html)
    bloque = html[marca.end():] if marca else html
    if marca:
        bloque = bloque.split("const dataLayerInfo", 1)[0]
    for campo in ("pictures", "pricesData", "mainFeatures", "location", "address",
                  "visibility", "expenses", "postingTitle", "realEstateType", "postingType",
                  "idAviso", "generatedTitle"):
        valor = valor_publicado(bloque, campo)
        if valor is not None:
            detalle[campo] = valor

    # Adondevivir publica mapLatOf/mapLngOf codificados en base64.
    for nombre, maximo in (("mapLat", 90), ("mapLng", 180)):
        valor = valor_publicado(html, nombre)
        if valor is None:
            marca = re.search(r"\b" + nombre + r"Of\s*=\s*(['\"])(.*?)\1", html)
            valor = marca[2] if marca else None
        detalle[nombre] = coordenada_publicada(valor, maximo)
    if (detalle.get("mapLat"), detalle.get("mapLng")) == (0, 0):
        detalle["mapLat"] = detalle["mapLng"] = None
    return detalle

def texto_rasgos(rasgos):
    """Mantiene nombre y valor de cada característica, una por línea."""
    return "\n".join(
        unescape(str(v["label"])) + (f": {v['value']}" if v.get("value") not in (None, "") else "")
        for v in (rasgos or {}).values() if isinstance(v, dict) and v.get("label")
    )

class DescripcionHTML(HTMLParser):
    """Extrae todo el contenido de Descripción, incluidos párrafos colapsados con CSS."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pila = []
        self.fragmentos = []
        self.encontrada = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        activo = self.pila[-1][1] if self.pila else False
        if a.get("id") == "reactDescription":
            activo = True
            self.encontrada = True
        if tag in ("script", "style", "button"):
            activo = False
        if activo and tag in ("br", "p", "li", "div", "section"):
            self.fragmentos.append("\n")
        if tag not in TarjetasHTML.VACIOS:
            self.pila.append((tag, activo))

    def handle_endtag(self, tag):
        if tag in TarjetasHTML.VACIOS:
            return
        for i in range(len(self.pila)-1, -1, -1):
            if self.pila[i][0] == tag:
                if self.pila[i][1] and tag in ("p", "li", "div", "section"):
                    self.fragmentos.append("\n")
                del self.pila[i:]
                return

    def handle_data(self, texto):
        if texto.strip().casefold() in ("leer descripción completa", "leer menos", "ver más", "ver menos"):
            return
        if self.pila and self.pila[-1][1]:
            self.fragmentos.append(texto)

    def texto(self):
        return "\n".join(" ".join(linea.split()) for linea in
                         "".join(self.fragmentos).splitlines() if linea.strip())

def descripcion_completa(html):
    lector = DescripcionHTML()
    lector.feed(html)
    return lector.texto()

def datos_ficha(html):
    """Extrae valores JSON del bloque público de la ficha sin ejecutar JavaScript."""
    datos = {}
    for campo in ("generalFeatures", "description"):
        marca = re.search(r"""['"]""" + campo + r"""['"]\s*:\s*""", html)
        if marca:
            try:
                datos[campo], _ = json.JSONDecoder().raw_decode(html, marca.end())
            except ValueError:
                continue
    texto = descripcion_completa(html)
    if not texto and datos.get("description"):
        texto = descripcion_completa('<div id="reactDescription">' + datos["description"] + '</div>')
    datos["description_text"] = texto
    return ampliar_datos_ficha(html, datos)

# 8.1. INTERACCIÓN: EXPANDIR DESCRIPCIÓN Y RECORRER CADA PESTAÑA
# Cada clic se valida para no guardar el contenido de la pestaña anterior.
def capturar_ficha_navegador(pagina):
    """Abre la descripción y pulsa cada pestaña disponible, según las imágenes del usuario."""
    pagina.locator("#reactDescription").wait_for(state="attached", timeout=25000)
    pagina.wait_for_function("""() => {
        const e = document.querySelector('#reactDescription');
        return e && e.textContent.trim().length > 0;
    }""", timeout=25000)

    ampliar = pagina.locator("#reactDescription").get_by_role(
        "button", name=re.compile(r"Leer descripción completa", re.I))
    if ampliar.count() and ampliar.first.is_visible():
        ampliar.first.click()

    detalle = datos_ficha(pagina.content())
    # Recuperar datos públicos de la ficha hidratada si no están ya en el HTML.
    # avisoInfo es el objeto que alimenta esta misma ficha; se selecciona una lista
    # explícita de campos inmobiliarios, sin copiar información de sesión.
    publicos = pagina.evaluate("""() => {
        if (typeof avisoInfo === 'undefined') return {};
        const campos = ['pictures','pricesData','mainFeatures','location','address',
                        'visibility','expenses','postingTitle','realEstateType',
                        'postingType','idAviso','mapLat','mapLng','generalFeatures'];
        return Object.fromEntries(campos.filter(k => avisoInfo[k] != null)
                                  .map(k => [k, avisoInfo[k]]));
    }""")
    for k, v in publicos.items():
        if detalle.get(k) in (None, "", [], {}):
            detalle[k] = v
    detalle["mapLat"] = coordenada_publicada(detalle.get("mapLat"), 90)
    detalle["mapLng"] = coordenada_publicada(detalle.get("mapLng"), 180)
    contenedor = pagina.locator("#reactGeneralFeatures")
    grupos = detalle.get("generalFeatures") or {}
    apartados = {}
    if grupos:
        contenedor.locator("button").first.wait_for(state="visible", timeout=20000)
    if contenedor.count():
        nombres = list(dict.fromkeys(
            t.strip() for t in contenedor.locator("button").all_text_contents() if t.strip()))
        for nombre in nombres:
            boton = contenedor.get_by_role("button").filter(
                has_text=re.compile(r"^\s*" + re.escape(nombre) + r"\s*$"))
            boton.first.click()
            # Verifica el cambio de pestaña antes de leer: evita asignar los
            # servicios a la columna Ambientes por una renderización retrasada.
            pagina.wait_for_function("""({nombre}) => {
                const root = document.querySelector('#reactGeneralFeatures');
                const activo = [...root.querySelectorAll('button')].find(
                    b => b.textContent.trim() === nombre &&
                         (b.className.includes('button-general-features-active') ||
                          b.getAttribute('aria-selected') === 'true'));
                return Boolean(activo && root.querySelector('[class*="description-text"]'));
            }""", arg={"nombre": nombre}, timeout=12000)
            valores = contenedor.locator('[class*="description-text"]').all_text_contents()
            texto = "\n".join(t.strip() for t in valores if t.strip())
            if not texto:
                raise FichaRevisar(f"No se pudo leer el apartado {nombre}; la extracción de esta ficha se detiene.")
            apartados[nombre] = texto

    # Si el portal anuncia un grupo pero su pestaña no cargó, no marcar la ficha completa.
    faltan = set(grupos) - set(apartados)
    if faltan:
        raise FichaRevisar(f"No cargaron los apartados {sorted(faltan)}; la extracción de esta ficha se detiene.")
    detalle["apartados_leidos"] = apartados
    detalle["apartados_verificados"] = True

    # Campos visibles complementan el HTML cuando React retiró los datos iniciales.
    detalle["ubicacion_visible"] = pagina.locator("#map-section h4").first.text_content() if pagina.locator("#map-section h4").count() else ""
    detalle["titulo_visible"] = pagina.locator("#article-container h1").first.text_content() if pagina.locator("#article-container h1").count() else ""
    gastos = pagina.locator(".price-expenses")
    detalle["mantenimiento_visible"] = gastos.first.text_content() if gastos.count() else ""

    return detalle

def imagenes_ficha(detalle):
    fotos = detalle.get("pictures") or []
    enlaces = []
    for foto in fotos:
        url = next((foto.get(k) for k in ("url1200x1200", "url730x532", "url360x266",
                                         "resizeUrl1200x1200") if foto.get(k)), None)
        if url and url not in enlaces:
            enlaces.append(url)
    return enlaces


def formato_urbania(aviso, fila, detalle):
    """Exporta la secuencia de las imágenes sin repetir los mismos apartados."""
    precios = [f"{moneda} {fila[campo]}" for moneda, campo in
               (("S/", "precio_pen"), ("USD", "precio_usd")) if fila.get(campo) not in (None, "")]
    mantenimiento = ""
    if fila.get("mantenimiento_importe") not in (None, ""):
        mantenimiento = f"{fila.get('mantenimiento_moneda') or ''} {fila['mantenimiento_importe']}".strip()
    return {
        **{c: fila.get(c, "") for c in COLUMNAS_URBANIA},
        "precio_general": " | ".join(precios), "mantenimiento": mantenimiento,
        "ubicacion": ", ".join(str(fila[k]) for k in ("direccion", "distrito", "provincia") if fila.get(k)),
    }


# 8.2. CONSOLIDACIÓN: UNA SOLA FILA CON LOS CAMPOS EN SU COLUMNA
class FichaRevisar(RuntimeError):
    """Datos incompletos o tipo fuera de alcance; no es un error de conexión."""


def enriquecer_anuncio(aviso, fila, detalle, completa):
    """Prioriza datos de la ficha sobre la tarjeta, que suele estar resumida.

    No deduce servicios a partir de la descripción: cada pestaña conserva su
    contenido. Si no existe una pestaña queda vacía; si falla su lectura, el
    navegador lanza un error en vez de marcar la extracción como completa.
    """
    if completa:
        # El título comercial del enlace por sí solo no prueba el tipo. Validar
        # la clasificación publicada en la ficha antes de exigir sus atributos.
        tipo_publicado = detalle.get("realEstateType") or {}
        nombre_tipo = clave(tipo_publicado.get("name"))
        tipo_ficha = TIPOS.get(nombre_tipo) or {"apartamento": "Departamento"}.get(nombre_tipo)
        codigo_tipo = str(tipo_publicado.get("realEstateTypeId") or "")
        if not tipo_ficha:
            tipo_ficha = {"1": "Casa", "2": "Departamento", "25": "Habitación"}.get(codigo_tipo)
        if (nombre_tipo or codigo_tipo) and not tipo_ficha:
            raise FichaRevisar("Tipo fuera de alcance en ficha: " + (nombre_tipo or codigo_tipo))
        if tipo_ficha:
            fila["tipo_inmueble"] = tipo_ficha
        if not detalle.get("description_text"):
            raise FichaRevisar("No se pudo leer la descripción completa de " + fila["url"])
        if detalle.get("idAviso") and str(detalle["idAviso"]) != fila["id_anuncio"]:
            raise RuntimeError("La ficha abierta no corresponde al anuncio solicitado.")
        if detalle.get("postingType") in ("DEVELOPMENT", "UNIT"):
            return None  # Es un proyecto incluso si la tarjeta no lo indicó.
        if "pictures" not in detalle or not detalle.get("mainFeatures"):
            raise FichaRevisar("No se pudo verificar la galería o los datos principales de " + fila["url"])
    fila["estado_extraccion"] = "ficha_completa" if completa else "solo_listado"
    fotos = imagenes_ficha(detalle if "pictures" in detalle else
                           {"pictures": (aviso.get("visiblePictures") or {}).get("pictures", [])})
    fila["imagenes"] = json.dumps(fotos, ensure_ascii=False)
    fila["titulo"] = detalle.get("postingTitle") or detalle.get("titulo_visible") or fila["titulo"]
    if detalle.get("description_text"):
        fila["descripcion"] = detalle["description_text"]
    rasgos = detalle.get("mainFeatures") or aviso.get("mainFeatures") or {}
    fila["datos_principales_generales"] = " | ".join(
        f"{r['label']}: {r.get('value', '')} {r.get('measure') or ''}".strip()
        for r in rasgos.values() if isinstance(r, dict) and r.get("label"))
    for campo, codigo in CARACTERISTICAS.items():
        if codigo in rasgos:
            fila[campo] = rasgos[codigo].get("value")
    apartados = detalle.get("apartados_leidos")
    if apartados is None:
        apartados = {nombre: texto_rasgos(valores) for nombre, valores in
                     (detalle.get("generalFeatures") or {}).items()}
    for nombre, campo in APARTADOS.items():
        fila[campo] = apartados.get(nombre, "")
    otros = {k: v for k, v in apartados.items() if k not in APARTADOS}
    fila["otros_apartados"] = json.dumps(otros, ensure_ascii=False) if otros else ""
    for op in detalle.get("pricesData") or []:
        if clave((op.get("operationType") or {}).get("name")) == "alquiler":
            for precio in op.get("prices") or []:
                campo = {"S/": "precio_pen", "PEN": "precio_pen", "USD": "precio_usd"}.get(precio.get("isoCode") or precio.get("currency"))
                if campo:
                    fila[campo] = precio.get("amount")
    gastos = importes_tarjeta(detalle.get("mantenimiento_visible") or "")
    if gastos:
        fila["mantenimiento_importe"], fila["mantenimiento_moneda"] = gastos[0]["amount"], gastos[0]["currency"]
    if isinstance(detalle.get("address"), dict):
        fila["direccion"] = detalle["address"].get("name") or fila["direccion"]
    punto = punto_valido(detalle.get("mapLat"), detalle.get("mapLng"))
    detalle_geo = {"latitud": punto[0], "longitud": punto[1]} if punto else {}
    completar_coordenadas(fila, detalle_geo)
    fila["fuente_coordenadas"] = "mapa_ficha" if punto else ("listado" if fila["coordenadas_geograficas"] else "no_disponibles")
    fila["precision_ubicacion"] = detalle.get("visibility") or "no_indicada"
    return fila


def candidatos_locales(archivos):
    """Alterna listados guardados desde el navegador, sin realizar peticiones."""
    fuentes = deque()
    for archivo in archivos:
        try:
            avisos, _ = leer_listado(archivo.read_text(encoding="utf-8-sig"))
        except (ValueError, KeyError) as exc:
            raise ValueError(f"{archivo}: guarde la página de resultados cargada como HTML.") from exc
        fuentes.append(iter(avisos))
    while fuentes:
        fuente = fuentes.popleft()
        aviso = next(fuente, None)
        if aviso is None:
            continue
        fuentes.append(fuente)
        tipo = TIPOS.get(clave((aviso.get("realEstateType") or {}).get("name")))
        if tipo:
            yield tipo, aviso


# =============================================
# 9. EXPORTACIÓN: UN ANUNCIO POR FILA
# =============================================
@contextmanager
def bloquear_salida(salida):
    """El bloqueo del sistema se libera incluso si el proceso se cierra a la fuerza."""
    ruta = salida.with_suffix(".lock")
    with ruta.open("a+b") as archivo:
        archivo.seek(0, os.SEEK_END)
        if archivo.tell() == 0:
            archivo.write(b"0")
            archivo.flush()
        archivo.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Ya hay otro proceso usando esta salida. Cierre ese proceso antes de reanudar.") from exc
        try:
            yield
        finally:
            archivo.seek(0)
            if os.name == "nt":
                msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)


class Avance:
    """SQLite confirma cada anuncio; el CSV se reconstruye sin duplicar IDs.

    El listado pendiente también se guarda antes de visitar sus fichas. No se
    almacena el navegador ni se cambia su configuración. Conservar ambos archivos.
    """
    def __init__(self, salida, columnas, config, parciales):
        self.salida, self.columnas = salida, list(columnas)
        self.db = sqlite3.connect(salida.with_suffix(".avance.sqlite"))
        try:
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS filas(id TEXT PRIMARY KEY, datos TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS fuentes(clave TEXT PRIMARY KEY, pagina INTEGER, url TEXT, cache TEXT);
                CREATE TABLE IF NOT EXISTS ajustes(clave TEXT PRIMARY KEY, valor TEXT);
                CREATE TABLE IF NOT EXISTS revision(id TEXT PRIMARY KEY, url TEXT, motivo TEXT, aviso TEXT, fecha TEXT);
            """)
            anterior = self.db.execute("SELECT valor FROM ajustes WHERE clave='config'").fetchone()
            config_json = json.dumps(config, sort_keys=True)
            if anterior and anterior[0] != config_json:
                raise ValueError("Este avance corresponde a otro ámbito o formato. Use otra --salida.")
            with self.db:
                if not anterior:
                    # Importar CSV previos y parciales de la misma salida al crear
                    # el avance. Los antiguos no tienen cursor: se revisan listados
                    # desde el inicio pero no se reabren los anuncios ya importados.
                    rutas = ([salida] if salida.exists() else []) + sorted(salida.parent.glob(salida.stem + "_parcial_*.csv"))
                    for ruta in rutas:
                        self.importar(ruta)
                    self.db.execute("INSERT OR REPLACE INTO ajustes VALUES ('config', ?)", (config_json,))
                for ruta in parciales or []:
                    self.importar(ruta.resolve())
            self.vistos = {r[0] for r in self.db.execute("SELECT id FROM filas")}
            self.revision = {r[0] for r in self.db.execute("SELECT id FROM revision")}
        except BaseException:
            self.db.close()
            raise

    def importar(self, ruta):
        agregados = 0
        with ruta.open(encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo, strict=True)
            if lector.fieldnames != self.columnas:
                raise ValueError(f"Columnas incompatibles en {ruta}; no se modificó el CSV original.")
            for fila in lector:
                if None in fila or any(v is None for v in fila.values()):
                    raise ValueError(f"Registro incompleto en {ruta}, línea {lector.line_num}.")
                identificador = fila.get("id_anuncio")
                if not identificador:
                    m = re.search(r"(\d+)\.html$", urlsplit(fila.get("url", "")).path)
                    identificador = m[1] if m else None
                if not identificador:
                    raise ValueError(f"No se puede identificar un anuncio en {ruta}.")
                cursor = self.db.execute("INSERT OR IGNORE INTO filas VALUES (?,?)", (identificador, json.dumps(fila, ensure_ascii=False)))
                agregados += cursor.rowcount
        logging.info("Importados %d anuncios nuevos desde %s", agregados, ruta)

    def fuente(self, clave):
        row = self.db.execute("SELECT pagina,url,cache FROM fuentes WHERE clave=?", (clave,)).fetchone()
        return (row[0], row[1], json.loads(row[2]) if row[2] else None) if row else None

    def guardar_fuente(self, clave, pagina, url, cache):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO fuentes VALUES (?,?,?,?)",
                            (clave, pagina, url, json.dumps(cache, ensure_ascii=False) if cache is not None else None))

    def registrar_revision(self, aviso, url, motivo):
        """Conserva ID, URL, motivo y tarjeta; no la cuenta como anuncio completo."""
        identificador = str(aviso["postingId"])
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO revision VALUES (?,?,?,?,?)",
                            (identificador, url, motivo, json.dumps(aviso, ensure_ascii=False),
                             datetime.now(timezone.utc).isoformat()))
        self.revision.add(identificador)
        logging.warning("Ficha registrada para revisión; se continúa: %s | %s", url, motivo)

    def guardar(self, identificador, fila):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO filas VALUES (?,?)", (identificador, json.dumps(fila, ensure_ascii=False)))
        self.vistos.add(identificador)
        self.exportar_csv()

    def exportar_csv(self):
        temporal = NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", dir=self.salida.parent, suffix=".tmp", delete=False)
        try:
            with temporal as archivo:
                escritor = csv.DictWriter(archivo, fieldnames=self.columnas)
                escritor.writeheader()
                for (datos,) in self.db.execute("SELECT datos FROM filas ORDER BY rowid"):
                    escritor.writerow(una_linea(json.loads(datos)))
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal.name, self.salida)
        finally:
            Path(temporal.name).unlink(missing_ok=True)

    def close(self):
        self.db.close()


def exportar(salida, provincias, max_paginas, pausa, limite=None, formato="urbania", archivos=None, obtener=descargar, solo_listados=False, importar_parcial=None):
    salida = salida.resolve()
    salida.parent.mkdir(parents=True, exist_ok=True)
    columnas = COLUMNAS_URBANIA if formato == "urbania" else COLUMNAS
    config = {"version": 1, "provincias": provincias, "formato": formato,
              "solo_listados": solo_listados, "archivos": [str(p.resolve()) for p in archivos or []]}
    with bloquear_salida(salida):
        avance = Avance(salida, columnas, config, importar_parcial)
        try:
            avance.exportar_csv()
            logging.info("Reanudando: %d anuncios guardados; %d fichas para revisión. CSV: %s", len(avance.vistos), len(avance.revision), salida)
            if limite is not None and len(avance.vistos) >= limite:
                return
            distritos, descartes = indice_distritos(provincias), Counter()
            fuente = (candidatos_locales(archivos) if archivos else
                      candidatos(provincias, max_paginas, pausa, limite is not None, obtener, avance))
            for tipo, aviso in fuente:
                if str(aviso.get("postingId")) in avance.vistos or str(aviso.get("postingId")) in avance.revision:
                    continue
                captura = datetime.now(timezone.utc).isoformat(timespec="seconds")
                fila = normalizar(aviso, tipo, distritos, captura, descartes)
                if fila is None:
                    continue
                url_ficha = fila["url"]
                try:
                    detalle = {}
                    completa = not archivos and not solo_listados
                    if completa:
                        time.sleep(pausa)
                        logging.info("Leyendo ficha: %s", fila["url"])
                        resultado = obtener(fila["url"])
                        detalle = resultado if isinstance(resultado, dict) else datos_ficha(resultado)
                    fila = enriquecer_anuncio(aviso, fila, detalle, completa)
                except FichaRevisar as exc:
                    avance.registrar_revision(aviso, url_ficha, str(exc))
                    continue
                if fila is None:
                    descartes["proyecto en ficha"] += 1
                    continue
                salida_fila = formato_urbania(aviso, fila, detalle) if formato == "urbania" else fila
                avance.guardar(fila["id_anuncio"], salida_fila)
                logging.info("Guardados %d anuncios únicos.", len(avance.vistos))
                if limite is not None and len(avance.vistos) >= limite:
                    break
        finally:
            try:
                avance.exportar_csv()
            finally:
                avance.close()



# =============================================
# 10. EJECUCIÓN DESDE LA TERMINAL
# =============================================
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--salida", type=Path, help="Ruta del CSV de salida.")
    parser.add_argument("--solo-lima", action="store_true", help="Excluir los distritos del Callao.")
    parser.add_argument("--max-paginas", type=int, help="Límite por categoría y provincia.")
    parser.add_argument("--pausa", type=float, default=5.0, help="Segundos entre solicitudes (5 por defecto, mínimo 1).")
    parser.add_argument("--limite", type=int, help="Máximo de anuncios únicos en total.")
    parser.add_argument("--formato", choices=["urbania", "analitico"], default="urbania",
                        help="Urbania: descripción completa y pestañas en columnas separadas. Analítico: variables en columnas separadas.")
    parser.add_argument("--html", nargs="+", type=Path, metavar="ARCHIVO",
                        help="Leer uno o varios listados HTML guardados desde el navegador, sin conexión.")
    parser.add_argument("--navegador", action="store_true", help="Abrir Chromium visible para leer el portal.")
    parser.add_argument("--solo-listados", action="store_true",
                        help="Extraer las tarjetas sin abrir cada ficha; puede haber menos características.")
    parser.add_argument("--importar-parcial", nargs="+", type=Path, metavar="CSV",
                        help="Importar anuncios de CSV parciales compatibles sin duplicarlos.")
    args = parser.parse_args()
    if args.navegador and args.html:
        parser.error("Elija --navegador o --html")
    if args.html and args.max_paginas:
        parser.error("--max-paginas solo se aplica a la descarga en línea")
    if args.limite is not None and args.limite < 1:
        parser.error("--limite debe ser positivo")
    if args.salida is None:
        directorio_destino = Path("data/raw/portals")
        directorio_destino.mkdir(parents=True, exist_ok=True)  # Crea la carpeta automáticamente si no existe
        args.salida = directorio_destino / "bronce_alquileres_adondevivir.csv"
    if args.max_paginas is not None and args.max_paginas < 1:
        parser.error("--max-paginas debe ser positivo")
    if not 1 <= args.pausa <= 3600 or args.salida.suffix.lower() != ".csv":
        parser.error("Use una salida .csv y una pausa entre 1 y 3600 segundos")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        with transporte(args.navegador) as obtener:
            exportar(args.salida, ["Lima"] if args.solo_lima else list(DISTRITOS),
                 args.max_paginas, args.pausa, args.limite, args.formato, args.html, obtener, args.solo_listados, args.importar_parcial)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, sqlite3.Error, csv.Error) as exc:
        logging.error("Extracción interrumpida: %s. El avance confirmado se conserva; repita el mismo comando.", exc)
        return 1
    except KeyboardInterrupt:
        logging.warning("Interrumpido. El avance se conserva; repita el mismo comando.")
        return 130
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
