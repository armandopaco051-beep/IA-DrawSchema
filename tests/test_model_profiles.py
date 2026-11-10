import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from app.agents.planner_agent import create_planner_agent, build_planner_input
from app.agents.suggestion_agent import create_suggestion_agent
from app.agents.validation_agent import create_validation_agent
from app.agents.codegen_agent import create_codegen_agent
from app.config.agents_models import select_text_provider
from app.prompts.gemini_rules import GEMINI_RULES
from app.agents.local.rules import LOCAL_RULES
from app.agents.local.planner_agent import INSTRUCTIONS as LOCAL_PLANNER
from app.agents.local.suggestion_agent import INSTRUCTIONS as LOCAL_SUGGESTION
from app.agents.local.validation_agent import INSTRUCTIONS as LOCAL_VALIDATION
from app.agents.local.codegen_agent import INSTRUCTIONS as LOCAL_CODEGEN

LOCAL_INSTRUCTIONS = dict(planner=LOCAL_PLANNER, suggestion=LOCAL_SUGGESTION,
                          validation=LOCAL_VALIDATION, codegen=LOCAL_CODEGEN)


FACTORIES = {
    "planner": create_planner_agent,
    "suggestion": create_suggestion_agent,
    "validation": create_validation_agent,
    "codegen": create_codegen_agent,
}


class ModelProfilesTest(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_requests_use_matching_model_and_instructions(self):
        async def inspect(provider):
            with select_text_provider(provider):
                await asyncio.sleep(0)
                result = {}
                for name, factory in FACTORIES.items():
                    module = f"app.agents.local.{name}_agent" if provider == "local" else f"app.agents.{name}_agent"
                    with patch(f"{module}.get_agent_model", return_value="model-" + provider):
                        agent = factory()
                    result[name] = (agent.model, agent.instructions, agent.name)
                return result

        local, gemini = await asyncio.gather(inspect("local"), inspect("gemini"))
        for name in FACTORIES:
            self.assertEqual(local[name][0], "model-local")
            self.assertEqual(gemini[name][0], "model-gemini")
            self.assertIn(LOCAL_RULES, local[name][1])
            self.assertTrue(local[name][2].startswith("Local "))
            self.assertIn(GEMINI_RULES, gemini[name][1])
            self.assertFalse(gemini[name][2].startswith("Local "))
            self.assertIn(LOCAL_INSTRUCTIONS[name], local[name][1])
            self.assertNotEqual(local[name][1], gemini[name][1])

    async def test_new_question_keeps_verified_author_and_active_diagram(self):
        context = {
            "solicitante": {"codigo": "ana", "nombre": "Ana"},
            "consulta_actual": {"id": 22, "autor_codigo": "ana"},
            "diagrama": {"id": 34, "contenido": {"nodes": [], "edges": []}},
            "conversacion": {"mensajes": [{"id": 21, "texto": "Crear Cliente"}]},
        }
        with select_text_provider("local"):
            data = json.loads(build_planner_input("Agrega Producto", context))
        self.assertEqual(data["peticion_actual"], "Agrega Producto")
        self.assertEqual(data["consulta_actual"]["autor_codigo"], "ana")
        self.assertEqual(data["diagrama_actual"]["id"], 34)
        self.assertEqual(data["diagrama_actual"]["nodes"], [])


class LocalDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_each_local_request_uses_its_own_runner(self):
        import importlib
        for name in FACTORIES:
            module = importlib.import_module(f"app.agents.{name}_agent")
            args = ("Crear Producto", {})
            if name == "codegen":
                args += ("demo", "com.demo", "demo_db")
            with select_text_provider("local"), \
                 patch(f"app.agents.local.{name}_agent.run_{name}", new_callable=AsyncMock) as local, \
                 patch(f"app.agents.{name}_agent.Runner.run", new_callable=AsyncMock) as gemini:
                local.return_value = object()
                result = await getattr(module, f"run_{name}")(*args)
                self.assertIs(result, local.return_value)
                local.assert_awaited_once_with(*args)
                gemini.assert_not_awaited()

    async def test_local_factory_does_not_depend_on_gemini_instructions(self):
        with select_text_provider("local"), \
             patch("app.agents.planner_agent.PLANNER_INSTRUCTIONS", "GEMINI_SENTINEL"), \
             patch("app.agents.planner_agent.GEMINI_RULES", "GEMINI_RULE_SENTINEL"), \
             patch("app.agents.local.planner_agent.get_agent_model", return_value="local-model"):
            agent = create_planner_agent()
        self.assertNotIn("GEMINI_SENTINEL", agent.instructions)
        self.assertNotIn("GEMINI_RULE_SENTINEL", agent.instructions)
        self.assertEqual(agent.model, "local-model")
