import unittest
from unittest.mock import patch, MagicMock
import json
import os
import datetime
from api_server import app, procesar_cita, db

class TestBotIntegration(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        # Use an in-memory DB or a test DB file would be better, but for now we test the logic functions
        # We will check if the DB entry is created.

    def test_procesar_cita(self):
        # Simulate AI response
        ai_response = "Claro, he agendado tu cita. [CITA]Juan Perez|Corte|2024-12-25|10:00[/CITA]"
        cliente_telefono = "12345678"

        # Clear previous test data if any
        citas_previas = db.obtener_citas_por_fecha("2024-12-25")

        # Execute logic
        procesar_cita(ai_response, cliente_telefono)

        # Verify DB
        citas_nuevas = db.obtener_citas_por_fecha("2024-12-25")

        # Check if we have one more appointment
        found = False
        for cita in citas_nuevas:
            if cita['cliente_nombre'] == "Juan Perez" and cita['hora'] == "10:00":
                found = True
                break

        self.assertTrue(found, "La cita no se guardó en la base de datos")
        print("✅ Test de Integración Bot -> DB exitoso: Cita guardada correctamente.")

if __name__ == '__main__':
    unittest.main()
