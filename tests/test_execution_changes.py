import unittest

import httpx
from copy import deepcopy
from unittest.mock import AsyncMock, patch

from app.agents.diagram_agent import execute_plan
from app.schemas.chat import PlannerAction
from app.schemas.diagram_execution import DiagramActionResult, DiagramExecutePlanRequest


class ExecutionChangesTest(unittest.IsolatedAsyncioTestCase):
    @patch("app.agents.diagram_agent.execute_diagram_action", new_callable=AsyncMock)
    @patch("app.agents.diagram_agent.load_diagram_context", new_callable=AsyncMock)
    async def test_questions_never_claim_a_diagram_change(self, load, execute):
        request = DiagramExecutePlanRequest(diagrama_id=1, confirmed=True, actions=[
            PlannerAction(order=1, tool="ask_user", description="Confirmar", arguments={"question": "¿Qué clases?"}),
        ])
        result = await execute_plan(request, "token")
        self.assertFalse(result.success)
        self.assertIn("¿Qué clases?", result.message)
        execute.assert_not_awaited()
        load.assert_not_awaited()

    async def _execute(self, updated):
        original = {"id": 1, "contenido": {"nodes": [], "edges": []}}
        action = PlannerAction(order=1, tool="create_class", description="Crear clase", arguments={"name": "Reserva"})
        status = DiagramActionResult(order=1, tool="create_class", success=True, message="Creada")
        with patch("app.agents.diagram_agent.load_diagram_context", new_callable=AsyncMock, return_value=original), \
             patch("app.agents.diagram_agent.execute_diagram_action", new_callable=AsyncMock, return_value=(deepcopy(updated), status)):
            return await execute_plan(DiagramExecutePlanRequest(diagrama_id=1, actions=[action], confirmed=True), "token")

    async def test_unchanged_content_does_not_report_success(self):
        result = await self._execute({"id": 1, "version": 9, "contenido": {"nodes": [], "edges": []}})
        self.assertFalse(result.success)
        self.assertIn("No se detectaron cambios", result.message)

    async def test_missing_content_does_not_report_success(self):
        result = await self._execute({"id": 1})
        self.assertFalse(result.success)

    async def test_changed_content_is_returned_for_canvas_update(self):
        updated = {"id": 1, "contenido": {"nodes": [{"id": "r", "data": {"name": "Reserva"}}], "edges": []}}
        result = await self._execute(updated)
        self.assertTrue(result.success)
        self.assertEqual(result.diagrama, updated)

    async def test_permission_connection_failure_returns_actionable_error(self):
        action = PlannerAction(order=1, tool="create_class", description="Crear", arguments={"name": "Reserva"})
        request = DiagramExecutePlanRequest(diagrama_id=1, proyecto_id=2, actions=[action], confirmed=True)
        with patch("app.agents.diagram_agent.verify_user_permission", new_callable=AsyncMock, side_effect=httpx.ConnectError("offline")):
            result = await execute_plan(request, "token")
        self.assertFalse(result.success)
        self.assertIn("Recarga el diagrama", result.message)

    async def test_structured_backend_error_does_not_crash_response(self):
        action = PlannerAction(order=1, tool="create_class", description="Crear", arguments={"name": "Reserva"})
        request = DiagramExecutePlanRequest(diagrama_id=1, actions=[action], confirmed=True)
        response = httpx.Response(422, json={"detail": [{"msg": "invalid"}]}, request=httpx.Request("GET", "https://backend.test"))
        error = httpx.HTTPStatusError("invalid", request=response.request, response=response)
        with patch("app.agents.diagram_agent.load_diagram_context", new_callable=AsyncMock, side_effect=error):
            result = await execute_plan(request, "token")
        self.assertFalse(result.success)
        self.assertIn("rechazó", result.message)
