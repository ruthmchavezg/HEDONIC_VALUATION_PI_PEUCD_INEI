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
            page.goto(url, wait_until="domcontentloaded", timeout=6000)
        except:
            pass 
            
        page.wait_for_timeout(1500) 
        
        datos_dinamicos = page.evaluate('''() => {
            let result = {
                descripcion: "", 
                fecha: "",
                id_contenido: ""
            };
            
            // Clic en "Ver más"
            let btns = Array.from(document.querySelectorAll('div[role="button"]'));
            let btnVerMas = btns.find(b => b.innerText && (b.innerText.includes("Ver más") || b.innerText.includes("See more")));
            if(btnVerMas) btnVerMas.click();

            let h1 = document.querySelector('h1');
            if (h1) {
                let current = h1;
                let bestContainer = current;
                
                // Subimos contenedor por contenedor
                while (current.parentElement) {
                    current = current.parentElement;
                    let text = current.innerText;
                    
                    if (text.includes("Sugerencias de hoy") || text.includes("Today's suggestions") || text.includes("Más publicaciones")) {
                        break;
                    }
                    bestContainer = current;
                }
                
                // Limpieza de renglones
                let lines = bestContainer.innerText.split('\\n').map(x => x.trim()).filter(x => x.length > 0);
                let cleanLines = lines.filter(l => !["Ver más", "Ver menos", "Enviar mensaje", "Guardar", "Compartir", "Enviar", "See more", "See less"].includes(l));
                
                // 🚀 CORTE EXACTO ANTES DE LA INFORMACIÓN DEL VENDEDOR
                let endIdx = cleanLines.findIndex(l => l.includes("Información del vendedor") || l.includes("Detalles del vendedor") || l.includes("Reporta esta publicación"));
                if (endIdx !== -1) {
                    cleanLines = cleanLines.slice(0, endIdx);
                }
                
                result.descripcion = cleanLines.join(' | ');
            } else {
                let mainDiv = document.querySelector('div[role="main"]');
                if (mainDiv) {
                    result.descripcion = mainDiv.innerText.replace(/\\n/g, ' | ');
                }
            }
            
            // 2. FECHA DE PUBLICACIÓN OCULTA
            let html = document.documentElement.innerHTML;
            let matchTime = html.match(/"creation_time":(\\d{10})/);
            if(matchTime) {
                let date = new Date(parseInt(matchTime[1]) * 1000);
                result.fecha = date.toISOString().split('T')[0];
            }
            
            // 3. ID CONTENIDO
            let matchId = window.location.href.match(/\\/item\\/(\\d+)/);
            if(matchId) result.id_contenido = matchId[1];
            
            return result;
        }''')

        descripcion = datos_dinamicos.get("descripcion", "")
        
        fecha_pub = datos_dinamicos.get("fecha", "")
        if not fecha_pub:
            fecha_pub = datetime.now().strftime('%Y-%m-%d')
            
        id_contenido = datos_dinamicos.get("id_contenido", "")
        if not id_contenido:
            match_id = re.search(r'/marketplace/item/(\d+)', url)
            id_contenido = match_id.group(1) if match_id else ""

        return {
            "id_contenido": id_contenido,
            "fecha_publicacion": fecha_pub,
            "descripcion": descripcion
        }