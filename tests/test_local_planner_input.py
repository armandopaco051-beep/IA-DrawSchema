import json
import unittest
from unittest.mock import patch

from app.agents.planner_agent import build_planner_input


class LocalPlannerInputTest(unittest.TestCase):
    @patch("app.agents.planner_agent.get_agent_provider", return_value="ollama")
    def test_compact_input_keeps_graph_identity_and_current_request(self, _provider):
        context = {
            "user_role": "EDITOR", "solicitante": {"codigo": "u1", "nombre": "Ana"},
            "consulta_actual": {"id": 7},
            "diagrama": {"id": 34, "nombre": "Actual", "contenido": {
                "nodes": [{"id": "n1", "data": {"name": "Proveedor"}, "style": {"width": 300}}],
                "edges": [{"id": "e1", "source": "n1", "target": "n1", "data": {"relationType": "association"}}],
            }},
            "conversacion": {"mensajes": [{"id": 7, "texto": "Petición actual"}]},
        }
        result = json.loads(build_planner_input("Agrega Cliente", context))
        self.assertEqual(result["solicitante"]["codigo"], "u1")
        self.assertEqual(result["diagrama_actual"]["id"], 34)
        self.assertEqual(result["diagrama_actual"]["nodes"][0]["data"]["name"], "Proveedor")
        self.assertEqual(len(result["diagrama_actual"]["edges"]), 1)
        self.assertNotIn("style", result["diagrama_actual"]["nodes"][0])
        self.assertEqual(result["historial_reciente"], [])
        self.assertEqual(result["peticion_actual"], "Agrega Cliente")
