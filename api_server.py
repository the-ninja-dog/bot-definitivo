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
    instrucciones = config.get('instrucciones', 'Horario: 9am-6pm. Corte $10.')
    
    # Fecha actual (zona horaria -4)
    ahora = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    fecha_hoy = ahora.strftime('%Y-%m-%d')
    hora_actual = ahora.strftime('%H:%M')
    dia_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][ahora.weekday()]
    
    system_prompt = f"""Eres el asistente virtual de {nombre_negocio}.

FECHA Y HORA ACTUAL: {dia_semana} {fecha_hoy}, {hora_actual}

INSTRUCCIONES DEL NEGOCIO:
{instrucciones}

TU TRABAJO ES AGENDAR CITAS:
1. Si el cliente saluda, responde breve y pregunta en qué puedes ayudar
2. Si quiere cita, pregunta su nombre
3. Luego pregunta qué servicio (corte, barba, cejas)
4. Luego pregunta día y hora
5. Cuando tengas TODO, confirma la cita

REGLAS:
- NO saludes de nuevo si ya saludaste
- RECUERDA lo que el cliente ya dijo
- Sé breve (2-3 oraciones máximo)
- Si no sabes algo, di que llamen al negocio

Cuando confirmes una cita, agrega al final:
[CITA]nombre|servicio|fecha|hora[/CITA]
Ejemplo: [CITA]Juan|Corte|2025-12-11|15:00[/CITA]"""

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
                db.agregar_cita(
                    fecha=datos[2].strip(),
                    hora=datos[3].strip(),
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
