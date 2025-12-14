# -*- coding: utf-8 -*-
"""
SERVIDOR PARA RAILWAY
======================
Solo ejecuta el API Server
El bot se ejecuta en una tarea separada
"""

import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Importar la app de api_server
from api_server import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    print("\n" + "="*60)
    print("  🌐 SERVIDOR API - Railway")
    print("="*60)
    print(f"  Puerto: {port}")
    print(f"  Debug: {debug}")
    print(f"  URL: https://tuapp.railway.app")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
