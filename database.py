# -*- coding: utf-8 -*-
"""
BASE DE DATOS SQLITE PARA BOT DE BARBERÍA
==========================================
Maneja: clientes, citas, conversaciones, configuración
"""

import sqlite3
import datetime
import json
import os

DATABASE_FILE = "barberia.db"

class Database:
    def __init__(self, db_file=DATABASE_FILE):
        self.db_file = db_file
        self.init_database()
    
    def get_connection(self):
        """Obtiene conexión a la base de datos"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row  # Para acceder por nombre de columna
        return conn
    
    def init_database(self):
        """Crea las tablas si no existen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Tabla de configuración
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
        ''')
        
        # [Se omiten otras tablas por brevedad, no se modifican]
        
        # Tabla de clientes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de citas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS citas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                cliente_nombre TEXT,
                telefono TEXT,
                fecha DATE NOT NULL,
                hora TIME NOT NULL,
                servicio TEXT DEFAULT 'Corte',
                total REAL DEFAULT 0,
                estado TEXT DEFAULT 'Confirmado',
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            )
        ''')
        
        # MIGRACIÓN SEGURA: Intentar añadir columna telefono si no existe
        try:
            cursor.execute('ALTER TABLE citas ADD COLUMN telefono TEXT')
        except sqlite3.OperationalError:
            pass # La columna ya existe, todo bien

        # Tabla de conversaciones (historial por chat)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_nombre TEXT NOT NULL,
                estado TEXT DEFAULT 'activa',
                ultimo_mensaje DATETIME DEFAULT CURRENT_TIMESTAMP,
                cita_confirmada INTEGER DEFAULT 0
            )
        ''')
        
        # Tabla de mensajes (historial de cada conversación)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversacion_id INTEGER,
                cliente_nombre TEXT,
                es_bot INTEGER DEFAULT 0,
                contenido TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversacion_id) REFERENCES conversaciones(id)
            )
        ''')
        
        # NUEVAS INSTRUCCIONES POR DEFECTO (AMIGABLES)
        instrucciones_default = """PERSONALIDAD:
- Eres un asistente AMIGABLE y buena onda ("crack", "bro", "genio").
- NO seas aburrido. Usa emojis ocasionalmente.
- Sé servicial pero ve al grano.

HORARIOS:
- Lunes a Sábado: 09:00 a 18:00 (Último turno 17:00).
- Domingo: CERRADO.
- Almuerzo: 12:00 a 13:00 (CERRADO).

PRECIOS:
- Corte: $10
- Barba: $5
- Corte + Barba: $12

UBICACIÓN:
- Av. Principal 123, Centro."""

        # Configuración por defecto (MIGRACIÓN A WASENDER)
        cursor.execute('''
            INSERT OR IGNORE INTO configuracion (clave, valor) VALUES
            ('nombre_negocio', 'Barbería Z'),
            ('api_key', ''),
            ('bot_encendido', 'true'),
            ('instrucciones', ?),
            ('contactos_ignorados', '[]'),
            ('hora_inicio', '9'),
            ('hora_fin', '20'),
            ('wasender_token', ''),  -- Token de WaSender
            ('wasender_url', 'https://wasenderapi.com/api/send-message') -- URL por defecto
        ''', (instrucciones_default,))

        # Limpieza de claves viejas de Twilio (Opcional, pero bueno para mantener limpio)
        cursor.execute("DELETE FROM configuracion WHERE clave LIKE 'twilio%'")
        
        conn.commit()
        conn.close()
        print(f"[DB] Base de datos inicializada: {self.db_file}")
    
    # [El resto de métodos (get_config, set_config, etc.) quedan igual]
    
    # ==================== CONFIGURACIÓN ====================
    
    def get_config(self, clave, default=None):
        """Obtiene un valor de configuración"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT valor FROM configuracion WHERE clave = ?', (clave,))
        row = cursor.fetchone()
        conn.close()
        return row['valor'] if row else default
    
    def set_config(self, clave, valor):
        """Establece un valor de configuración"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)
        ''', (clave, valor))
        conn.commit()
        conn.close()
    
    def get_all_config(self):
        """Obtiene toda la configuración como diccionario"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT clave, valor FROM configuracion')
        rows = cursor.fetchall()
        conn.close()
        return {row['clave']: row['valor'] for row in rows}
    
    # ==================== CITAS ====================
    
    def agregar_cita(self, fecha, hora, cliente_nombre, telefono='', servicio='Corte', total=0):
        """Agrega una nueva cita"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO citas (fecha, hora, cliente_nombre, telefono, servicio, estado)
            VALUES (?, ?, ?, ?, ?, 'Confirmado')
        ''', (fecha, hora, cliente_nombre, telefono, servicio))
        conn.commit()
        cita_id = cursor.lastrowid
        conn.close()
        return cita_id
    
    def obtener_citas_por_fecha(self, fecha):
        """Obtiene todas las citas de una fecha específica"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, fecha, hora, cliente_nombre, servicio, estado
            FROM citas 
            WHERE fecha = ?
            ORDER BY hora
        ''', (fecha,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def obtener_todas_las_citas(self):
        """Obtiene todas las citas"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, fecha, hora, cliente_nombre, servicio, estado
            FROM citas 
            ORDER BY fecha, hora
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def cancelar_cita_por_id(self, cita_id):
        """Cancela una cita por su ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('Cancelado', cita_id))
        conn.commit()
        conn.close()
    
    def eliminar_cita(self, cita_id):
        """Elimina una cita por su ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM citas WHERE id = ?', (cita_id,))
        conn.commit()
        conn.close()
    
    def contar_citas_hoy(self):
        """Cuenta las citas de hoy"""
        hoy = datetime.date.today().isoformat()
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as total FROM citas WHERE fecha = ?', (hoy,))
        row = cursor.fetchone()
        conn.close()
        return row['total'] if row else 0
    
    # ==================== MENSAJES ====================
    
    def agregar_mensaje(self, cliente, contenido, es_bot=False):
        """Agrega un mensaje al historial"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO mensajes (cliente_nombre, contenido, es_bot)
            VALUES (?, ?, ?)
        ''', (cliente, contenido, 1 if es_bot else 0))
        conn.commit()
        conn.close()
    
    def contar_mensajes_hoy(self):
        """Cuenta los mensajes de hoy"""
        hoy = datetime.date.today().isoformat()
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as total FROM mensajes 
            WHERE DATE(timestamp) = ?
        ''', (hoy,))
        row = cursor.fetchone()
        conn.close()
        return row['total'] if row else 0

# Instancia global
db = Database()


# Para retrocompatibilidad con agenda_helper
def inicializar_agenda():
    """Compatibilidad con código anterior"""
    pass  # La DB se inicializa sola

def obtener_horarios_disponibles(fecha):
    """Compatibilidad con código anterior"""
    return db.obtener_horarios_disponibles(fecha)

def agendar_cita(fecha, hora, cliente, telefono):
    """Compatibilidad con código anterior"""
    return db.agendar_cita(fecha, hora, cliente, telefono)

def cancelar_cita(fecha, cliente):
    """Compatibilidad con código anterior"""
    return db.cancelar_cita(fecha, cliente)