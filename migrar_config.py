# -*- coding: utf-8 -*-
"""
SCRIPT DE MIGRACIÓN
===================
Migra la API key del config_barberia.json a la nueva base de datos SQLite
"""

import json
import os

def migrar():
    # Cargar config viejo
    config_viejo = "config_barberia.json"
    
    if os.path.exists(config_viejo):
        with open(config_viejo, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Importar base de datos
        from database import db
        
        # Migrar cada valor
        if config.get('api_key'):
            db.set_config('api_key', config['api_key'])
            print(f"[OK] API Key migrada")
        
        if config.get('nombre_negocio'):
            db.set_config('nombre_negocio', config['nombre_negocio'])
            print(f"[OK] Nombre del negocio: {config['nombre_negocio']}")
        
        if config.get('instrucciones'):
            db.set_config('instrucciones', config['instrucciones'])
            print(f"[OK] Instrucciones migradas")
        
        if config.get('contactos_ignorados'):
            db.set_config('contactos_ignorados', json.dumps(config['contactos_ignorados']))
            print(f"[OK] Contactos ignorados migrados")
        
        print("\n[OK] Migracion completada!")
        print("Puedes eliminar config_barberia.json si quieres")
    else:
        print(f"No se encontró {config_viejo}")


if __name__ == "__main__":
    migrar()
