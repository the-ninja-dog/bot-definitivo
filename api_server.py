# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
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

app = Flask(__name__)
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
sesiones = {}

def obtener_sesion(cliente):
    if cliente not in sesiones:
        sesiones[cliente] = {
            'history': [],
            'state': {}
        }
    return sesiones[cliente]

def actualizar_historial(cliente, rol, mensaje):
    sesion = obtener_sesion(cliente)
    sesion['history'].append({"role": rol, "content": mensaje})
    if len(sesion['history']) > 20:
        sesion['history'] = sesion['history'][-20:]

# === HELPER DISPONIBILIDAD INTELIGENTE ===
def obtener_estado_agenda(dias=5):
    # Usar timezone UTC para evitar deprecation warning, luego restar 4 horas
    ahora = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)
    resumen = []

    # Horas posibles de 09:00 a 19:00 (Cierre 20:00)
    # Excluyendo almuerzo 12:00
    horas_totales = [f"{h:02d}:00" for h in range(9, 20) if h != 12]

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
            resumen.append(f"   ✅ Turnos libres: {', '.join(disponibles)}")
        else:
            resumen.append("   ❌ COMPLETO (Sin turnos)")

    return "\n".join(resumen)

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

            # Actualizar campos si no están vacíos
            if datos.get('nombre'): nuevo_estado['nombre'] = datos['nombre']
            if datos.get('fecha'): nuevo_estado['fecha_intencion'] = datos['fecha']
            if datos.get('servicio'): nuevo_estado['servicio'] = datos['servicio']

            # Lógica de corrección de HORA (12h -> 24h)
            if datos.get('hora'):
                hora_raw = str(datos['hora']).replace(':', '').strip()
                # Si es un número pequeño (1-8), asumir PM
                if hora_raw.isdigit():
                    h_int = int(hora_raw)
                    if 1 <= h_int <= 8:
                        nuevo_estado['hora_intencion'] = f"{h_int + 12}:00"
                    elif h_int <= 24: # Caso normal
                        nuevo_estado['hora_intencion'] = datos['hora']
                # Caso "05:00" o "5:00"
                elif ':' in datos['hora']:
                    parts = datos['hora'].split(':')
                    try:
                        h_int = int(parts[0])
                        if 1 <= h_int <= 8:
                            nuevo_estado['hora_intencion'] = f"{h_int + 12}:{parts[1]}"
                        else:
                            nuevo_estado['hora_intencion'] = datos['hora']
                    except:
                        nuevo_estado['hora_intencion'] = datos['hora']
                else:
                    nuevo_estado['hora_intencion'] = datos['hora']

            print(f"🧠 MEMORIA ACTUALIZADA: {nuevo_estado}")
    except Exception as e:
        print(f"⚠️ Error procesando memoria IA: {e}")

    return nuevo_estado

# === BOT LOGIC ===
def generar_respuesta_ia(mensaje, cliente):
    global current_key_index
    
    bot_encendido = db.get_config('bot_encendido', 'true')
    if bot_encendido != 'true':
        return None
    
    if not GROQ_API_KEYS:
        return "Error: Sistema no configurado."
    
    config = db.get_all_config()
    nombre_negocio = config.get('nombre_negocio', 'Barbería Z')
    instrucciones_negocio = config.get('instrucciones', 'Horario: 9am-6pm. Corte $10.')
    
    # Cálculo robusto de fecha/hora (UTC-4)
    ahora = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)
    fecha_hoy = ahora.strftime('%Y-%m-%d')
    hora_actual = ahora.strftime('%H:%M')
    dia_semana_int = ahora.weekday()
    dia_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][dia_semana_int]

    print(f"🕒 SERVER TIME (UTC-4): {fecha_hoy} {hora_actual} ({dia_semana})")

    sesion = obtener_sesion(cliente)
    # Ya no usamos regex, usamos la memoria del turno anterior
    estado_actual = sesion['state']
    estado_agenda = obtener_estado_agenda(5)

    contexto_memoria = ""
    if estado_actual.get('nombre'):
        contexto_memoria += f"- NOMBRE: {estado_actual['nombre']}\n"
    if estado_actual.get('fecha_intencion'):
        contexto_memoria += f"- FECHA: {estado_actual['fecha_intencion']}\n"
    if estado_actual.get('hora_intencion'):
        contexto_memoria += f"- HORA: {estado_actual['hora_intencion']}\n"
    if estado_actual.get('servicio'):
        contexto_memoria += f"- SERVICIO: {estado_actual['servicio']}\n"

    system_prompt = f"""Eres el asistente virtual de {nombre_negocio}.

=== CONTEXTO TEMPORAL ===
HOY ES: {dia_semana} {fecha_hoy}, {hora_actual}

=== MEMORIA DE ESTA CHARLA (NO PREGUNTES DE NUEVO ESTOS DATOS) ===
{contexto_memoria}

=== DISPONIBILIDAD REAL (TURNOS LIBRES) ===
{estado_agenda}

=== INSTRUCCIONES DEL NEGOCIO ===
{instrucciones_negocio}

=== TAREA CRÍTICA: GESTIÓN DE MEMORIA OBLIGATORIA ===
Al final de CADA respuesta, DEBES incluir un bloque JSON oculto con los datos que detectes del usuario.
Formato: [MEMORIA]{{"nombre": "...", "fecha": "...", "hora": "...", "servicio": "..."}}[/MEMORIA]
- Si detectas un dato nuevo, agrégalo.
- Si el usuario corrige un dato, actualízalo.
- Mantén los datos anteriores si no cambian.
- Si no detectas nada nuevo, repite lo que ya sabes.
- "hora" debe ser en formato 24h (ej: 19:00). Si dicen "7" y es tarde, es 19:00.

=== FLUJO DE CONVERSACIÓN (NATURAL) ===
1. **SI FALTA INFORMACIÓN**:
   - Saluda y menciona los turnos disponibles SOLO si es el inicio de la charla o si preguntan disponibilidad.
   - Si ya estamos hablando de un horario específico (ej: "quiero a las 19"), **NO REPITAS LA LISTA DE TURNOS**. Simplemente confirma si ese horario está libre y pide lo que falta (Nombre o Servicio).
   - Sé directo: "¿Cómo te llamas?" o "¿Qué servicio necesitas?".

2. **SI TENEMOS TODO (Nombre, Hora/Fecha, Servicio)**:
   - **DETENTE**. No ofrezcas más horarios.
   - Muestra un resumen final claro: "Perfecto {{Nombre}}, ¿te agendo el {{Servicio}} a las {{Hora}}?"
   - Pide confirmación (Sí/No).

3. **CONFIRMACIÓN FINAL**:
   - Si el usuario dice "SÍ" o "CONFIRMO" y YA TIENES los 3 datos:
   - **NO** preguntes nada más.
   - Genera INMEDIATAMENTE: [CITA]Nombre|Servicio|YYYY-MM-DD|HH:MM[/CITA]
"""

    actualizar_historial(cliente, "user", mensaje)
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
            
            actualizar_historial(cliente, "assistant", respuesta)
            
            # Procesar Memoria Oculta
            nuevo_estado = procesar_memoria_ia(respuesta, sesion['state'])
            sesion['state'] = nuevo_estado
            
            # Limpiar bloque de memoria de la respuesta al usuario
            respuesta_visible = re.sub(r'\[MEMORIA\].*?\[/MEMORIA\]', '', respuesta, flags=re.DOTALL).strip()

            if '[CITA]' in respuesta_visible and '[/CITA]' in respuesta_visible:
                procesar_cita(respuesta_visible, cliente)
                respuesta_visible = re.sub(r'\[CITA\].*?\[/CITA\]', '', respuesta_visible).strip()
                sesion['state'] = {} # Reset estado tras confirmar
                if not respuesta_visible:
                    respuesta_visible = "✅ ¡Listo! Tu cita ha sido agendada. ¡Te esperamos!"

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
                db.agregar_cita(
                    fecha=datos[2].strip(),
                    hora=hora_raw,
                    cliente_nombre=datos[0].strip(),
                    telefono=telefono,
                    servicio=datos[1].strip()
                )
                print(f"✅ CITA GUARDADA EN DB")
    except Exception as e:
        print(f"❌ Error DB: {e}")

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
        
        # Lógica de parsing flexible (Adaptar según llegue el JSON real)
        # Asumimos estructura común: {'data': {'message': '...', 'from': '...'}} o directa
        mensaje = ""
        remitente = ""
        
        # Caso 1: Estructura plana
        if 'message' in data and 'from' in data:
            mensaje = data['message']
            remitente = data['from']
        # Caso 2: Estructura WaSender (según logs recientes)
        elif 'data' in data and 'messages' in data['data']:
            msg_data = data['data']['messages'][0] if isinstance(data['data']['messages'], list) else data['data']['messages']

            # Extracción del mensaje (Prioridad: messageBody -> conversation -> text)
            mensaje = msg_data.get('messageBody')
            if not mensaje:
                 contenido_msg = msg_data.get('message', {})
                 mensaje = contenido_msg.get('conversation') or contenido_msg.get('extendedTextMessage', {}).get('text')

            # Extracción del remitente
            remitente = msg_data.get('remoteJid') or msg_data.get('key', {}).get('remoteJid')

        # Caso 3: Estructura anidada genérica (fallback)
        elif 'data' in data:
            mensaje = data['data'].get('message') or data['data'].get('body')
            remitente = data['data'].get('from') or data['data'].get('phone')

        if not mensaje or not remitente:
            print("⚠️ No se pudo extraer mensaje/remitente del JSON")
            return 'OK', 200

        # Limpiar remitente (quitar @c.us si existe)
        remitente = remitente.replace('@c.us', '').replace('+', '')
        
        # Procesar con IA
        db.agregar_mensaje(remitente, mensaje, es_bot=False)
        respuesta = generar_respuesta_ia(mensaje, remitente)
        
        if respuesta:
            # ENVIAR RESPUESTA VÍA API WASENDER
            exito = enviar_mensaje_wasender(remitente, respuesta)
            if exito:
                db.agregar_mensaje(remitente, respuesta, es_bot=True)
        
        return 'OK', 200
        
    except Exception as e:
        print(f"❌ ERROR WEBHOOK: {str(e)}")
        return 'Error', 500

# === RUTAS API FRONTEND (MANTENIDAS) ===
@app.route('/', methods=['GET'])
def home():
    return jsonify({'status': 'online', 'message': 'Bot WaSender Activo'})

# [Resto de rutas /api/stats, /api/citas se mantienen igual que antes]
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

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print(f"🟢 Bot WaSender iniciado en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
