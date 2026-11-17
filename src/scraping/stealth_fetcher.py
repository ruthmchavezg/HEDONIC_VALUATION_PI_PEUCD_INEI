# [COMENTARIO] IMPORTACIÓN DE LIBRERÍAS Y DEPENDENCIAS
# Lo que hace: Importa módulos nativos (random, time, logging), herramientas de automatización web (Playwright), gestores de reintentos (Tenacity) y configuraciones/módulos propios del proyecto.
# Para qué sirve: Integra todas las herramientas necesarias para levantar un navegador invisible, simular tiempos humanos, reintentar ante errores y coordinar el uso de proxies.
# Metodología: Modularidad y Desacoplamiento de dependencias, separando las utilidades base (reintentos, log, azar) de las reglas de negocio (configuraciones y rotador de proxies).
import random
import time
import logging
from playwright.sync_api import sync_playwright, Page, BrowserContext
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import USER_AGENTS, RAW_DIR, PROXY_SERVER, USE_FREE_PROXIES
from src.scraping.proxy_manager import FreeProxyRotator

# [COMENTARIO] CONSTANTE DE ALMACENAMIENTO DE SESIÓN
# Lo que hace: Define la ruta exacta dentro de la capa Bronze (RAW_DIR) donde se guardarán y leerán las cookies del navegador.
# Para qué sirve: Permite almacenar el estado de la sesión de forma persistente, evitando tener que iniciar sesión repetidas veces o reiniciar el historial de confianza ante el servidor.
# Metodología: Persistencia de Estado (State Persistence) y Gestión de Sesiones Locales.
COOKIES_FILE = RAW_DIR / "sessions" / "session_cookies.json"

# [COMENTARIO] SCRIPT DE EVASIÓN (STEALTH)
# Lo que hace: Define un código JavaScript que se inyecta en el navegador para eliminar la propiedad 'webdriver', añadir lenguajes y plugins falsos, y parchear los permisos de notificaciones.
# Para qué sirve: Oculta el rastro algorítmico del bot, engañando a los sistemas de seguridad (como Cloudflare) haciéndoles creer que es un humano navegando desde un Chrome real.
# Metodología: Suplantación de Huella Digital (Browser Fingerprint Spoofing) e Inyección de Código del Lado del Cliente (Client-Side Script Injection).
STEALTH_JS = """
(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => ['es-PE', 'es', 'en-US', 'en'] });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    window.chrome = { runtime: {} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: 'denied' }) :
            originalQuery(parameters)
    );
})();
"""

# [COMENTARIO] DEFINICIÓN DEL MOTOR DE NAVEGACIÓN
# Lo que hace: Crea la clase constructora que inicializa variables internas de Playwright, control de páginas, un contador de peticiones y evalúa si se debe instanciar el rotador de proxies.
# Para qué sirve: Encapsula todo el control del ciclo de vida del navegador en un objeto único y ordenado que se puede llamar desde cualquier otra parte del programa.
# Metodología: Programación Orientada a Objetos (POO) aplicando el Patrón Fachada (Facade Pattern) para simplificar la interacción compleja con el motor del navegador.
class StealthBrowserEngine:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.requests_count = 0
        self.proxy_actual = None
        self.proxy_rotator = FreeProxyRotator() if USE_FREE_PROXIES else None

    # [COMENTARIO] MÉTODO: start
    # Lo que hace: Ejecuta el validador de proxies (si está activo), inicia la instancia de Playwright, lanza el ejecutable de Chromium con parámetros "antibot" (sin sandbox, sin infobars) y llama a rotar el primer contexto.
    # Para qué sirve: Enciende la infraestructura subyacente del navegador en modo seguro y prepara el entorno antes de hacer la primera petición HTTP.
    # Metodología: Inicialización Defensiva (Safe Initialization) y Sandboxing, previniendo fugas de automatización desde los argumentos de inicio del navegador.
    def start(self):
        if self.proxy_rotator:
            self.proxy_rotator.inicializar_pool()

        self.playwright = sync_playwright().start()
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
        ]
        # Lanzamos Chromium permitiendo configurar proxies dinámicamente por contexto
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=launch_args
        )
        self.rotar_contexto()

    # [COMENTARIO] MÉTODO: rotar_contexto
    # Lo que hace: Cierra la página y el contexto actuales (guardando cookies previamente), escoge un nuevo User-Agent al azar, asigna un proxy fresco del pool e inyecta el script Stealth, además de bloquear imágenes/videos.
    # Para qué sirve: Cambia la identidad completa del scraper sin cerrar el programa, evitando que el servidor destino sume muchas peticiones a una misma IP o sesión y bloquee el acceso.
    # Metodología: Rotación Preventiva de Identidad (Identity Rotation), Gestión Dinámica de Sesiones y Optimización de Ancho de Banda (Resource Blocking).
    def rotar_contexto(self, forzar_sin_proxy: bool = False):
        """Crea o renueva el contexto rotando tanto el User-Agent como el Proxy activo."""
        if self.page:
            try:
                self.context.storage_state(path=str(COOKIES_FILE))
                self.page.close()
                self.context.close()
            except Exception:
                pass

        ua = random.choice(USER_AGENTS)
        storage = str(COOKIES_FILE) if COOKIES_FILE.exists() else None

        # Determinar qué proxy usar en este contexto
        proxy_cfg = None
        if not forzar_sin_proxy:
            if PROXY_SERVER:
                self.proxy_actual = PROXY_SERVER
                proxy_cfg = {"server": PROXY_SERVER}
            elif self.proxy_rotator:
                self.proxy_actual = self.proxy_rotator.obtener_proxy()
                if self.proxy_actual:
                    proxy_cfg = {"server": self.proxy_actual}
        else:
            self.proxy_actual = None

        self.context = self.browser.new_context(
            user_agent=ua,
            viewport={"width": random.randint(1360, 1920), "height": random.randint(768, 1080)},
            locale="es-PE",
            timezone_id="America/Lima",
            storage_state=storage,
            proxy=proxy_cfg
        )

        self.context.add_init_script(STEALTH_JS)
        self.context.route(
            "**/*.{png,jpg,jpeg,webp,gif,woff,woff2,ttf,mp4,avi}",
            lambda route: route.abort()
        )

        self.page = self.context.new_page()
        modo_red = f"Proxy Libre ({self.proxy_actual})" if self.proxy_actual else "Conexión Directa Stealth"
        logging.info(f"[*] Contexto activo [{modo_red}] | UA: {ua[:50]}...")

    # [COMENTARIO] MÉTODO: simular_humano
    # Lo que hace: Genera desplazamientos curvos del ratón hacia coordenadas aleatorias y acciona la rueda de scroll mediante bucles con pausas microscópicas (time.sleep).
    # Para qué sirve: Engaña a los algoritmos de detección biométrica de los portales web (como Cloudflare) demostrando que hay una supuesta interacción física en la pantalla y no solo peticiones automáticas.
    # Metodología: Emulación de Comportamiento Humano (Human-like Interaction Emulation) e Inyección de Varianza Estocástica.
    def simular_humano(self):
        try:
            for _ in range(random.randint(2, 4)):
                x = random.randint(100, 900)
                y = random.randint(100, 600)
                self.page.mouse.move(x, y, steps=random.randint(8, 15))
                time.sleep(random.uniform(0.15, 0.35))
            self.page.mouse.wheel(0, random.randint(250, 600))
        except Exception:
            pass

    # [COMENTARIO] MÉTODO: verificar_y_evadir_captcha
    # Lo que hace: Lee el título y el cuerpo de la página en busca de textos clave de bloqueos ("just a moment", "cf-turnstile"). Si los halla, simula movimientos del mouse y da un clic exacto en la casilla del CAPTCHA.
    # Para qué sirve: Actúa como un mecanismo de auto-resolución ante "muros de seguridad", permitiendo que el scraping continúe su ejecución desatendida sin intervención humana.
    # Metodología: Detección Activa de Amenazas (Threat Detection) y Resolución Automática de Retos de Seguridad (Challenge-Response Evasion).
    def verificar_y_evadir_captcha(self):
        try:
            titulo = self.page.title().lower()
            contenido = self.page.content().lower()
            indicadores_bloqueo = ["just a moment", "un momento", "attention required", "verifica que eres un ser humano", "cf-turnstile"]

            if any(ind in titulo or ind in contenido for ind in indicadores_bloqueo):
                logging.warning("[!] Reto antibot/CAPTCHA detectado. Activando protocolo de evasión...")
                self.simular_humano()
                self.page.wait_for_timeout(4000)

                for frame in self.page.frames:
                    if "cloudflare" in frame.url or "turnstile" in frame.url:
                        box = frame.locator("body").bounding_box()
                        if box:
                            cx = box["x"] + box["width"] / 4
                            cy = box["y"] + box["height"] / 2
                            self.page.mouse.move(cx, cy, steps=15)
                            self.page.mouse.click(cx, cy)
                            self.page.wait_for_timeout(6000)
                            break

                self.context.storage_state(path=str(COOKIES_FILE))
        except Exception as e:
            logging.debug(f"Verificación CAPTCHA finalizada: {e}")

    # [COMENTARIO] MÉTODO: navegar_seguro (CON DECORADOR RETRY)
    # Lo que hace: Incorpora un decorador que reintenta la navegación automáticamente si falla, con tiempos de espera crecientes (wait_exponential). Envía al navegador a la URL, maneja las caídas del proxy (descartándolo y rotando en caliente) y evalúa los códigos de estado HTTP 403/429.
    # Para qué sirve: Proporciona la capa más fuerte de resiliencia del sistema: si la conexión se cae, el servidor rechaza la visita o el proxy es lento, el script se reconfigura solo y vuelve a intentarlo sin abortar el programa completo.
    # Metodología: Control de Tolerancia a Fallos (Fault Tolerance), Backoff Exponencial para descongestión de red (Rate Limiting) y Mecanismo de Respaldo Automático (Auto-Fallback).
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=12), reraise=True)
    def navegar_seguro(self, url: str, pausa_min: float = 2.8, pausa_max: float = 5.5):
        """Navega con soporte de proxy y fallback automático si un proxy libre se cae."""
        self.requests_count += 1
        time.sleep(random.uniform(pausa_min, pausa_max))

        try:
            response = self.page.goto(url, wait_until="domcontentloaded", timeout=35000)
        except Exception as e:
            # Si falló por culpa de un proxy libre caído o lento, lo descartamos y cambiamos al instante
            if self.proxy_actual and self.proxy_rotator:
                logging.warning(f"[!] El proxy libre {self.proxy_actual} falló. Cambiando automáticamente...")
                self.proxy_rotator.descartar_proxy(self.proxy_actual)
                usar_directo = len(self.proxy_rotator.proxies_validos) == 0
                self.rotar_contexto(forzar_sin_proxy=usar_directo)
            raise e

        if response and response.status in [403, 429, 503]:
            logging.warning(f"[!] Estado HTTP {response.status} en {url}.")
            if self.proxy_actual and self.proxy_rotator:
                self.proxy_rotator.descartar_proxy(self.proxy_actual)
                self.rotar_contexto()
            else:
                self.verificar_y_evadir_captcha()

        self.page.wait_for_timeout(random.randint(2000, 3500))
        self.verificar_y_evadir_captcha()
        self.simular_humano()

    # [COMENTARIO] MÉTODO: close
    # Lo que hace: Realiza un último guardado del estado de almacenamiento (cookies locales) y procede a cerrar controladamente la página, el contexto y finalmente el navegador entero.
    # Para qué sirve: Evita fugas de memoria RAM (Memory Leaks) ocasionadas por procesos huérfanos de Chromium y asegura que la sesión quede persistida en disco para la próxima ejecución de scraper.
    # Metodología: Gestión de Ciclo de Vida de Recursos (Resource Lifecycle Management) y Limpieza Segura (Graceful Teardown).
    def close(self):
        try:
            if self.context:
                self.context.storage_state(path=str(COOKIES_FILE))
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass