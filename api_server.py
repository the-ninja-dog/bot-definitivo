# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import datetime
import re
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
    if not to.startswith('+'):
        to = '+' + to

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
    ahora = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    resumen = []
    for i in range(dias):
        fecha_obj = ahora + datetime.timedelta(days=i)
        fecha_str = fecha_obj.strftime('%Y-%m-%d')
        dia_semana = fecha_obj.weekday()
        if dia_semana == 6:
            resumen.append(f"{fecha_str} (DOMINGO): CERRADO. NO AGENDAR.")
            continue
        citas = db.obtener_citas_por_fecha(fecha_str)
        ocupadas = [c['hora'][:5] for c in citas]
        ocupadas.append("12:00 (ALMUERZO)")
        if ocupadas:
            resumen.append(f"{fecha_str}: Ocupado en {', '.join(ocupadas)}")
        else:
            resumen.append(f"{fecha_str}: Todo libre (Excepto 12:00 Almuerzo)")
    return "\n".join(resumen)

# === ANALIZADOR DE INTENCIÓN ===
def analizar_intencion(mensaje, estado_actual):
    mensaje = mensaje.lower()
    nuevo_estado = estado_actual.copy()
    match_nombre = re.search(r'(?:soy|me llamo|mi nombre es)\s+([a-zA-ZáéíóúÁÉÍÓÚ]+)', mensaje)
    if match_nombre:
        nuevo_estado['nombre'] = match_nombre.group(1).title()
    dias_semana = ['lunes', 'martes', 'miércoles', 'miercoles', 'jueves', 'viernes', 'sábado', 'sabado', 'domingo']
    for dia in dias_semana:
        if dia in mensaje:
            nuevo_estado['fecha_intencion'] = dia
    if 'hoy' in mensaje:
        nuevo_estado['fecha_intencion'] = 'HOY'
    if 'mañana' in mensaje or 'manana' in mensaje:
        nuevo_estado['fecha_intencion'] = 'MAÑANA'
    match_hora = re.search(r'(?:las|la)\s+(\d{1,2})', mensaje)
    if match_hora:
        hora = int(match_hora.group(1))
        if 1 <= hora <= 6:
            nuevo_estado['hora_intencion'] = f"{hora + 12}:00"
        else:
            nuevo_estado['hora_intencion'] = f"{hora}:00"
    servicios = []
    if 'corte' in mensaje or 'cabello' in mensaje or 'pelo' in mensaje:
        servicios.append('Corte')
    if 'barba' in mensaje:
        servicios.append('Barba')
    if 'cejas' in mensaje:
        servicios.append('Cejas')
    if servicios:
        prev_servicios = nuevo_estado.get('servicio', '')
        nuevo_str = " + ".join(servicios)
        if prev_servicios and prev_servicios != nuevo_str:
             if 'Corte' in prev_servicios and 'Barba' in servicios:
                 nuevo_estado['servicio'] = 'Corte + Barba'
             else:
                 nuevo_estado['servicio'] = nuevo_str
        else:
            nuevo_estado['servicio'] = nuevo_str
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
    instrucciones_negocio = config.get('instrucciones', 'Horario: 9am-8pm. Corte $10.')
    
    ahora = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    fecha_hoy = ahora.strftime('%Y-%m-%d')
    hora_actual = ahora.strftime('%H:%M')
    dia_semana_int = ahora.weekday()
    dia_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][dia_semana_int]

    sesion = obtener_sesion(cliente)
    sesion['state'] = analizar_intencion(mensaje, sesion['state'])
    estado_actual = sesion['state']
    estado_agenda = obtener_estado_agenda(5)

    contexto_memoria = ""
    if estado_actual.get('nombre'):
        contexto_memoria += f"- NOMBRE DETECTADO: {estado_actual['nombre']}\n"
    if estado_actual.get('fecha_intencion'):
        contexto_memoria += f"- FECHA SOLICITADA: {estado_actual['fecha_intencion']}\n"
    if estado_actual.get('hora_intencion'):
        contexto_memoria += f"- HORA SOLICITADA: {estado_actual['hora_intencion']}\n"
    if estado_actual.get('servicio'):
        contexto_memoria += f"- SERVICIO DETECTADO: {estado_actual['servicio']}\n"

    system_prompt = f"""Eres el asistente virtual de {nombre_negocio}.

=== CONTEXTO TEMPORAL ===
HOY ES: {dia_semana} {fecha_hoy}, {hora_actual}

=== MEMORIA DE ESTA CHARLA ===
{contexto_memoria}

=== ESTADO DE LA AGENDA (REALIDAD) ===
{estado_agenda}

=== INSTRUCCIONES DEL NEGOCIO ===
{instrucciones_negocio}

=== REGLAS DE ORO (LÓGICA BLINDADA) ===
1. OBJETIVO: Confirmar la cita en POCAS PREGUNTAS. Ahorra mensajes.
   - Pide Nombre, Servicio y Hora juntos si faltan.
2. SI ES DOMINGO HOY: Si piden "hoy", DI QUE NO. Ofrece mañana.
3. PRECIOS: Corte $10 | Barba $5 | Cejas $3 | Pack $12.
4. CONFIRMACIÓN FINAL:
   [CITA]Nombre|Servicio|YYYY-MM-DD|HH:MM[/CITA]

IMPORTANTE:
- Si en MEMORIA ya tienes datos, NO los preguntes de nuevo.
- NO preguntes método de pago.
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
            
            if '[CITA]' in respuesta and '[/CITA]' in respuesta:
                procesar_cita(respuesta, cliente)
                respuesta = re.sub(r'\[CITA\].*?\[/CITA\]', '', respuesta).strip()
                sesion['state'] = {}
                if not respuesta:
                    respuesta = "✅ ¡Listo! Tu cita ha sido agendada. ¡Te esperamos!"
            
            return respuesta
            
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
