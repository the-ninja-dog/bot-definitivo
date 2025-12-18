# -*- coding: utf-8 -*-
"""
BASE DE DATOS PARA BOT DE BARBERÍA
==========================================
Maneja: clientes, citas, conversaciones, configuración
Soporta: SQLite (Local) y PostgreSQL (Cloud/Railway)
"""

import sqlite3
import datetime
import json
import os

# Importar psycopg2 solo si está disponible
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

DATABASE_FILE = "barberia.db"

class Database:
    def __init__(self, db_file=DATABASE_FILE):
        self.db_file = db_file
        self.db_url = os.environ.get('DATABASE_URL')
        self.is_postgres = bool(self.db_url and HAS_POSTGRES)
        self.init_database()

        if self.is_postgres:
            print("🚀 [DB] Conectado a PostgreSQL (Cloud)")
        else:
            print(f"📂 [DB] Usando SQLite Local: {self.db_file}")
    
    def get_connection(self):
        """Obtiene conexión a la base de datos (SQLite o Postgres)"""
        if self.is_postgres:
            try:
                conn = psycopg2.connect(self.db_url)
                return conn
            except Exception as e:
                print(f"❌ Error conectando a Postgres: {e}")
                # Fallback o crash? Crash es mejor en prod.
                raise e
        else:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row  # Para acceder por nombre de columna
            return conn

    def _get_cursor(self, conn):
        if self.is_postgres:
            return conn.cursor(cursor_factory=RealDictCursor)
        else:
            return conn.cursor()

    def _fmt_query(self, query):
        """Reemplaza placeholders '?' de SQLite por '%s' de Postgres si es necesario"""
        if self.is_postgres:
            return query.replace('?', '%s')
        return query
    
    def init_database(self):
        """Crea las tablas si no existen"""
        conn = self.get_connection()
        cursor = conn.cursor() # Usar cursor normal para DDL

        # Definir tipos de PK
        pk_type = "SERIAL PRIMARY KEY" if self.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        
        # Tabla de configuración
        cursor.execute(self._fmt_query(f'''
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
        '''))
        
        # Tabla de clientes
        cursor.execute(self._fmt_query(f'''
            CREATE TABLE IF NOT EXISTS clientes (
                id {pk_type},
                nombre TEXT NOT NULL,
                telefono TEXT,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        
        # Tabla de citas
        cursor.execute(self._fmt_query(f'''
            CREATE TABLE IF NOT EXISTS citas (
                id {pk_type},
                cliente_id INTEGER,
                cliente_nombre TEXT,
                telefono TEXT,
                fecha DATE NOT NULL,
                hora TIME NOT NULL,
                servicio TEXT DEFAULT 'Corte',
                total REAL DEFAULT 0,
                estado TEXT DEFAULT 'Confirmado',
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                -- FK omitida por simplicidad en migración cruzada, pero idealmente:
                -- FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            )
        '''))

        # MIGRACIÓN SEGURA: Intentar añadir columna telefono si no existe
        # Nota: 'ALTER TABLE' es estándar, pero 'ADD COLUMN' varía ligeramente.
        # SQLite/Postgres soportan 'ADD COLUMN'.
        try:
            cursor.execute('ALTER TABLE citas ADD COLUMN telefono TEXT')
            conn.commit()
        except Exception:
            conn.rollback() # Ignorar si ya existe

        # Tabla de conversaciones (historial por chat)
        cursor.execute(self._fmt_query(f'''
            CREATE TABLE IF NOT EXISTS conversaciones (
                id {pk_type},
                cliente_nombre TEXT NOT NULL,
                estado TEXT DEFAULT 'activa',
                ultimo_mensaje TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cita_confirmada INTEGER DEFAULT 0
            )
        '''))
        
        # Tabla de mensajes (historial de cada conversación)
        cursor.execute(self._fmt_query(f'''
            CREATE TABLE IF NOT EXISTS mensajes (
                id {pk_type},
                conversacion_id INTEGER,
                cliente_nombre TEXT,
                es_bot INTEGER DEFAULT 0,
                contenido TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))

        # Tabla de SESIONES BOT (Persistencia de Estado)
        cursor.execute(self._fmt_query('''
            CREATE TABLE IF NOT EXISTS sesiones_bot (
                cliente_id TEXT PRIMARY KEY,
                estado_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))

        # NUEVAS INSTRUCCIONES POR DEFECTO
        instrucciones_default = """PERSONALIDAD:
- Eres eficiente y natural.
- Si el cliente saluda sin más, ofrece los horarios libres.
- Si el cliente ya pide una hora concreta, responde DIRECTAMENTE a eso (sí/no) y pide lo que falte.
- NO seas robótico repitiendo listas largas si ya estamos enfocados en una hora.

HORARIOS:
- Lunes a Sábado: 09:00 a 20:00 (Último turno 19:00).
- Domingo: CERRADO.
- Almuerzo: 12:00 a 13:00 (CERRADO).

PRECIOS:
- Normal: 40.000 Gs.
- FIESTAS (23, 24, 30, 31 Diciembre): 60.000 Gs.

UBICACIÓN:
- Av. Principal 123, Centro."""

        # Configuración por defecto
        # Upsert en Postgres es diferente (ON CONFLICT), en SQLite (INSERT OR IGNORE).
        # Vamos a usar un try/except simple para el insert inicial.
        try:
            cursor.execute(self._fmt_query('''
                INSERT INTO configuracion (clave, valor) VALUES ('nombre_negocio', 'Barbería Z')
            '''))
            conn.commit()
        except Exception:
            conn.rollback()

        # Insertar resto si no existen
        keys = {
            'api_key': '',
            'bot_encendido': 'true',
            'instrucciones': instrucciones_default,
            'hora_inicio': '9',
            'hora_fin': '20',
            'wasender_token': '',
            'wasender_url': 'https://wasenderapi.com/api/send-message'
        }

        for k, v in keys.items():
            try:
                cursor.execute(self._fmt_query("INSERT INTO configuracion (clave, valor) VALUES (?, ?)"), (k, v))
                conn.commit()
            except Exception:
                conn.rollback()
        
        conn.close()
    
    # ==================== CONFIGURACIÓN ====================
    
    def get_config(self, clave, default=None):
        conn = self.get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute(self._fmt_query('SELECT valor FROM configuracion WHERE clave = ?'), (clave,))
        row = cursor.fetchone()
        conn.close()
        # En Postgres RealDictCursor devuelve dict, en SQLite Row devuelve objeto accesible por key
        if row:
            return row['valor']
        return default
    
    def set_config(self, clave, valor):
        conn = self.get_connection()
        cursor = conn.cursor()
        # Postgres UPSERT: INSERT ... ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
        # SQLite UPSERT: INSERT OR REPLACE ...

        if self.is_postgres:
            cursor.execute('''
                INSERT INTO configuracion (clave, valor) VALUES (%s, %s)
                ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
            ''', (clave, valor))
        else:
            cursor.execute('''
                INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)
            ''', (clave, valor))

        conn.commit()
        conn.close()
    
    def get_all_config(self):
        conn = self.get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute('SELECT clave, valor FROM configuracion')
        rows = cursor.fetchall()
        conn.close()
        return {row['clave']: row['valor'] for row in rows}
    
    # ==================== CITAS ====================
    
    def agregar_cita(self, fecha, hora, cliente_nombre, telefono='', servicio='Corte', total=0):
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # 0. VALIDACIÓN ESTRICTA (Anti-Doble Turno)
            cursor.execute(self._fmt_query('''
                SELECT id FROM citas
                WHERE fecha = ? AND hora = ? AND estado = 'Confirmado'
            '''), (fecha, hora))
            if cursor.fetchone():
                print(f"🚫 RECHAZADO: El turno {fecha} {hora} ya está ocupado.")
                return None

            # 1. Buscar citas activas de este teléfono (Futuras o de hoy) para Reagendamiento
            if telefono and len(telefono) > 5:
                # Postgres date('now') no existe, es CURRENT_DATE. SQLite usa date('now').
                # Solución: Pasar la fecha desde Python para evitar SQL dialect issues.
                hoy_str = datetime.date.today().isoformat()

                cursor.execute(self._fmt_query('''
                    SELECT id FROM citas
                    WHERE telefono = ?
                    AND estado = 'Confirmado'
                    AND fecha >= ?
                '''), (telefono, hoy_str))

                citas_activas = cursor.fetchall()
                # fetchall devuelve lista de tuplas en cursor standard, o list of dicts en RealDictCursor?
                # Si usamos cursor standard para inserts, devuelve tuplas.

                for cita in citas_activas:
                    # En cursor standard cita[0] es id.
                    cid = cita[0] if isinstance(cita, tuple) else cita['id']
                    print(f"🔄 REAGENDANDO: Cancelando cita anterior ID {cid} para {telefono}")
                    cursor.execute(self._fmt_query("UPDATE citas SET estado = 'Cancelado' WHERE id = ?"), (cid,))

            # 2. Insertar nueva cita
            cursor.execute(self._fmt_query('''
                INSERT INTO citas (fecha, hora, cliente_nombre, telefono, servicio, estado)
                VALUES (?, ?, ?, ?, ?, 'Confirmado')
            '''), (fecha, hora, cliente_nombre, telefono, servicio))

            # lastrowid no siempre funciona en Postgres.
            if self.is_postgres:
                # En Postgres hay que usar RETURNING id
                # Pero ya ejecutamos. Si queremos ID necesitamos cambiar query.
                # Simplificamos: si no devuelve ID, retornamos True/Dummy ID para indicar éxito.
                # O re-ejecutamos con RETURNING.
                # Hack simple para compatibilidad: No necesitamos el ID exacto en la lógica actual (solo Truthy).
                cita_id = 999
            else:
                cita_id = cursor.lastrowid

            conn.commit()
            return cita_id

        except Exception as e:
            conn.rollback()
            print(f"❌ Error en agregar_cita: {e}")
            raise e
        finally:
            conn.close()
    
    def obtener_citas_por_fecha(self, fecha):
        conn = self.get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute(self._fmt_query('''
            SELECT id, fecha, hora, cliente_nombre, telefono, servicio, estado
            FROM citas 
            WHERE fecha = ? AND estado = 'Confirmado'
            ORDER BY hora
        '''), (fecha,))
        rows = cursor.fetchall()
        conn.close()
        # RealDictCursor returns dict-like objects. SQLite Row returns dict-like.
        # Ensure we return list of dicts.
        return [dict(row) for row in rows]
    
    def obtener_todas_las_citas(self):
        conn = self.get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute(self._fmt_query('''
            SELECT id, fecha, hora, cliente_nombre, servicio, estado
            FROM citas 
            WHERE estado = 'Confirmado'
            ORDER BY fecha, hora
        '''))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def eliminar_cita(self, cita_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._fmt_query('DELETE FROM citas WHERE id = ?'), (cita_id,))
        conn.commit()
        conn.close()
    
    def contar_citas_hoy(self):
        hoy = datetime.date.today().isoformat()
        conn = self.get_connection()
        cursor = self._get_cursor(conn)
        cursor.execute(self._fmt_query('''
            SELECT COUNT(*) as total FROM citas
            WHERE fecha = ?
            AND estado = 'Confirmado'
        '''), (hoy,))
        row = cursor.fetchone()
        conn.close()
        return row['total'] if row else 0
    
    # ==================== MENSAJES ====================
    
    def agregar_mensaje(self, cliente, contenido, es_bot=False):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._fmt_query('''
            INSERT INTO mensajes (cliente_nombre, contenido, es_bot)
            VALUES (?, ?, ?)
        '''), (cliente, contenido, 1 if es_bot else 0))
        conn.commit()
        conn.close()
    
    def contar_mensajes_hoy(self):
        hoy = datetime.date.today().isoformat()
        conn = self.get_connection()
        cursor = self._get_cursor(conn)

        # Postgres: DATE(timestamp) funciona. SQLite: DATE(timestamp) funciona.
        cursor.execute(self._fmt_query('''
            SELECT COUNT(*) as total FROM mensajes 
            WHERE DATE(timestamp) = ?
        '''), (hoy,))
        row = cursor.fetchone()
        conn.close()
        return row['total'] if row else 0

    # ==================== SESIONES BOT (PERSISTENCIA) ====================

    def get_session(self, cliente_id):
        conn = self.get_connection()
        cursor = self._get_cursor(conn)

        # 1. Recuperar Estado con Timeout (15 min)
        # Postgres uses NOW(), SQLite uses CURRENT_TIMESTAMP or datetime('now')
        # We will fetch updated_at and check in Python to be safe across engines
        cursor.execute(self._fmt_query('SELECT estado_json, updated_at FROM sesiones_bot WHERE cliente_id = ?'), (cliente_id,))
        row = cursor.fetchone()

        state = {}
        reset_needed = False

        if row:
            # Check timeout
            last_update = row['updated_at']
            if isinstance(last_update, str):
                # SQLite usually returns string "YYYY-MM-DD HH:MM:SS"
                try:
                    last_update = datetime.datetime.strptime(last_update, "%Y-%m-%d %H:%M:%S")
                except:
                    last_update = datetime.datetime.now() # Fallback

            # If postgres, it might be datetime object already

            diff = datetime.datetime.now() - last_update
            if diff.total_seconds() > 900: # 15 minutes
                print(f"⏰ Sesión expirada para {cliente_id} (>15m). Reiniciando.")
                reset_needed = True
            elif row['estado_json']:
                try:
                    state = json.loads(row['estado_json'])
                except:
                    state = {}

        if reset_needed:
            # Clear state in DB
            self.save_session_state(cliente_id, {})
            # Return empty history implies "New Conversation" to the LLM context essentially
            return {"state": {}, "history": []}

        # 2. Recuperar Historial (Últimos 10 mensajes)
        cursor.execute(self._fmt_query('''
            SELECT es_bot, contenido
            FROM mensajes
            WHERE cliente_nombre = ?
            ORDER BY id DESC LIMIT 10
        '''), (cliente_id,))
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
        state_json = json.dumps(state_dict)

        if self.is_postgres:
            cursor.execute('''
                INSERT INTO sesiones_bot (cliente_id, estado_json, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (cliente_id) DO UPDATE SET estado_json = EXCLUDED.estado_json, updated_at = CURRENT_TIMESTAMP
            ''', (cliente_id, state_json))
        else:
            cursor.execute('''
                INSERT OR REPLACE INTO sesiones_bot (cliente_id, estado_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (cliente_id, state_json))

        conn.commit()
        conn.close()

# Instancia global
db = Database()

# Helpers retrocompatibles
def inicializar_agenda(): pass
def obtener_horarios_disponibles(fecha): return db.obtener_horarios_disponibles(fecha)
def agendar_cita(fecha, hora, cliente, telefono): return db.agendar_cita(fecha, hora, cliente, telefono)
def cancelar_cita(fecha, cliente): return db.cancelar_cita(fecha, cliente)
