# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from groq import Groq
import datetime
import re
import json
from database import db
import os
import requests
import time
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

<<<<<<< HEAD
# Servir Flutter web desde build/web
app = Flask(__name__, static_folder='build/web', static_url_path='')
=======
# Use absolute path for static folder to avoid CWD issues
# UPDATE: Renaming to 'web' to match standard Flutter build output
STATIC_FOLDER = os.path.join(os.getcwd(), 'web')
# Disable default static routing to prevent conflicts
app = Flask(__name__, static_folder=None)
>>>>>>> b23a026260ad094a3226be3ee6bd56b737a0c5fa
CORS(app)

# === API KEYS DE GROQ (ROTACIÓN) ===
GROQ_API_KEYS = [
    os.environ.get('GROQ_API_KEY', ''),
    os.environ.get('GROQ_API_KEY_2', ''),
]
GROQ_API_KEYS = [k for k in GROQ_API_KEYS if k]
current_key_index = 0

# === CLIENTE WASENDER (NUEVO) ===
WASENDER_URL = "https://wasenderapi.com/api/send-message"
WASENDER_TOKEN = "23b0342bd631a643edbb96b4c9c2d29ae77fff50c1597fed8d3e92eeef5b6ebd"

# LISTA NEGRA DE NOMBRES
NAME_BLACKLIST = ['bro', 'man', 'kp', 'kape', 'amigo', 'hola', 'buenas', 'que tal', 'haupei', 'info', 'precio', 'sera']

def enviar_mensaje_wasender(to, text):
    """Envía mensaje usando WaSender con manejo de errores y throttling"""
    # 1. Throttling (Seguridad)
    time.sleep(2)

    headers = {
        "Authorization": f"Bearer {WASENDER_TOKEN}",
        "Content-Type": "application/json"
    }

    # Asegurar formato del número (WaSender suele pedir solo números, sin + o con + según proveedor, probamos con +)
    # FIX: WaSender rechaza + para JIDs. Solo agregamos @s.whatsapp.net si es solo número
    to = to.replace('+', '')
    if '@' not in to:
        to = to + "@s.whatsapp.net"

    payload = {
        "to": to,
        "text": text
    }

    try:
        print(f"📤 ENVIANDO A WASENDER: {to} -> {text[:20]}...")
        response = requests.post(WASENDER_URL, json=payload, headers=headers, timeout=10)

        if response.status_code in [200, 201]:
            print("✅ WaSender: Enviado OK")
            return True
        else:
            print(f"❌ WaSender Error {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print(f"❌ WaSender Exception: {str(e)}")
        return False

# === MEMORIA DE ESTADO (CONVERSACIÓN + INTENCIÓN) ===
# sesiones = {}  <-- Eliminado, ahora usamos DB

# === HELPER DISPONIBILIDAD INTELIGENTE ===
def obtener_estado_agenda(dias=5):
    # Usar timezone UTC para evitar deprecation warning, luego restar 4 horas
    ahora = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)
    resumen = []

    # Horas posibles de 08:00 a 19:00 (Cierre 20:00)
    # Excluyendo almuerzo 12:00
    # FIX: Opening at 08:00 AM as per new instruction
    horas_totales = [f"{h:02d}:00" for h in range(8, 20) if h != 12]

    for i in range(dias):
        fecha_obj = ahora + datetime.timedelta(days=i)
        fecha_str = fecha_obj.strftime('%Y-%m-%d')
        dia_semana = fecha_obj.weekday()

        if dia_semana == 6:
            resumen.append(f"🚫 {fecha_str} (DOMINGO): CERRADO.")
            continue

        citas = db.obtener_citas_por_fecha(fecha_str)
        ocupadas = [c['hora'][:5] for c in citas]

        # Calcular disponibles
        disponibles = [h for h in horas_totales if h not in ocupadas]

        # Si es HOY, filtrar horas pasadas
        if i == 0:
            hora_actual_int = int(ahora.strftime('%H'))
            disponibles = [h for h in disponibles if int(h[:2]) > hora_actual_int]

        resumen.append(f"📅 {fecha_str}:")
        if disponibles:
            # Formato simplificado para evitar confusión del LLM
            resumen.append(f"   [DISPONIBLE]: {', '.join(disponibles)}")
        else:
            resumen.append("   [AGOTADO]")

    return "\n".join(resumen)

# === HELPER: NORMALIZACIÓN DE HORA (1-7 PM Rule) ===
def normalizar_hora_str(hora_raw):
    """Convierte inputs como '5', '17', '5:00' a formato 'HH:MM' 24h usando regla PM"""
    h_int = -1
    minutes_str = "00"

    # Limpieza
    clean = hora_raw.lower().replace('hs', '').replace('h', '').replace('pm', '').replace('am', '').strip()

    if ':' in clean:
        try:
            parts = clean.split(':')
            h_int = int(parts[0])
            minutes_str = parts[1]
        except: pass
    elif clean.isdigit():
        h_int = int(clean)

    if h_int != -1:
        # 1 <= h <= 7 -> PM (13-19)
        if 1 <= h_int <= 7:
            return f"{h_int + 12}:{minutes_str}"
        # 8 <= h <= 11 -> AM (8-11)
        elif 8 <= h_int <= 11:
             return f"{h_int:02d}:{minutes_str}"
        # 12 <= h <= 23 -> Mantiene
        elif 12 <= h_int <= 23:
             return f"{h_int:02d}:{minutes_str}"

    return None

# === HELPER: DETECCIÓN DE CONFLICTOS ===
def analizar_conflicto_horario(mensaje):
    """Revisa si el usuario pide una hora específica que YA está ocupada"""
    try:
        # 1. Determinar fecha (Hoy o Mañana)
        ahora = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)
        target_date = ahora

        msg_lower = mensaje.lower()
        if 'mañana' in msg_lower:
            target_date = ahora + datetime.timedelta(days=1)
        elif 'lunes' in msg_lower or 'martes' in msg_lower:
            # Si menciona un día, asumimos que el LLM lo manejará,
            # o podríamos implementar lógica compleja.
            # Por seguridad, si es explicito "mañana", chequeamos. Si es hoy (implícito), chequeamos.
            pass

        fecha_str = target_date.strftime('%Y-%m-%d')

        # 2. Extraer posibles horas del mensaje (Ej: "5", "17:00", "5 pm")
        # Regex captura números 1-23 opcionalmente seguidos de :00-59
        matches = re.findall(r'\b(\d{1,2})(?::(\d{2}))?\b', mensaje)

        if not matches:
            return None

        citas = db.obtener_citas_por_fecha(fecha_str)
        ocupadas = [c['hora'][:5] for c in citas] # ['17:00', '18:00']

        alertas = []
        for m in matches:
            h_str = m[0]
            if m[1]: h_str += ":" + m[1]

            norm = normalizar_hora_str(h_str)
            if norm and norm in ocupadas:
                alertas.append(f"{norm} ({fecha_str})")

        if alertas:
            lista_conflictos = ", ".join(alertas)
            return f"""[ALERTA DE SISTEMA CRÍTICA]: El usuario preguntó por el horario: {lista_conflictos}.
            ESE HORARIO YA ESTÁ RESERVADO/OCUPADO en la base de datos.
            ⚠️ DEBES RESPONDER QUE NO ESTÁ DISPONIBLE y ofrecer otra hora cercana. NO CONFIRMES."""

    except Exception as e:
        print(f"⚠️ Error analizando conflicto: {e}")

    return None

# === PROCESADOR DE MEMORIA LLM ===
def procesar_memoria_ia(respuesta, estado_actual):
    """Extrae y actualiza el estado basado en la respuesta JSON oculta del LLM"""
    nuevo_estado = estado_actual.copy()
    try:
        # Buscar bloque [MEMORIA]...[/MEMORIA]
        match = re.search(r'\[MEMORIA\](.*?)\[/MEMORIA\]', respuesta, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            # Intento de corrección de JSON común (comillas simples a dobles)
            json_str = json_str.replace("'", '"')
            datos = json.loads(json_str)

            # Actualizar campos si no están vacíos y son válidos

            # 1. Validación de NOMBRE (Blacklist)
            if datos.get('nombre'):
                nombre_candidato = str(datos['nombre']).strip()
                if nombre_candidato.lower() not in NAME_BLACKLIST:
                    nuevo_estado['nombre'] = nombre_candidato
                else:
                    print(f"⚠️ Nombre '{nombre_candidato}' en lista negra. Ignorando.")

            if datos.get('fecha'): nuevo_estado['fecha_intencion'] = datos['fecha']
            if datos.get('servicio'): nuevo_estado['servicio'] = datos['servicio']

            # 2. Lógica de corrección de HORA (AM/PM) y RANGO
            if datos.get('hora'):
                # Usar el helper centralizado
                hora_final = normalizar_hora_str(str(datos['hora'])) or datos['hora']

                # 3. Validación de Rango (08:00 - 20:00)
                try:
                    h_check = int(hora_final.split(':')[0])
                    # Abierto de 8 a 20. Última cita probable 19:00.
                    # Si es >= 20, está cerrado. Si es < 8, cerrado.
                    if h_check < 8 or h_check >= 20:
                        # Si está fuera de rango, NO lo guardamos (o lo borramos si existía)
                        print(f"⚠️ Hora {hora_final} fuera de rango (8-20). Ignorando.")
                        if 'hora_intencion' in nuevo_estado:
                            del nuevo_estado['hora_intencion']
                    else:
                        nuevo_estado['hora_intencion'] = hora_final
                except:
                    # Si no podemos validar, no guardamos basura
                    pass

            print(f"🧠 MEMORIA ACTUALIZADA: {nuevo_estado}")
    except Exception as e:
        print(f"⚠️ Error procesando memoria IA: {e}")

    return nuevo_estado

# === BOT LOGIC ===
def generar_respuesta_ia(mensaje, cliente, push_name=None):
    global current_key_index
    
    bot_encendido = db.get_config('bot_encendido', 'true')
    if bot_encendido != 'true':
        return None
    
    if not GROQ_API_KEYS:
        return "Error: Sistema no configurado."
    
    config = db.get_all_config()
    nombre_negocio = config.get('nombre_negocio', 'Barbería Z')
    instrucciones_negocio = config.get('instrucciones', 'Horario: 8am-8pm. Corte $10.')
    
    # Cálculo robusto de fecha/hora (UTC-4)
    ahora = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)
    fecha_hoy = ahora.strftime('%Y-%m-%d')
    hora_actual = ahora.strftime('%H:%M')
    dia_semana_int = ahora.weekday()
    dia_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][dia_semana_int]

    print(f"🕒 SERVER TIME (UTC-4): {fecha_hoy} {hora_actual} ({dia_semana})")

    # Recuperar sesión desde DB (Persistencia)
    sesion = db.get_session(cliente)
    estado_actual = sesion['state']

    # AUTO-LEARN NAME from PushName if not known
    if not estado_actual.get('nombre') and push_name:
         # Filter pushname too
         if push_name.lower() not in NAME_BLACKLIST:
             print(f"👤 Auto-detectando nombre de WhatsApp: {push_name}")
             estado_actual['nombre'] = push_name.title() # Title case fix
             # Guardamos inmediatamente para que el prompt lo use
             db.save_session_state(cliente, estado_actual)

    estado_agenda = obtener_estado_agenda(5)

    contexto_memoria = ""
    if estado_actual.get('nombre'):
        contexto_memoria += f"- NOMBRE: {estado_actual['nombre'].title()}\n"
    if estado_actual.get('fecha_intencion'):
        contexto_memoria += f"- FECHA: {estado_actual['fecha_intencion']}\n"
    if estado_actual.get('hora_intencion'):
        contexto_memoria += f"- HORA: {estado_actual['hora_intencion']}\n"
    if estado_actual.get('servicio'):
        contexto_memoria += f"- SERVICIO: {estado_actual['servicio']}\n"

    # === DETECCIÓN PROACTIVA DE CONFLICTOS (EMERGENCY FIX) ===
    alerta_conflicto = analizar_conflicto_horario(mensaje)

    # === LÓGICA DE ESTADOS DINÁMICA (STATE MACHINE) ===
    # Determinamos qué falta para guiar al LLM con una instrucción ÚNICA y CLARA.
    datos_faltantes = []
    if not estado_actual.get('nombre'): datos_faltantes.append("NOMBRE")
    if not estado_actual.get('servicio'): datos_faltantes.append("SERVICIO")
    if not (estado_actual.get('fecha_intencion') and estado_actual.get('hora_intencion')): datos_faltantes.append("FECHA Y HORA")

    instruccion_dinamica = ""

    if len(datos_faltantes) == 3:
        # 1. INICIO / NADA: Saludo Simple (Anti-Spam).
        instruccion_dinamica = """
        OBJETIVO: SALUDAR Y ORIENTAR.
        - Di: "¡Hola! 👋 Soy el asistente de Barbería Z. ¿Te gustaría ver los turnos disponibles para hoy o para mañana?"
        - NO muestres la lista de horarios todavía. Espera que el usuario elija.
        """
    elif len(datos_faltantes) > 0:
        # 2. PROCESO (Faltan datos): Pedir lo que falta.
        faltan_str = ", ".join(datos_faltantes)
        # COPY UX MEJORADO
        instruccion_dinamica = f"""
        OBJETIVO: COMPLETAR DATOS ({faltan_str}).
        - YA TENEMOS algunos datos (ver MEMORIA). NO LOS VUELVAS A PEDIR.
        - SOLO PREGUNTA por: {faltan_str}.
        - IMPORTANTE: NO vuelvas a mostrar la lista de horarios disponibles.
        - Si falta SERVICIO, di: "¡Dale! Para agendarte bien, contame qué te querés hacer: ¿Solo el corte, un retoque de barba, o el servicio completo (cejas incluidas)?"
        """
    else:
        # 3. COMPLETO: Confirmar.
        instruccion_dinamica = """
        OBJETIVO: CONFIRMAR CITA.
        - Tienes TODOS los datos.
        - Di: "Perfecto [Nombre], te anoto para el [Fecha] a las [Hora] hs entonces. ¿Te confirmo el turno?"
        - Si responde SÍ/CONFIRMO: Genera el código [CITA]...[/CITA].
        """

    system_prompt = f"""Eres el asistente virtual de {nombre_negocio}.

=== CONTEXTO TEMPORAL ===
HOY ES: {dia_semana} {fecha_hoy}, {hora_actual}

=== MEMORIA DE ESTA CHARLA (DATOS YA OBTENIDOS) ===
{contexto_memoria}
(¡NO pidas de nuevo lo que ya está aquí!)

=== DISPONIBILIDAD REAL (SOLO PUEDES OFRECER ESTO) ===
{estado_agenda}

=== INSTRUCCIONES DEL NEGOCIO ===
{instrucciones_negocio}
HORARIO OFICIAL: 08:00 AM a 20:00 PM.

=== OBJETIVO ACTUAL (PRIORIDAD MÁXIMA) ===
{instruccion_dinamica}

{alerta_conflicto if alerta_conflicto else ""}

=== REGLAS DE ORO (LÓGICA) ===
1. **INTERPRETACIÓN DE HORAS (CRÍTICO)**:
   - Si el usuario dice un número del 1 al 7, **ASUME QUE ES PM**. (Ej: "5" = 17:00, "2" = 14:00).
   - Si dice 8, 9, 10, 11, ASUME AM (mañana).
   - SIEMPRE usa formato 24h para verificar disponibilidad (ej: busca "17:00", no "5").

2. **VERIFICACIÓN ESTRICTA**: Antes de decir "no disponible", REVISA la lista 'DISPONIBILIDAD REAL'.
   - Si el usuario pide una hora (ej: "17:00" o "5") y aparece en la lista [DISPONIBLE], **DI QUE SÍ**.
   - Si NO está en la lista, di que no y ofrece las alternativas más cercanas.
   - NO alucines horarios ocupados si la lista dice que están libres.

3. **GESTIÓN DE MEMORIA**: Al final de CADA respuesta, incluye SIEMPRE:
   [MEMORIA]{{"nombre": "...", "fecha": "...", "hora": "...", "servicio": "..."}}[/MEMORIA]
   - Copia los datos de la MEMORIA anterior.
   - Agrega/Actualiza lo nuevo que diga el usuario.
   - "hora" debe ser en formato 24h (ej: 19:00).
   - REGLA DE ORO: Si la hora detectada es menor a 08:00 o mayor a 20:00, NO LA GUARDES en memoria (déjala vacía o null).

4. **CONFIRMACIÓN FINAL**:
   Solo si el usuario confirma explícitamente y tienes todo:
   [CITA]Nombre|Servicio|YYYY-MM-DD|HH:MM[/CITA]
"""

    mensajes = [{"role": "system", "content": system_prompt}]
    mensajes.extend(sesion['history'])
    
    for intento in range(len(GROQ_API_KEYS)):
        api_key = GROQ_API_KEYS[current_key_index]
        try:
            groq_client = Groq(api_key=api_key)
            chat_completion = groq_client.chat.completions.create(
                messages=mensajes,
                model="llama-3.1-8b-instant",
                max_tokens=300,
                temperature=0.5
            )
            respuesta = chat_completion.choices[0].message.content
            print(f"✅ GROQ respondió: {respuesta[:50]}...")

            # Guardar respuesta del bot en el historial (DB)
            db.agregar_mensaje(cliente, respuesta, es_bot=True)

            # Procesar Memoria Oculta
            nuevo_estado = procesar_memoria_ia(respuesta, sesion['state'])

            # GUARDAR ESTADO EN DB (PERSISTENCIA)
            db.save_session_state(cliente, nuevo_estado)
            
            # Limpiar bloque de memoria de la respuesta al usuario
            respuesta_visible = re.sub(r'\[MEMORIA\].*?\[/MEMORIA\]', '', respuesta, flags=re.DOTALL).strip()

            if '[CITA]' in respuesta_visible and '[/CITA]' in respuesta_visible:
                # Extraer datos de cita antes de limpiar
                datos_cita = procesar_cita(respuesta_visible, cliente)

                # BUGFIX: Limpieza de chat (Triple despedida)
                match_cita = re.search(r'\[CITA\](.+?)\[/CITA\]', respuesta_visible)

                if datos_cita:
                    # ÉXITO: Cita guardada
                    if match_cita:
                        try:
                            raw = match_cita.group(1).split('|')
                            c_nombre = raw[0].strip().title()
                            c_fecha = raw[2].strip()
                            c_hora = raw[3].strip()
                            respuesta_visible = f"¡LISTO {c_nombre}! ✅ Tu turno quedó confirmado para el {c_fecha} a las {c_hora} hs. Te esperamos en Barbería Z. ¡Nos vemos!"
                        except:
                            respuesta_visible = "¡LISTO! ✅ Tu turno quedó confirmado. ¡Te esperamos!"

                    # Reset estado tras confirmar
                    db.save_session_state(cliente, {})
                else:
                    # FALLO: procesar_cita devolvió None (Ocupado)
                    respuesta_visible = "⚠️ Lo siento, ese turno se acaba de ocupar hace unos segundos. 😅 Por favor elige otro horario."
                    # Mantenemos el estado para que el usuario pueda intentar otra hora inmediatamente
                    # (Quizás borramos solo la hora de la intención?)
                    if 'hora_intencion' in sesion['state']:
                        del sesion['state']['hora_intencion']
                        db.save_session_state(cliente, sesion['state'])

            return respuesta_visible
            
        except Exception as e:
            print(f"⚠️ GROQ Error: {str(e)}")
            current_key_index = (current_key_index + 1) % len(GROQ_API_KEYS)
    
    return "El sistema está ocupado."

def procesar_cita(respuesta, telefono):
    try:
        match = re.search(r'\[CITA\](.+?)\[/CITA\]', respuesta)
        if match:
            datos = match.group(1).split('|')
            if len(datos) >= 4:
                hora_raw = datos[3].strip()
                if len(hora_raw) == 4 and ':' in hora_raw:
                    hora_raw = "0" + hora_raw

                # Llamar a DB (Ahora retorna ID o None si falla)
                cita_id = db.agregar_cita(
                    fecha=datos[2].strip(),
                    hora=hora_raw,
                    cliente_nombre=datos[0].strip(),
                    telefono=telefono,
                    servicio=datos[1].strip()
                )

                if cita_id:
                    print(f"✅ CITA GUARDADA EN DB (ID: {cita_id})")
                    return datos # Retornar datos para uso en mensaje
                else:
                    print(f"🚫 FALLO AL GUARDAR CITA (Ocupado)")
                    return None
    except Exception as e:
        print(f"❌ Error DB: {e}")
    return None

# === WEBHOOK WASENDER (GENÉRICO) ===
@app.route("/wasender/webhook", methods=['POST'])
def wasender_webhook():
    try:
        # Intentar leer JSON
        data = request.json
        if not data:
            print("⚠️ Webhook vacío")
            return 'OK', 200

        print(f"📩 WEBHOOK RAW: {data}")
        
        # Lógica de parsing flexible
        mensaje = ""
        remitente = ""
        push_name = None
        
        # Caso 1: Estructura plana
        if 'message' in data and 'from' in data:
            mensaje = data['message']
            remitente = data['from']
        # Caso 2: Estructura WaSender
        elif 'data' in data and 'messages' in data['data']:
            msg_data = data['data']['messages'][0] if isinstance(data['data']['messages'], list) else data['data']['messages']

            # Extracción del mensaje
            mensaje = msg_data.get('messageBody')
            if not mensaje:
                 contenido_msg = msg_data.get('message', {})
                 mensaje = contenido_msg.get('conversation') or contenido_msg.get('extendedTextMessage', {}).get('text')

            # Extracción del remitente
            remitente = msg_data.get('remoteJid') or msg_data.get('key', {}).get('remoteJid')

            # Extracción del PushName (Nombre Perfil)
            push_name = msg_data.get('pushName')

        # Caso 3: Estructura anidada genérica (fallback)
        elif 'data' in data:
            mensaje = data['data'].get('message') or data['data'].get('body')
            remitente = data['data'].get('from') or data['data'].get('phone')

        if not mensaje or not remitente:
            print("⚠️ No se pudo extraer mensaje/remitente del JSON")
            return 'OK', 200

        # Limpiar remitente
        remitente = remitente.replace('@c.us', '').replace('+', '')
        
        # Procesar con IA
        db.agregar_mensaje(remitente, mensaje, es_bot=False)
        respuesta = generar_respuesta_ia(mensaje, remitente, push_name=push_name)
        
        if respuesta:
            exito = enviar_mensaje_wasender(remitente, respuesta)
        
        return 'OK', 200
        
    except Exception as e:
        print(f"❌ ERROR WEBHOOK: {str(e)}")
        return 'Error', 500

<<<<<<< HEAD
# === SERVIR FLUTTER WEB ===
@app.route('/')
def serve_flutter():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_flutter_files(path):
    if path.startswith('api/') or path.startswith('wasender/'):
        return jsonify({'error': 'Not found'}), 404
    try:
        return send_from_directory(app.static_folder, path)
    except:
        return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({'status': 'online', 'message': 'Bot WaSender Activo'})

=======
>>>>>>> b23a026260ad094a3226be3ee6bd56b737a0c5fa
@app.route('/api/stats', methods=['GET'])
def api_stats():
    config = db.get_all_config()
    return jsonify({
        'bot_encendido': config.get('bot_encendido', 'true') == 'true',
        'nombre_negocio': config.get('nombre_negocio', 'Barbería Z'),
        'total_citas': len(db.obtener_todas_las_citas()),
        'citas_hoy': db.contar_citas_hoy(),
        'mensajes_hoy': db.contar_mensajes_hoy()
    })

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        data = request.json
        for key, value in data.items():
            db.set_config(key, str(value))
        return jsonify({'success': True})
    return jsonify(db.get_all_config())

@app.route('/api/citas', methods=['GET', 'POST'])
def api_citas():
    if request.method == 'POST':
        data = request.json
        cita_id = db.agregar_cita(
            fecha=data.get('fecha'),
            hora=data.get('hora'),
            cliente_nombre=data.get('cliente_nombre', 'Cliente'),
            telefono=data.get('telefono', ''),
            servicio=data.get('servicio', 'Corte')
        )
        return jsonify({'success': True, 'id': cita_id})
    fecha = request.args.get('fecha', '')
    if fecha:
        citas = db.obtener_citas_por_fecha(fecha)
    else:
        citas = db.obtener_todas_las_citas()
    return jsonify(citas)

@app.route('/api/citas/<int:cita_id>', methods=['DELETE'])
def eliminar_cita_api(cita_id):
    db.eliminar_cita(cita_id)
    return jsonify({'success': True})

@app.route('/api/citas_hoy', methods=['GET'])
def citas_hoy():
    hoy = datetime.date.today().isoformat()
    return jsonify(db.obtener_citas_por_fecha(hoy))

@app.route('/api/toggle_bot', methods=['POST'])
def toggle_bot():
    data = request.json
    estado = 'true' if data.get('encendido', True) else 'false'
    db.set_config('bot_encendido', estado)
    return jsonify({'success': True, 'bot_encendido': estado == 'true'})

# === RUTA CATCH-ALL PARA FRONTEND (Debe ir al final) ===
@app.route('/')
def serve_root():
    print(f"🌐 Serving ROOT from {STATIC_FOLDER}")
    if os.path.exists(os.path.join(STATIC_FOLDER, 'index.html')):
        return send_from_directory(STATIC_FOLDER, 'index.html')
    else:
        # Debugging directory listing
        msg = f"❌ Error: index.html not found in {STATIC_FOLDER}\n"
        msg += f"📂 CWD: {os.getcwd()}\n"
        if os.path.exists(STATIC_FOLDER):
            msg += f"📂 Content of {STATIC_FOLDER}: {os.listdir(STATIC_FOLDER)}"
        else:
            msg += f"⚠️ Folder {STATIC_FOLDER} does not exist"
        return msg, 404

@app.route('/<path:path>')
def serve_static(path):
    print(f"📂 Requesting static file: {path}")
    if os.path.exists(os.path.join(STATIC_FOLDER, path)):
        return send_from_directory(STATIC_FOLDER, path)
    else:
        print(f"⚠️ File not found: {path} - Serving index.html (SPA Fallback)")
        return send_from_directory(STATIC_FOLDER, 'index.html')

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    index_path = os.path.join(app.static_folder, 'index.html')
    if os.path.exists(index_path):
        print(f"✅ build/web/index.html encontrado: {index_path}")
    else:
        print(f"❌ build/web/index.html NO encontrado: {index_path}")
    print(f"🟢 Bot WaSender iniciado en puerto {port}")

    # DEBUG CRÍTICO: Ver qué hay en el disco
    print("📂 CONTENIDO DE LA CARPETA ACTUAL:", os.listdir('.'))
    if os.path.exists('web'):
        print("📂 CONTENIDO DE CARPETA 'web':", os.listdir('web'))
    else:
        print("⚠️ CARPETA 'web' NO EXISTE")

    app.run(host='0.0.0.0', port=port, debug=False)
