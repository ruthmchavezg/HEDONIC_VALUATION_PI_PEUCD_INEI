import logging
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import RAW_DIR

CHROME_CDP_DIR = RAW_DIR / "sessions" / "chrome_cdp_profile"

class StealthBrowserEngine:
    """
    Motor híbrido de scraping:
    - Utiliza curl_cffi (suplantación de huella TLS/JA4 de Chrome) para portales endurecidos con Cloudflare (Urbania, Adondevivir, RE/MAX).
    - Utiliza Playwright para portales basados en interacción profunda (Babilonia, Properati, LaEncontre, Century21).
    """
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.requests_count = 0
        self._html_actual = ""
        self._soup_actual = None
        self._usando_cffi = False

    def start(self):
        # Inicializamos Playwright de respaldo por si se requiere navegación interactiva
        self.playwright = sync_playwright().start()
        CHROME_CDP_DIR.mkdir(parents=True, exist_ok=True)
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_CDP_DIR),
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={"width": 1366, "height": 768},
            locale="es-PE",
            timezone_id="America/Lima",
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def navegar_seguro(self, url: str, pausa_min: float = 0.5, pausa_max: float = 1.0):
        self.requests_count += 1
        dominio_bajo = url.lower()

        # Detección de portales protegidos por Cloudflare estricto (Navent / RE/MAX)
        if any(p in dominio_bajo for p in ["urbania.pe", "adondevivir.com", "remax.pe"]):
            self._usando_cffi = True
            try:
                logging.info(f"[*] Usando Bypass TLS (curl_cffi) para portal protegido: {url}")
                # cffi_requests emula la huella TLS exacta de Chrome 120+ saltándose a Cloudflare sin bloqueos
                resp = cffi_requests.get(
                    url,
                    impersonate="chrome120",
                    timeout=15,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.8,en;q=0.7",
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                    }
                )
                if resp.status_code == 200:
                    self._html_actual = resp.text
                    self._soup_actual = BeautifulSoup(self._html_actual, "html.parser")
                    return
                else:
                    logging.warning(f"[!] curl_cffi obtuvo estado HTTP {resp.status_code}. Reintentando con Playwright...")
            except Exception as e:
                logging.warning(f"[!] Error en curl_cffi ({e}). Respalando a Playwright...")

        # Para los demás portales o en caso de fallo, usamos Playwright estándar de forma limpia
        self._usando_cffi = False
        self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
        self._html_actual = self.page.content()
        self._soup_actual = BeautifulSoup(self._html_actual, "html.parser")

    def content(self) -> str:
        return self._html_actual

    def soup(self) -> BeautifulSoup:
        if not self._soup_actual:
            self._soup_actual = BeautifulSoup(self._html_actual, "html.parser")
        return self._soup_actual

    def close(self):
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass