

import requests

# 1. Pega tu API Key aquí
API_KEY = "AIzaSyB7qtjoa9juIB916UcTcpMifgkxbYiUA3A"

def probar_google_directo():
    print("Consultando a Google directamente...")
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address=Lima,+Peru&key={API_KEY}"
    
    try:
        respuesta = requests.get(url)
        datos = respuesta.json()
        
        estado = datos.get("status")
        
        if estado == "OK":
            print("✅ ¡ÉXITO! Tu API Key está funcionando perfecto.")
            print(f"Resultado: {datos['results'][0]['formatted_address']}")
        else:
            print(f"❌ GOOGLE RECHAZÓ LA PETICIÓN. Estado: {estado}")
            print(f"Mensaje de error oficial de Google: {datos.get('error_message', 'No hay mensaje')}")
            
    except Exception as e:
        print(f"Error de conexión: {e}")

if __name__ == "__main__":
    probar_google_directo()