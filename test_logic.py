import unittest
from api_server import procesar_memoria_ia

class TestBotLogic(unittest.TestCase):
    def test_hour_normalization(self):
        # Case 1: "5" -> "17:00"
        state = {}
        response = '[MEMORIA]{"hora": "5"}[/MEMORIA]'
        new_state = procesar_memoria_ia(response, state)
        self.assertEqual(new_state.get('hora_intencion'), "17:00")

    def test_hour_explicit_am_rejection(self):
        # Case 2: "05:00" -> Now converted to 17:00 (PM rule)
        state = {}
        response = '[MEMORIA]{"hora": "05:00"}[/MEMORIA]'
        new_state = procesar_memoria_ia(response, state)
        self.assertEqual(new_state.get('hora_intencion'), "17:00")

    def test_hour_explicit_pm_acceptance(self):
        # Case 3: "17:00" -> Accepted
        state = {}
        response = '[MEMORIA]{"hora": "17:00"}[/MEMORIA]'
        new_state = procesar_memoria_ia(response, state)
        self.assertEqual(new_state.get('hora_intencion'), "17:00")

    def test_hour_ghost_slot_rejection(self):
        # Case 4: "07:00" -> Now converted to 19:00 (PM rule)
        state = {}
        response = '[MEMORIA]{"hora": "07:00"}[/MEMORIA]'
        new_state = procesar_memoria_ia(response, state)
        self.assertEqual(new_state.get('hora_intencion'), "19:00")

    def test_hour_upper_boundary(self):
        # Case 5: "20:00" -> Rejected (Closed at 20:00)
        state = {}
        response = '[MEMORIA]{"hora": "20:00"}[/MEMORIA]'
        new_state = procesar_memoria_ia(response, state)
        self.assertIsNone(new_state.get('hora_intencion'))

    def test_hour_valid_slot(self):
        # Case 6: "19:00" -> Accepted
        state = {}
        response = '[MEMORIA]{"hora": "19:00"}[/MEMORIA]'
        new_state = procesar_memoria_ia(response, state)
        self.assertEqual(new_state.get('hora_intencion'), "19:00")

    def test_hour_explicit_am_valid(self):
        # Case 7: "08:00" -> Accepted (It is AM but open)
        state = {}
        response = '[MEMORIA]{"hora": "08:00"}[/MEMORIA]'
        new_state = procesar_memoria_ia(response, state)
        self.assertEqual(new_state.get('hora_intencion'), "08:00")

if __name__ == '__main__':
    unittest.main()
