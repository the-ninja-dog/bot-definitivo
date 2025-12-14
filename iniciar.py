import os
import sys

def main():
    print("--- INICIANDO SISTEMA (MODO RAILWAY COMPATIBLE) ---")
    
    # 1. Instalamos las librerías necesarias (incluyendo gunicorn para Railway)
    print("1. Verificando librerías...")
    os.system("pip install flask twilio google-generativeai flask-cors gunicorn")
    
    # 2. Arrancamos el servidor
    print("\n2. Arrancando servidor...")
    print("✅ Si estás en tu PC: El bot corre en http://localhost:5000")
    print("✅ Si estás en Railway: El bot usará la URL que Railway te asigne.")
    
    # Ejecuta el servidor
    os.system("python api_server.py")

if __name__ == "__main__":
    main()          