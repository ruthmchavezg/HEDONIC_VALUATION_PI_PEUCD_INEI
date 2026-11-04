# [COMENTARIO] IMPORTACIÓN DE LIBRERÍAS ESTÁNDAR
# Lo que hace: Importa herramientas nativas de Python para peticiones HTTP (urllib), ejecución paralela (concurrent.futures), aleatoriedad (random) y registro de eventos (logging).
# Para qué sirve: Provee toda la infraestructura necesaria para descargar, probar y rotar proxies en segundo plano sin instalar pesadas librerías externas.
# Metodología: Uso de Biblioteca Estándar (Zero-dependency) y concurrencia asíncrona para optimizar tiempos de ejecución.
import urllib.request
import concurrent.futures
import random
import logging

# [COMENTARIO] FUENTES DE PROXIES LIBRES
# Lo que hace: Almacena una lista de URLs públicas (repositorios de GitHub y APIs gratuitas) que publican listas de proxies HTTP en tiempo real.
# Para qué sirve: Sirve como directorio semilla para obtener miles de direcciones IP actualizadas al minuto cada vez que se ejecuta el scraper.
# Metodología: Abastecimiento dinámico de datos abiertos (Open Data Sourcing) para evitar dependencias de listas estáticas (hardcoded) que se vuelven obsoletas rápidamente.
FUENTES_PROXIES_LIBRES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=all&anonymity=elite",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"
]

# [COMENTARIO] CLASE PRINCIPAL: FreeProxyRotator
# Lo que hace: Define la estructura del objeto que administrará todo el ciclo de vida de las direcciones IP alternativas.
# Para qué sirve: Encapsula las funciones de descarga, prueba y descarte de proxies para que el orquestador principal solo tenga que pedir un proxy listo para usar.
# Metodología: Programación Orientada a Objetos (OOP) para gestión de estado, asegurando un diseño modular y desacoplado[cite: 14].
class FreeProxyRotator:
    
    # [COMENTARIO] MÉTODO INICIALIZADOR
    # Lo que hace: Configura los parámetros iniciales: un límite de 60 proxies a validar, un tiempo máximo de espera de 3.0 segundos y una lista vacía para los proxies que aprueben.
    # Para qué sirve: Establece límites estrictos de control de calidad; solo los proxies que respondan en menos de 3 segundos serán aceptados, asegurando que el scraper sea veloz.
    # Metodología: Configuración de umbrales de tolerancia (Thresholding) y gestión de estado inicial.
    def __init__(self, max_proxies_a_validar: int = 60, timeout_validacion: float = 3.0):
        self.max_proxies_a_validar = max_proxies_a_validar
        self.timeout_validacion = timeout_validacion
        self.proxies_validos = []

    # [COMENTARIO] MÉTODO: _descargar_candidatos
    # Lo que hace: Itera sobre las URLs de las fuentes, descarga el texto plano de las IPs, limpia los espacios, filtra comentarios y mezcla los resultados aleatoriamente.
    # Para qué sirve: Reúne y estandariza una lista "cruda" masiva de IPs extraídas de internet y selecciona solo una muestra aleatoria (60) para no saturar la red probando miles.
    # Metodología: Peticiones HTTP secuenciales, filtrado de texto (Sanitization) y Muestreo Aleatorio (Random Sampling).
    def _descargar_candidatos(self) -> list:
        candidatos = set()
        for url in FUENTES_PROXIES_LIBRES:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    lineas = resp.read().decode("utf-8", errors="ignore").splitlines()
                    for linea in lineas:
                        linea = linea.strip()
                        if ":" in linea and not linea.startswith("#"):
                            candidatos.add(f"http://{linea}")
            except Exception:
                continue
        lista = list(candidatos)
        random.shuffle(lista)
        return lista[:self.max_proxies_a_validar]

    # [COMENTARIO] MÉTODO: _probar_proxy
    # Lo que hace: Configura un canal (ProxyHandler) para enrutar una petición hacia "https://httpbin.org/ip" a través del proxy candidato y verifica si responde HTTP 200 en menos de 3 segundos.
    # Para qué sirve: Confirma matemáticamente que el proxy es funcional, rápido y soporta conexiones HTTPS antes de intentar usarlo en portales reales (como Urbania/Babilonia).
    # Metodología: Verificación de salud (Health-Checking Activo) y Control de Timeouts para garantizar resiliencia[cite: 14].
    def _probar_proxy(self, proxy_url: str) -> str | None:
        """Verifica en menos de 3 segundos si el proxy libre responde y tiene salida HTTPS."""
        try:
            proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
            req = urllib.request.Request("https://httpbin.org/ip", headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=self.timeout_validacion) as resp:
                if resp.status == 200:
                    return proxy_url
        except Exception:
            return None
        return None

    # [COMENTARIO] MÉTODO: inicializar_pool
    # Lo que hace: Usa un ThreadPoolExecutor para lanzar 20 hilos de ejecución paralela que prueban simultáneamente los 60 proxies candidatos extraídos.
    # Para qué sirve: Acelera masivamente la validación; en lugar de probar 60 proxies uno por uno (lo que tomaría minutos), los prueba todos a la vez en un par de segundos.
    # Metodología: Procesamiento Concurrente (Multithreading / Paralelismo), reduciendo drásticamente el tiempo muerto en el pipeline de ingesta de datos.
    def inicializar_pool(self):
        """Descarga y filtra en paralelo solo los proxies rápidos que funcionan hoy."""
        logging.info("[*] Buscando y validando proxies libres activos en tiempo real...")
        candidatos = self._descargar_candidatos()
        if not candidatos:
            logging.warning("[!] No se pudieron descargar listas de proxies. Se usará conexión directa Stealth.")
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            resultados = list(executor.map(self._probar_proxy, candidatos))

        self.proxies_validos = [p for p in resultados if p is not None]
        logging.info(f"[+] Pool de proxies libres listo: {len(self.proxies_validos)} proxies rápidos verificados.")

    # [COMENTARIO] MÉTODO: obtener_proxy
    # Lo que hace: Verifica si hay proxies válidos disponibles; si no hay (o se agotaron), ejecuta el método de inicialización para descargar un nuevo lote. Finalmente, devuelve uno al azar.
    # Para qué sirve: Proporciona la IP falsa al navegador. Además, implementa la auto-recarga (Auto-Refill) para que el scraper pueda seguir corriendo por horas sin intervención humana.
    # Metodología: Aprovisionamiento "Just-in-Time" (JIT) y Auto-Recarga Autónoma, clave para evadir bloqueos de IP masivos en entornos gubernamentales/institucionales[cite: 14].
    def obtener_proxy(self) -> str | None:
        """
        Devuelve un proxy validado al azar. 
        Si el pool se quedó sin proxies vivos a mitad del scrapeo, 
        descarga y valida un lote nuevo automáticamente (Auto-Refill).
        """
        if not self.proxies_validos:
            logging.info("[*] El pool de proxies se agotó. Descargando un nuevo lote fresco en vivo...")
            self.inicializar_pool()
            
        if not self.proxies_validos:
            return None
            
        return random.choice(self.proxies_validos)

    # [COMENTARIO] MÉTODO: descartar_proxy
    # Lo que hace: Recibe la URL de un proxy que falló durante el scraping y lo borra de la memoria activa (self.proxies_validos).
    # Para qué sirve: Evita que el navegador intente reutilizar un proxy que acaba de ser baneado por Cloudflare o que se cayó, manteniendo el pool limpio.
    # Metodología: Lista negra dinámica (Dynamic Blacklisting) y degradación elegante, asegurando que la calidad del red permanezca alta durante la sesión.
    def descartar_proxy(self, proxy_url: str):
        """Elimina del pool un proxy que haya fallado o sea lento."""
        if proxy_url in self.proxies_validos:
            self.proxies_validos.remove(proxy_url)
            logging.info(f"[-] Proxy lento descartado ({proxy_url}). Quedan {len(self.proxies_validos)} en el pool.")