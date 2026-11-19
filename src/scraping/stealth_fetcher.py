import os, platform, random, shutil, subprocess, time, urllib.request, logging
from pathlib import Path
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from config.settings import RAW_DIR

CHROME_CDP_DIR = RAW_DIR / "sessions" / "chrome_cdp_profile"
CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

def _puerto_cdp_activo() -> bool:
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False

def _lanzar_chrome_limpio() -> bool:
    if _puerto_cdp_activo(): return True
    # Busca chrome nativo
    rutas = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    ejecutable = next((r for r in rutas if Path(r).exists()), None)
    if not ejecutable: return False
    
    CHROME_CDP_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([ejecutable, f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={CHROME_CDP_DIR}", "--no-first-run", "--start-maximized"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        if _puerto_cdp_activo():
            time.sleep(1)
            return True
        time.sleep(0.5)
    return False


class MotorBase:
    def navegar(self, url: str): pass
    def obtener_html(self) -> str: pass
    def obtener_soup(self) -> BeautifulSoup: pass
    def cerrar(self): pass


class PlaywrightEngine(MotorBase):
    def __init__(self, headless=False):
        self.playwright = sync_playwright().start()
        _lanzar_chrome_limpio()
        try:
            self.browser = self.playwright.chromium.connect_over_cdp(CDP_URL)
            self.context = self.browser.contexts[0]
            logging.info("[*] Motor Playwright Nativo Iniciado.")
        except Exception:
            self.context = self.playwright.chromium.launch_persistent_context(user_data_dir=str(CHROME_CDP_DIR), headless=headless)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def navegar(self, url: str):
        time.sleep(random.uniform(1.0, 2.0))
        self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
        self.page.wait_for_timeout(1500)
        
        # Bypass manual ligero para Playwright si cayera en CF
        if any(x in self.page.title().lower() for x in ["just a moment", "un momento", "attention"]):
            logging.warning("[!] Playwright chocó con Cloudflare. Intentando clic automático...")
            try:
                for sel in ['iframe[src*="challenges"]', '#challenge-stage']:
                    if self.page.locator(sel).count() > 0:
                        b = self.page.locator(sel).first.bounding_box()
                        if b: self.page.mouse.click(b["x"] + 20, b["y"] + b["height"]/2)
            except Exception: pass
            self.page.wait_for_timeout(4000)

    def obtener_html(self) -> str:
        return self.page.content()
        
    def obtener_soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.obtener_html(), "html.parser")

    def cerrar(self):
        self.playwright.stop()


class CurlCffiEngine(MotorBase):
    def __init__(self):
        self.session = cffi_requests.Session(impersonate="chrome120")
        self.html_actual = ""
        logging.info("[*] Motor Curl_CFFI (Bypass TLS) Iniciado.")

    def navegar(self, url: str):
        time.sleep(random.uniform(1.0, 2.5))
        try:
            resp = self.session.get(url, timeout=15)
            self.html_actual = resp.text
        except Exception as e:
            logging.error(f"[!] Error de red CurlCFFI en {url}: {e}")
            self.html_actual = ""

    def obtener_html(self) -> str:
        return self.html_actual

    def obtener_soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.html_actual, "html.parser")

    def cerrar(self):
        self.session.close()


def obtener_motor(tipo: str, headless: bool = False) -> MotorBase:
    if tipo == "curl_cffi":
        return CurlCffiEngine()
    return PlaywrightEngine(headless)