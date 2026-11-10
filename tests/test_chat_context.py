import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.main import planner
from app.schemas.chat import PlannerRequest, PlannerResponse


class ChatContextTest(unittest.IsolatedAsyncioTestCase):
    @patch("app.main.run_chat", new_callable=AsyncMock)
    @patch("app.main.get_contexto_chat", new_callable=AsyncMock)
    @patch("app.main.build_context", new_callable=AsyncMock)
    async def test_active_diagram_excludes_other_diagram_history(self, context, history, run):
        run.return_value = PlannerResponse(intent="explain_diagram", summary="Respuesta")
        context.return_value = {"diagrama": {"id": 5, "id_proyecto": 2, "nombre": "Actual", "contenido": {"nodes": [], "edges": []}}}
        history.return_value = {
            "proyecto_id": 2, "solicitante": {"codigo": "u1", "nombre": "Ana"},
            "consulta_actual": {"id": 3, "autor_codigo": "u1", "texto": "Qué clases hay", "diagrama_id": 5},
            "mensajes": [{"diagrama_id": 5, "texto": "Mensaje actual"},
                         {"diagrama_id": 9, "texto": "Clases de otro diagrama"}],
        }
        await planner(PlannerRequest(message="Qué clases hay", proyecto_id=2, diagrama_id=5, conversacion_id=10, mensaje_id=3), "Bearer token")
        supplied = run.call_args.args[1]
        self.assertEqual(supplied["diagrama_activo"]["id"], 5)
        self.assertEqual(len(supplied["conversacion"]["mensajes"]), 1)
        self.assertEqual(supplied["conversacion"]["mensajes"][0]["texto"], "Mensaje actual")

    @patch("app.main.run_chat", new_callable=AsyncMock)
    @patch("app.main.get_contexto_chat", new_callable=AsyncMock)
    @patch("app.main.build_context", new_callable=AsyncMock)
    async def test_uses_authorized_history_and_server_role(self, context, history, run):
        run.return_value = PlannerResponse(intent="explain_diagram", summary="Respuesta")
        context.return_value = {"user_role": "VISUALIZADOR", "diagrama": {"id": 5, "id_proyecto": 2}}
        history.return_value = {
            "proyecto_id": 2, "tipo": "individual",
            "solicitante": {"codigo": "u1", "nombre": "Ana"},
            "consulta_actual": {"id": 3, "autor_codigo": "u1", "texto": "Consulta guardada", "diagrama_id": 5},
            "mensajes": [{"autor_nombre": "Ana", "texto": "Hola", "diagrama_id": 5}],
        }
        request = PlannerRequest(message="Explica", proyecto_id=2, diagrama_id=5,
                                 conversacion_id=10, mensaje_id=3, user_role="OWNER")
        await planner(request, authorization="Bearer test-token")
        history.assert_awaited_once_with(10, "test-token", 3)
        supplied = run.call_args.args[1]
        self.assertEqual(supplied["user_role"], "VISUALIZADOR")
        self.assertEqual(supplied["conversacion"]["mensajes"][0]["autor_nombre"], "Ana")
        self.assertEqual(supplied["solicitante"]["codigo"], "u1")
        self.assertEqual(run.call_args.args[0], "Consulta guardada")

    @patch("app.main.run_chat", new_callable=AsyncMock)
    @patch("app.main.get_contexto_chat", new_callable=AsyncMock)
    @patch("app.main.build_context", new_callable=AsyncMock)
    async def test_rejects_other_authors_question(self, context, history, run):
        run.return_value = PlannerResponse(intent="explain_diagram", summary="Respuesta")
        context.return_value = {}
        history.return_value = {
            "proyecto_id": 2, "solicitante": {"codigo": "u1", "nombre": "Ana"},
            "consulta_actual": {"id": 3, "autor_codigo": "u2", "texto": "Hola", "diagrama_id": None},
        }
        with self.assertRaises(HTTPException) as caught:
            await planner(PlannerRequest(message="Hola", proyecto_id=2, conversacion_id=10, mensaje_id=3), "Bearer token")
        self.assertEqual(caught.exception.status_code, 403)
        run.assert_not_awaited()

    @patch("app.main.run_chat", new_callable=AsyncMock)
    @patch("app.main.get_contexto_chat", new_callable=AsyncMock)
    @patch("app.main.build_context", new_callable=AsyncMock)
    async def test_rejects_conversation_from_another_project(self, context, history, run):
        run.return_value = PlannerResponse(intent="explain_diagram", summary="Respuesta")
        context.return_value = {}
        history.return_value = {"proyecto_id": 99}
        with self.assertRaises(HTTPException) as caught:
            await planner(PlannerRequest(message="Hola", proyecto_id=2, conversacion_id=10), "Bearer token")
        self.assertEqual(caught.exception.status_code, 400)
        run.assert_not_awaited()
