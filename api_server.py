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

# === MEMORIA DE CONVERSACIONES ===
conversaciones = {}

def obtener_historial(cliente):
    if cliente not in conversaciones:
        conversaciones[cliente] = []
    return conversaciones[cliente]

def agregar_al_historial(cliente, rol, mensaje):
    if cliente not in conversaciones:
        conversaciones[cliente] = []
    conversaciones[cliente].append({"role": rol, "content": mensaje})
    if len(conversaciones[cliente]) > 20:
        conversaciones[cliente] = conversaciones[cliente][-20:]

# === HELPER DISPONIBILIDAD ===
def obtener_citas_proximos_dias(dias=3):
    """Obtiene una lista de citas ocupadas para hoy y los próximos días"""
    ahora = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    resumen = []

    for i in range(dias):
        fecha = (ahora + datetime.timedelta(days=i)).strftime('%Y-%m-%d')
        citas = db.obtener_citas_por_fecha(fecha)
        if citas:
            horas_ocupadas = [c['hora'][:5] for c in citas] # Solo HH:MM
            resumen.append(f"{fecha}: {', '.join(horas_ocupadas)}")

    return "\n".join(resumen) if resumen else "Ninguna (Todo disponible)"

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
    instrucciones = config.get('instrucciones', 'Horario: 9am-8pm. Corte $10.')
    
    # Fecha actual (zona horaria -4)
    ahora = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    fecha_hoy = ahora.strftime('%Y-%m-%d')
    hora_actual = ahora.strftime('%H:%M')
    dia_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][ahora.weekday()]
    
    # Obtener disponibilidad real
    citas_ocupadas = obtener_citas_proximos_dias(4)

    system_prompt = f"""Eres el asistente virtual AMIGABLE y PROFESIONAL de {nombre_negocio}.

FECHA Y HORA ACTUAL: {dia_semana} {fecha_hoy}, {hora_actual}

HORARIOS OCUPADOS (YA ESTÁN TOMADOS, NO AGENDAR AQUÍ):
{citas_ocupadas}

HORARIO COMERCIAL:
- Lunes a Sábado: 09:00 a 20:00 (Último turno 19:00)
- Domingo: CERRADO
- ALMUERZO: 12:00 a 13:00 (El local cierra, no hay citas a las 12:00, reanuda a las 13:00)

PERSONALIDAD Y TONO:
- Sé amable, servicial y casual, pero educado. (Ej: "¡Hola crack!", "¿Qué tal todo?", "Claro que sí").
- NO hables como un robot (Evita "Somos abiertos", usa "Estamos abiertos" o "Atendemos de...").
- NO vuelvas a preguntar el nombre si ya te lo dijeron. Revisa el historial.
- Si el usuario saluda, responde con energía y pregunta qué necesita.

REGLAS DE INTELIGENCIA DE FECHA/HORA:
1. Si el usuario dice un número solo como "4", "3", "5", ASUME QUE ES DE LA TARDE (PM). (Ej: "4" = 16:00).
2. Si el usuario dice "1", asume 13:00.
3. Si dice "Hoy a las 3", significa HOY a las 15:00.
4. NO agendar a las 12:00 (Almuerzo).
5. NO agendar Domingos.
6. SIEMPRE verifica la lista de "HORARIOS OCUPADOS" antes de decir que sí.

TU MISIÓN (FLUJO):
1. Si no sabes el nombre, pregúntalo amablemente.
2. Pregunta el servicio (Corte, Barba, Cejas).
3. Acuerda el día y la hora (ofrece opciones si está lleno).
4. CONFIRMA la cita.

FORMATO FINAL PARA GUARDAR CITA:
Solo cuando el cliente confirme fecha y hora, escribe al final de tu mensaje:
[CITA]Nombre|Servicio|YYYY-MM-DD|HH:MM[/CITA]
Ejemplo: [CITA]Juan|Corte|2025-12-11|15:00[/CITA]

IMPORTANTE:
- Sé breve.
- Si ya saludaste, ve al grano.
- Si el cliente dice "Hola soy Juan", NO preguntes "¿Cuál es tu nombre?". Di "¡Hola Juan! ¿En qué te ayudo hoy?".
"""

    # Obtener historial y agregar mensaje actual
    historial = obtener_historial(cliente)
    agregar_al_historial(cliente, "user", mensaje)
    
    # Construir mensajes
    mensajes = [{"role": "system", "content": system_prompt}]
    mensajes.extend(historial)
    
    # Intentar con cada API key
    for intento in range(len(GROQ_API_KEYS)):
        api_key = GROQ_API_KEYS[current_key_index]
        try:
            groq_client = Groq(api_key=api_key)
            
            chat_completion = groq_client.chat.completions.create(
                messages=mensajes,
                model="llama-3.1-8b-instant",
                max_tokens=300,
                temperature=0.7
            )
            
            respuesta = chat_completion.choices[0].message.content
            print(f"✅ GROQ[{current_key_index}] respondió: {respuesta[:80]}...")
            
            # Agregar al historial
            agregar_al_historial(cliente, "assistant", respuesta)
            
            # Procesar cita si existe
            if '[CITA]' in respuesta and '[/CITA]' in respuesta:
                procesar_cita(respuesta, cliente)
                respuesta = re.sub(r'\[CITA\].*?\[/CITA\]', '', respuesta).strip()
                if not respuesta:
                    respuesta = "✅ ¡Listo! Tu cita ha sido agendada. ¡Te esperamos!"
            
            return respuesta
            
        except Exception as e:
            print(f"⚠️ GROQ[{current_key_index}] falló: {str(e)[:80]}")
            # Rotar a la siguiente key
            current_key_index = (current_key_index + 1) % len(GROQ_API_KEYS)
    
    print("❌ Todas las API keys fallaron")
    return "El sistema está ocupado. Intenta en un momento."

def procesar_cita(respuesta, telefono):
    try:
        match = re.search(r'\[CITA\](.+?)\[/CITA\]', respuesta)
        if match:
            datos = match.group(1).split('|')
            if len(datos) >= 4:
                # Normalizar hora si es necesario (ej: 4:00 -> 04:00, 16:00 -> 16:00)
                hora_raw = datos[3].strip()
                if len(hora_raw) == 4 and ':' in hora_raw: # h:mm
                    hora_raw = "0" + hora_raw

                db.agregar_cita(
                    fecha=datos[2].strip(),
                    hora=hora_raw,
                    cliente_nombre=datos[0].strip(),
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
        sender = request.values.get('From', '')  # whatsapp:+595...
        
        if not sender or not msg:
            print("⚠️ Mensaje vacío o sin remitente")
            return '', 200
        
        print(f"📩 MENSAJE de {sender}: {msg}")
        
        # Guardar mensaje
        cliente = sender.replace('whatsapp:', '')
        db.agregar_mensaje(cliente, msg, es_bot=False)
        
        # Generar respuesta
        respuesta = generar_respuesta_ia(msg, cliente)
        
        if respuesta is None:
            print("🔴 Bot apagado")
            return '', 200
        
        # Guardar respuesta
        db.agregar_mensaje(cliente, respuesta, es_bot=True)
        
        # Responder con TwiML (método estándar)
        print(f"📤 ENVIANDO: {respuesta[:80]}...")
        resp = MessagingResponse()
        resp.message(respuesta)
        return str(resp), 200, {'Content-Type': 'application/xml'}
        
    except Exception as e:
        print(f"❌ ERROR WEBHOOK: {str(e)}")
        return '', 500
        
    except Exception as e:
        print(f"❌ ERROR WEBHOOK: {str(e)}")
        return '', 500

# === RUTAS API ===
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
