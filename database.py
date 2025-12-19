import sqlite3
import datetime
import json
import os
import time

# Nombre de la DB
DB_NAME = "barberia.db"

class Database:
    def __init__(self):
        self.db_path = os.path.join(os.getcwd(), DB_NAME)
        self.init_db()

    def get_connection(self):
        """Crea una conexión a la base de datos"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Inicializa tablas y carga datos del video"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 1. Tabla Citas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS citas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT NOT NULL,
                telefono TEXT,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                servicio TEXT,
                estado TEXT DEFAULT 'Confirmado',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. Tabla Configuración
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
        ''')

        # 3. Tabla Mensajes (Historial Chat)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_nombre TEXT,
                contenido TEXT,
                es_bot INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 4. Tabla Sesiones (Memoria IA)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sesiones_bot (
                cliente_id TEXT PRIMARY KEY,
                estado_json TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # Cargar datos iniciales (Seed del Video)
        self.migrar_datos_video()

    def migrar_datos_video(self):
        """Inserta los turnos del video si no existen"""
        # Lista de turnos del video (Ya convertidos a 24hs)
        turnos_video = [
            # Viernes 19/12
            ("Matias", "2025-12-19", "10:00"),
            ("Dario", "2025-12-19", "13:00"),
            ("Facundo", "2025-12-19", "17:00"),
            ("Chocho", "2025-12-19", "19:00"),
            # Sabado 20/12
            ("Thiago", "2025-12-20", "08:00"),
            ("Monyo", "2025-12-20", "09:00"),
            ("Ale", "2025-12-20", "10:00"),
            ("Lucas", "2025-12-20", "11:00"),
            ("Dionisio", "2025-12-20", "12:00"),
            ("Martin Silva", "2025-12-20", "16:00"),
            ("Mati Aranda", "2025-12-20", "17:00"),
            ("Elías Chávez", "2025-12-20", "18:00"),
            ("Ian", "2025-12-20", "19:00"),
            ("Kevin Fariña", "2025-12-20", "20:00"),
            ("Lucas Obregón", "2025-12-20", "21:00"),
            # Lunes 22/12
            ("Joaquín", "2025-12-22", "09:00"),
            ("Erick", "2025-12-22", "13:00"),
            ("Jun", "2025-12-22", "14:00"),
            ("Thiago Vivero", "2025-12-22", "17:00"),
            ("Chocho", "2025-12-22", "19:00"),
            ("Brian", "2025-12-22", "20:00"),
            # Martes 23/12
            ("Santiago", "2025-12-23", "15:00"),
            ("Esteban Pesoa", "2025-12-23", "18:00"),
            ("Noa", "2025-12-23", "21:00"),
        ]

        conn = self.get_connection()
        cursor = conn.cursor()
        
        count_inserts = 0
        for cliente, fecha, hora in turnos_video:
            # Verificar si ya existe para no duplicar
            cursor.execute("SELECT id FROM citas WHERE fecha = ? AND hora = ?", (fecha, hora))
            data = cursor.fetchone()
            if not data:
                cursor.execute("INSERT INTO citas (cliente, fecha, hora, servicio) VALUES (?, ?, ?, ?)", 
                               (cliente, fecha, hora, "Corte (Importado)"))
                count_inserts += 1
                
        conn.commit()
        conn.close()
        if count_inserts > 0:
            print(f"🔄 [DB] Se importaron {count_inserts} turnos del video.")

    # === FUNCIONES QUE PIDE TU API_SERVER.PY ===

    def get_config(self, clave, default=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM config WHERE clave = ?", (clave,))
        row = cursor.fetchone()
        conn.close()
        return row['valor'] if row else default

    def get_all_config(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT clave, valor FROM config")
        rows = cursor.fetchall()
        conn.close()
        return {row['clave']: row['valor'] for row in rows}
        
    def set_config(self, clave, valor):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", (clave, valor))
        conn.commit()
        conn.close()

    def obtener_citas_por_fecha(self, fecha):
        """Retorna lista de citas para verificar disponibilidad"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM citas WHERE fecha = ? AND estado = 'Confirmado'", (fecha,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def obtener_todas_las_citas(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM citas ORDER BY fecha DESC, hora DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def contar_citas_hoy(self):
        hoy = datetime.date.today().isoformat()
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM citas WHERE fecha = ?", (hoy,))
        res = cursor.fetchone()[0]
        conn.close()
        return res

    def contar_mensajes_hoy(self):
        hoy = datetime.date.today().isoformat()
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM mensajes WHERE date(timestamp) = ?", (hoy,))
        res = cursor.fetchone()[0]
        conn.close()
        return res

    def agregar_mensaje(self, cliente, contenido, es_bot=False):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO mensajes (cliente_nombre, contenido, es_bot) VALUES (?, ?, ?)", 
                       (cliente, contenido, 1 if es_bot else 0))
        conn.commit()
        conn.close()

    def agregar_cita(self, fecha, hora, cliente_nombre, telefono, servicio):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")
            # Verificar disponibilidad
            cursor.execute("SELECT count(*) FROM citas WHERE fecha = ? AND hora = ?", (fecha, hora))
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                return None
            
            cursor.execute("INSERT INTO citas (cliente, telefono, fecha, hora, servicio) VALUES (?, ?, ?, ?, ?)",
                           (cliente_nombre, telefono, fecha, hora, servicio))
            last_id = cursor.lastrowid
            conn.commit()
            return last_id
        except Exception as e:
            conn.rollback()
            print(f"Error DB: {e}")
            return None
        finally:
            conn.close()

    def eliminar_cita(self, cita_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM citas WHERE id = ?", (cita_id,))
        conn.commit()
        conn.close()

    # === MANEJO DE SESIONES (MEMORIA) ===
    def get_session(self, cliente_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 1. Obtener estado
        cursor.execute("SELECT estado_json FROM sesiones_bot WHERE cliente_id = ?", (cliente_id,))
        row = cursor.fetchone()
        state = json.loads(row['estado_json']) if row and row['estado_json'] else {}

        # 2. Obtener historial reciente
        cursor.execute("SELECT es_bot, contenido FROM mensajes WHERE cliente_nombre = ? ORDER BY id DESC LIMIT 6", (cliente_id,))
        rows = cursor.fetchall()
        
        history = []
        for r in rows:
            role = "assistant" if r['es_bot'] else "user"
            history.insert(0, {"role": role, "content": r['contenido']})
            
        conn.close()
        return {"state": state, "history": history}

    def save_session_state(self, cliente_id, state_dict):
        conn = self.get_connection()
        cursor = conn.cursor()
        json_str = json.dumps(state_dict)
        cursor.execute("INSERT OR REPLACE INTO sesiones_bot (cliente_id, estado_json) VALUES (?, ?)", (cliente_id, json_str))
        conn.commit()
        conn.close()

# INSTANCIA GLOBAL (Importante para api_server.py)
db = Database()