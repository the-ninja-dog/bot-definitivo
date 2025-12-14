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

# === HELPER DISPONIBILIDAD INTELIGENTE ===
def obtener_estado_agenda(dias=3):
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
    # Obtenemos las instrucciones personalizadas de la DB
    instrucciones_negocio = config.get('instrucciones', 'Horario: 9am-8pm. Corte $10.')
    
    # Fecha actual (zona horaria -4)
    ahora = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    fecha_hoy = ahora.strftime('%Y-%m-%d')
    hora_actual = ahora.strftime('%H:%M')
    dia_semana_int = ahora.weekday()
    dia_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][dia_semana_int]

    # Obtener disponibilidad real e inteligente
    estado_agenda = obtener_estado_agenda(5) # Mirar 5 días adelante

    # === SISTEMA PROMPT ===
    system_prompt = f"""Eres el asistente virtual de {nombre_negocio}.

FECHA Y HORA ACTUAL: {dia_semana} {fecha_hoy}, {hora_actual}

ESTADO DE LA AGENDA (DISPONIBILIDAD REAL):
{estado_agenda}

=== INSTRUCCIONES DEL NEGOCIO (PERSONALIDAD) ===
{instrucciones_negocio}

=== REGLAS DE ORO (NO ROMPER) ===
1. REVISA "ESTADO DE LA AGENDA" ARRIBA.
   - Si dice "CERRADO", dile al cliente amablemente que no se puede y ofrece el siguiente día libre.
   - Si el horario pedido está en la lista de "Ocupado", ofrece otro.
2. FECHAS RELATIVAS:
   - Si dicen "este martes", busca el martes de esta semana en base a la FECHA ACTUAL.
   - Si dicen "próximo martes", suma 7 días.
3. ALMUERZO: 12:00 a 13:00 siempre cerrado.

=== FLUJO DE CONVERSACIÓN (MEMORIA) ===
1. EXTRAER NOMBRE: Busca en todo el historial. Si el usuario dijo "Soy Fernando" o "Me llamo Fernando", EL NOMBRE ES FERNANDO.
   - NUNCA uses "Nombre" o "Cliente" como placeholder.
   - Si no encuentras el nombre, pregúntalo.
2. MODIFICACIONES (CRÍTICO):
   - Si ya acordaste una hora y el usuario agrega algo (ej: "y cejas también"), MANTÉN LA HORA ACORDADA.
   - No preguntes "¿A qué hora?" de nuevo. Solo confirma el nuevo servicio en la misma hora.
3. CONFIRMACIÓN FINAL: Solo cuando tengas Día + Hora + Servicio + Nombre, escribe:
   [CITA]Nombre|Servicio|YYYY-MM-DD|HH:MM[/CITA]

IMPORTANTE:
- Sé inteligente. Si es Domingo, di "Hoy domingo descansamos, crack. ¿Te anoto para mañana lunes?".
- Si dicen "Las 5", es 17:00.
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
                    telefono=telefono,  # <-- FIX: Pasamos el teléfono
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
