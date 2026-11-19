import re
from urllib.parse import quote
from datetime import datetime

class FacebookParser:
    def recolectar_enlaces_busqueda(self, page, query: str, urls_procesadas: set) -> list:
        enlaces_totales = set()
        
        # Filtros: precio mínimo 100 y orden de MÁS RECIENTE a más antiguo
        url_busqueda = f"https://www.facebook.com/marketplace/lima/search/?query={quote(query)}&minPrice=100&sortBy=creation_time_desc&exact=false"
        
        print(f"  -> Buscando en Marketplace: '{query}'")
        
        try:
            page.goto(url_busqueda, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_selector('div[role="main"]', timeout=5000)
        except:
            pass 

        print("  -> Scrolleando modo rápido (solo recientes)...")
        
        cantidad_anterior = 0
        intentos_sin_crecer = 0
        intentos_sin_nuevos = 0 
        
        for i in range(1, 4):
            urls_js = page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a'))
                    .map(a => a.href)
                    .filter(href => href && href.includes('/marketplace/item/'));
            }''')
            
            nuevos_en_pantalla = 0
            
            for href in urls_js:
                href_limpio = href.split("?")[0]
                if href_limpio.startswith("/"):
                    href_limpio = f"https://www.facebook.com{href_limpio}"
                    
                if href_limpio not in enlaces_totales and href_limpio not in urls_procesadas:
                    enlaces_totales.add(href_limpio)
                    nuevos_en_pantalla += 1
            
            if nuevos_en_pantalla == 0 and len(urls_procesadas) > 0:
                intentos_sin_nuevos += 1
                if intentos_sin_nuevos >= 3: 
                    print("    [!] 3 scrolls seguidos sin ver nada nuevo. Pasando al siguiente distrito.")
                    break
            else:
                intentos_sin_nuevos = 0 
            
            page.keyboard.press("End")
            page.wait_for_timeout(1000) 
            page.keyboard.press("End")
            page.wait_for_timeout(1000)
            
            if len(enlaces_totales) == cantidad_anterior:
                intentos_sin_crecer += 1
                limite_intentos = 4 if cantidad_anterior == 0 else 3
                if intentos_sin_crecer >= limite_intentos:
                    print("    [-] Fin de las publicaciones recientes alcanzado.")
                    break
            else:
                intentos_sin_crecer = 0
                cantidad_anterior = len(enlaces_totales)

        print(f"    [+] {len(enlaces_totales)} anuncios NUEVOS listos para extraer.")
        return list(enlaces_totales)

    def extraer_publicacion(self, page, url: str) -> dict:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

        # 1. Esperar a que aparezca el título real del anuncio en el panel derecho
        try:
            page.wait_for_function('''() => {
                const ignorar = new Set(['Marketplace', 'Notificaciones', 'Facebook', 'Chats']);
                return Array.from(document.querySelectorAll('h1')).some(h => {
                    const t = (h.innerText || '').trim();
                    return t.length > 2 && !ignorar.has(t);
                });
            }''', timeout=8000)
        except Exception:
            page.wait_for_timeout(2000)

        # 2. Hacer clic en "Ver más" para desplegar toda la descripción antes de leer
        try:
            for selector in ['div[role="button"]:has-text("Ver más")', 'div[role="button"]:has-text("See more")']:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=1500)
                    page.wait_for_timeout(600)
                    break
        except Exception:
            pass

        # 3. Capturar únicamente el panel derecho: desde el título hasta antes de "Información del vendedor"
        datos_dinamicos = page.evaluate('''() => {
            let result = {
                descripcion: "",
                fecha: "",
                id_contenido: ""
            };

            const ignorarH1 = new Set(['Marketplace', 'Notificaciones', 'Facebook', 'Chats']);
            const h1 = Array.from(document.querySelectorAll('h1')).find(h => {
                const t = (h.innerText || '').trim();
                return t.length > 2 && !ignorarH1.has(t);
            });

            if (h1) {
                const titulo = h1.innerText.trim();
                let current = h1;
                let panelDerecho = h1;

                // Subir solo hasta el contenedor que engloba el anuncio completo del panel derecho
                while (current.parentElement) {
                    current = current.parentElement;
                    const txt = current.innerText || "";
                    panelDerecho = current;

                    if (
                        txt.includes("Información del vendedor") ||
                        txt.includes("Detalles del vendedor") ||
                        txt.includes("Reporta esta publicación")
                    ) {
                        break;
                    }
                }

                let lines = (panelDerecho.innerText || "")
                    .split('\\n')
                    .map(x => x.trim())
                    .filter(x => x.length > 0);

                // Empezar exactamente en el título del anuncio
                const startIdx = lines.findIndex(l => l === titulo);
                if (startIdx !== -1) {
                    lines = lines.slice(startIdx);
                }

                // Cortar exactamente antes de "Información del vendedor"
                const endIdx = lines.findIndex(l =>
                    l.includes("Información del vendedor") ||
                    l.includes("Detalles del vendedor") ||
                    l.includes("Reporta esta publicación")
                );
                if (endIdx !== -1) {
                    lines = lines.slice(0, endIdx);
                }

                // Limpiar botones de la interfaz
                const botones = new Set([
                    "Enviar mensaje", "Guardar", "Compartir", "Enviar",
                    "Ver más", "Ver menos", "See more", "See less"
                ]);
                const cleanLines = lines.filter(l => !botones.has(l));

                result.descripcion = cleanLines.join(' | ');
            }

            // Fecha de publicación oculta en el HTML
            const html = document.documentElement.innerHTML;
            const matchTime = html.match(/"creation_time":(\\d{10})/);
            if (matchTime) {
                const date = new Date(parseInt(matchTime[1]) * 1000);
                result.fecha = date.toISOString().split('T')[0];
            }

            // ID del anuncio
            const matchId = window.location.href.match(/\\/item\\/(\\d+)/);
            if (matchId) result.id_contenido = matchId[1];

            return result;
        }''')

        descripcion = datos_dinamicos.get("descripcion", "")
        fecha_pub = datos_dinamicos.get("fecha", "") or datetime.now().strftime('%Y-%m-%d')

        id_contenido = datos_dinamicos.get("id_contenido", "")
        if not id_contenido:
            match_id = re.search(r'/marketplace/item/(\d+)', url)
            id_contenido = match_id.group(1) if match_id else ""

        return {
            "id_contenido": id_contenido,
            "fecha_publicacion": fecha_pub,
            "descripcion": descripcion
        }