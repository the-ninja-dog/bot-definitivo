# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from groq import Groq
import datetime
import re
from database import db
import os
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
# Filtrar keys vacías
GROQ_API_KEYS = [k for k in GROQ_API_KEYS if k]
current_key_index = 0

# === MEMORIA DE ESTADO (CONVERSACIÓN + INTENCIÓN) ===
# Estructura: {'telefono': {'history': [], 'state': {'nombre': None, 'fecha': None, 'hora': None}}}
sesiones = {}

def obtener_sesion(cliente):
    if cliente not in sesiones:
        sesiones[cliente] = {
            'history': [],
            'state': {} # Estado vacío
        }
    return sesiones[cliente]

def actualizar_historial(cliente, rol, mensaje):
    sesion = obtener_sesion(cliente)
    sesion['history'].append({"role": rol, "content": mensaje})
    if len(sesion['history']) > 20:
        sesion['history'] = sesion['history'][-20:]

# === HELPER DISPONIBILIDAD INTELIGENTE ===
def obtener_estado_agenda(dias=5):
    """Obtiene el estado de la agenda (Citas + Reglas de Negocio)"""
    ahora = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    resumen = []

    for i in range(dias):
        fecha_obj = ahora + datetime.timedelta(days=i)
        fecha_str = fecha_obj.strftime('%Y-%m-%d')
        dia_semana = fecha_obj.weekday() # 0=Lun, 6=Dom

        # Regla 1: Domingo CERRADO
        if dia_semana == 6:
            resumen.append(f"{fecha_str} (DOMINGO): CERRADO. NO AGENDAR.")
            continue

        # Obtener citas
        citas = db.obtener_citas_por_fecha(fecha_str)
        ocupadas = [c['hora'][:5] for c in citas] # Solo HH:MM

        # Regla 2: Almuerzo siempre ocupado
        ocupadas.append("12:00 (ALMUERZO)")

        if ocupadas:
            resumen.append(f"{fecha_str}: Ocupado en {', '.join(ocupadas)}")
        else:
            resumen.append(f"{fecha_str}: Todo libre (Excepto 12:00 Almuerzo)")

    return "\n".join(resumen)

# === ANALIZADOR DE INTENCIÓN (REGEX) ===
def analizar_intencion(mensaje, estado_actual):
    """Analiza el mensaje y extrae datos clave para mantener el estado"""
    mensaje = mensaje.lower()
    nuevo_estado = estado_actual.copy()

    # 1. Detectar Nombre ("soy x", "me llamo x")
    match_nombre = re.search(r'(?:soy|me llamo|mi nombre es)\s+([a-zA-ZáéíóúÁÉÍÓÚ]+)', mensaje)
    if match_nombre:
        nuevo_estado['nombre'] = match_nombre.group(1).title()

    # 2. Detectar Fecha ("lunes", "mañana", "hoy")
    dias_semana = ['lunes', 'martes', 'miércoles', 'miercoles', 'jueves', 'viernes', 'sábado', 'sabado', 'domingo']
    for dia in dias_semana:
        if dia in mensaje:
            nuevo_estado['fecha_intencion'] = dia

    if 'hoy' in mensaje:
        nuevo_estado['fecha_intencion'] = 'HOY'
    if 'mañana' in mensaje or 'manana' in mensaje:
        nuevo_estado['fecha_intencion'] = 'MAÑANA'

    # 3. Detectar Hora Simple ("las 5", "a las 4")
    match_hora = re.search(r'(?:las|la)\s+(\d{1,2})', mensaje)
    if match_hora:
        hora = int(match_hora.group(1))
        # Lógica Smart Time (1-6 -> PM)
        if 1 <= hora <= 6:
            nuevo_estado['hora_intencion'] = f"{hora + 12}:00"
        else:
            nuevo_estado['hora_intencion'] = f"{hora}:00"

    return nuevo_estado

# === BOT CON GROQ (ROTACIÓN DE KEYS) ===
def generar_respuesta_ia(mensaje, cliente):
    global current_key_index
    
    # Verificar si el bot está encendido
    bot_encendido = db.get_config('bot_encendido', 'true')
    if bot_encendido != 'true':
        print("🔴 Bot está APAGADO")
        return None
    
    if not GROQ_API_KEYS:
        print("❌ No hay GROQ_API_KEY configurada")
        return "Error: Sistema no configurado."
    
    # Configuración del negocio
    config = db.get_all_config()
    nombre_negocio = config.get('nombre_negocio', 'Barbería Z')
    instrucciones_negocio = config.get('instrucciones', 'Horario: 9am-8pm. Corte $10.')
    
    # Contexto Temporal
    ahora = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    fecha_hoy = ahora.strftime('%Y-%m-%d')
    hora_actual = ahora.strftime('%H:%M')
    dia_semana_int = ahora.weekday()
    dia_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][dia_semana_int]

    # Obtener estado de la sesión y agenda
    sesion = obtener_sesion(cliente)

    # Analizar y Actualizar Estado (Memoria a Corto Plazo)
    sesion['state'] = analizar_intencion(mensaje, sesion['state'])
    estado_actual = sesion['state']

    estado_agenda = obtener_estado_agenda(5)

    # Construir "Memoria Explícita" para el Prompt
    contexto_memoria = ""
    if estado_actual.get('nombre'):
        contexto_memoria += f"- NOMBRE DETECTADO: {estado_actual['nombre']}\n"
    if estado_actual.get('fecha_intencion'):
        contexto_memoria += f"- FECHA SOLICITADA: {estado_actual['fecha_intencion']}\n"
    if estado_actual.get('hora_intencion'):
        contexto_memoria += f"- HORA SOLICITADA: {estado_actual['hora_intencion']}\n"

    # === SISTEMA PROMPT ===
    system_prompt = f"""Eres el asistente virtual de {nombre_negocio}.

=== CONTEXTO TEMPORAL ===
HOY ES: {dia_semana} {fecha_hoy}, {hora_actual}

=== MEMORIA DE ESTA CHARLA (LO QUE YA SABEMOS) ===
{contexto_memoria}
(Usa estos datos. NO preguntes lo que ya está aquí).

=== ESTADO DE LA AGENDA (REALIDAD) ===
{estado_agenda}

=== INSTRUCCIONES DEL NEGOCIO ===
{instrucciones_negocio}

=== REGLAS DE ORO (LÓGICA BLINDADA) ===
1. SI ES DOMINGO HOY ({dia_semana}):
   - Si piden "hoy", DI QUE NO. Está cerrado.
   - Si piden "mañana" (Lunes), DI QUE SÍ (si hay lugar).
   - NO confundas "mañana" con "hoy".

2. PRECIOS Y SERVICIOS:
   - Corte $10 | Barba $5 | Cejas $3 | Pack (Corte+Barba) $12.

3. FLUJO DE CIERRE (CRÍTICO):
   - Si el usuario dice "Sí", "Dale", "Confirmo": CONFIRMA LA CITA con los datos que ya tienes en MEMORIA.
   - Si agrega un servicio extra (upsell), MANTÉN la hora y fecha ya acordada.

4. AL CONFIRMAR:
   - Solo escribe [CITA]... si tienes Nombre, Servicio, Fecha y Hora.
   - Formato: [CITA]Nombre|Servicio|YYYY-MM-DD|HH:MM[/CITA]

IMPORTANTE:
- Si en MEMORIA dice NOMBRE DETECTADO, úsalo ("Hola Fernando").
- Si en MEMORIA dice HORA SOLICITADA, asume que esa es la hora, no preguntes "¿a qué hora?".
"""

    # Actualizar historial
    actualizar_historial(cliente, "user", mensaje)
    
    # Construir mensajes
    mensajes = [{"role": "system", "content": system_prompt}]
    mensajes.extend(sesion['history'])
    
    # Intentar con cada API key
    for intento in range(len(GROQ_API_KEYS)):
        api_key = GROQ_API_KEYS[current_key_index]
        try:
            groq_client = Groq(api_key=api_key)
            
            chat_completion = groq_client.chat.completions.create(
                messages=mensajes,
                model="llama-3.1-8b-instant",
                max_tokens=350,
                temperature=0.6 # Bajamos temperatura para ser más precisos
            )
            
            respuesta = chat_completion.choices[0].message.content
            print(f"✅ GROQ[{current_key_index}] respondió: {respuesta[:80]}...")
            
            # Agregar al historial
            actualizar_historial(cliente, "assistant", respuesta)
            
            # Procesar cita si existe
            if '[CITA]' in respuesta and '[/CITA]' in respuesta:
                procesar_cita(respuesta, cliente)
                respuesta = re.sub(r'\[CITA\].*?\[/CITA\]', '', respuesta).strip()
                # Limpiar estado tras confirmar (Opcional, pero bueno para nueva cita)
                sesion['state'] = {}
                if not respuesta:
                    respuesta = "✅ ¡Listo! Tu cita ha sido agendada. ¡Te esperamos!"
            
            return respuesta
            
        except Exception as e:
            print(f"⚠️ GROQ[{current_key_index}] falló: {str(e)[:80]}")
            current_key_index = (current_key_index + 1) % len(GROQ_API_KEYS)
    
    print("❌ Todas las API keys fallaron")
    return "El sistema está ocupado. Intenta en un momento."

def procesar_cita(respuesta, telefono):
    try:
        match = re.search(r'\[CITA\](.+?)\[/CITA\]', respuesta)
        if match:
            datos = match.group(1).split('|')
            if len(datos) >= 4:
                # Normalizar hora
                hora_raw = datos[3].strip()
                if len(hora_raw) == 4 and ':' in hora_raw: # h:mm -> 0h:mm
                    hora_raw = "0" + hora_raw

                # Normalizar fecha (Intentar arreglar si el LLM manda "Lunes" en vez de YYYY-MM-DD)
                fecha_raw = datos[2].strip()
                # (Aquí podríamos agregar lógica extra si el LLM falla, pero confiamos en el prompt por ahora)

                db.agregar_cita(
                    fecha=fecha_raw,
                    hora=hora_raw,
                    cliente_nombre=datos[0].strip(),
                    telefono=telefono,
                    servicio=datos[1].strip()
                )
                print(f"✅ CITA GUARDADA: {datos[0]} - {datos[2]} {datos[3]}")
    except Exception as e:
        print(f"❌ Error guardando cita: {e}")

# === WEBHOOK WHATSAPP ===
@app.route("/whatsapp/inbound", methods=['POST'])
def whatsapp_webhook():
    try:
        msg = request.values.get('Body', '').strip()
        sender = request.values.get('From', '')
        
        if not sender or not msg:
            return '', 200
        
        print(f"📩 MENSAJE de {sender}: {msg}")
        
        cliente = sender.replace('whatsapp:', '')
        db.agregar_mensaje(cliente, msg, es_bot=False)
        
        respuesta = generar_respuesta_ia(msg, cliente)
        
        if respuesta is None:
            return '', 200
        
        db.agregar_mensaje(cliente, respuesta, es_bot=True)
        
        resp = MessagingResponse()
        resp.message(respuesta)
        return str(resp), 200, {'Content-Type': 'application/xml'}
        
    except Exception as e:
        print(f"❌ ERROR WEBHOOK: {str(e)}")
        return '', 500

# === RUTAS API RESTAURADAS ===
@app.route('/', methods=['GET'])
def home():
    return jsonify({'status': 'online', 'message': 'Bot de Barbería activo'})

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
    print(f"🟢 Bot iniciado en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
