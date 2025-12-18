import csv
import os
import datetime

FILE_AGENDA = "agenda_citas.csv"

# Horarios de trabajo (9am - 8pm)
HORA_INICIO = 9
HORA_FIN = 20

def inicializar_agenda():
    """Crea el archivo Excel/CSV si no existe"""
    if not os.path.exists(FILE_AGENDA):
        with open(FILE_AGENDA, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["Fecha", "Hora", "Cliente", "Telefono", "Estado"])

def leer_todas_las_citas():
    """Lee todas las citas del CSV y las devuelve como lista de diccionarios"""
    citas = []
    if not os.path.exists(FILE_AGENDA):
        return citas
        
    try:
        with open(FILE_AGENDA, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                citas.append(row)
    except Exception as e:
        print(f"[ERROR LEYENDO AGENDA] {e}")
        
    return citas

def guardar_todas_las_citas(citas):
    """Sobrescribe el CSV con la lista actualizada"""
    try:
        with open(FILE_AGENDA, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["Fecha", "Hora", "Cliente", "Telefono", "Estado"])
            for cita in citas:
                writer.writerow([cita["Fecha"], cita["Hora"], cita["Cliente"], cita["Telefono"], cita["Estado"]])
        return True
    except Exception as e:
        print(f"[ERROR GUARDANDO AGENDA] {e}")
        return False

def obtener_citas_dia(fecha_str):
    """Devuelve lista de horas ocupadas para una fecha"""
    citas = leer_todas_las_citas()
    ocupadas = []
    for c in citas:
        if c["Fecha"] == fecha_str and c["Estado"] == "Confirmado":
            ocupadas.append(c["Hora"])
    return ocupadas

def obtener_horarios_disponibles(fecha_str):
    """Devuelve lista de horarios libres"""
    ocupadas = obtener_citas_dia(fecha_str)
    disponibles = []
    
    for h in range(HORA_INICIO, HORA_FIN + 1):
        hora_formato = f"{h:02d}:00"
        if hora_formato not in ocupadas:
            disponibles.append(hora_formato)
            
    return disponibles

def agendar_cita(fecha, hora, cliente, telefono):
    """
    Guarda la cita. 
    Si el cliente YA tiene cita ese día, la actualiza (reprogramación).
    Si el horario está ocupado por OTRO, da error.
    """
    inicializar_agenda()
    citas = leer_todas_las_citas()
    
    # 1. Verificar si el horario está ocupado por ALGUIEN MÁS
    for c in citas:
        if c["Fecha"] == fecha and c["Hora"] == hora and c["Estado"] == "Confirmado":
            # Si es el mismo cliente, no pasa nada (es confirmar lo mismo)
            # Pero si es otro, error.
            if c["Cliente"].lower() != cliente.lower():
                return False, f"El horario {hora} ya está ocupado."

    # 2. Buscar si el cliente ya tiene cita ESE DÍA para reprogramarla
    cita_existente = None
    print(f"[DEBUG] Buscando cita previa para {cliente} en {fecha}...")
    
    for c in citas:
        # Normalizamos nombres para comparar mejor (strip y lower)
        nombre_csv = c["Cliente"].strip().lower()
        nombre_nuevo = cliente.strip().lower()
        
        if c["Fecha"] == fecha and nombre_csv == nombre_nuevo and c["Estado"] == "Confirmado":
            cita_existente = c
            print(f"[DEBUG] ¡Encontrada! Hora actual: {c['Hora']}")
            break
    
    if cita_existente:
        # REPROGRAMAR: Cambiamos la hora de la cita existente
        old_hora = cita_existente["Hora"]
        cita_existente["Hora"] = hora
        cita_existente["Telefono"] = telefono # Actualizar tel si cambió
        guardar_todas_las_citas(citas)
        print(f"[DEBUG] Actualizada a las {hora}")
        return True, f"Reprogramado: De {old_hora} a {hora}"
    else:
        # NUEVA CITA
        print(f"[DEBUG] No se encontró previa. Creando nueva.")
        nueva_cita = {
            "Fecha": fecha,
            "Hora": hora,
            "Cliente": cliente,
            "Telefono": telefono,
            "Estado": "Confirmado"
        }
        citas.append(nueva_cita)
        guardar_todas_las_citas(citas)
        return True, "Agendado correctamente"

def cancelar_cita(fecha, cliente):
    """Cancela citas de un cliente en una fecha"""
    citas = leer_todas_las_citas()
    encontrada = False
    
    for c in citas:
        if c["Fecha"] == fecha and c["Cliente"].lower() == cliente.lower() and c["Estado"] == "Confirmado":
            c["Estado"] = "Cancelado"
            encontrada = True
            
    if encontrada:
        guardar_todas_las_citas(citas)
        return True, "Cita cancelada"
    return False, "No se encontró cita"
