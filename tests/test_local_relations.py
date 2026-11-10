import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas.chat import PlannerAction, PlannerResponse
from app.agents.local.relation_checks import relation_request_issues
from app.agents.local.planner_agent import run_planner


MESSAGE = "Relaciona Producto y Venta muchos a muchos y crea la clase intermedia DetalleVenta"
CONTEXT = {"diagrama": {"id": 34, "contenido": {"nodes": [
    {"id": "p", "data": {"name": "Producto"}},
    {"id": "v", "data": {"name": "Venta"}},
], "edges": []}}}


def plan(name="DetalleVenta", source="Producto", target="Venta"):
    return PlannerResponse(intent="modify_diagram", summary="Crear vínculo", can_execute=True, actions=[
        PlannerAction(order=1, tool="create_class", description="Crear intermedia", arguments={"name": name}),
        PlannerAction(order=2, tool="create_relation", description="Relacionar participantes", arguments={
            "sourceName": source, "targetName": target, "relationType": "associationClass",
            "associationClassName": name, "sourceCardinality": "0..*", "targetCardinality": "1..*",
        }),
    ])


class LocalRelationTest(unittest.TestCase):
    def test_rule_is_independent_of_entity_names(self):
        for source, target, middle in (
            ("Paciente", "Tratamiento", "Prescripción"),
            ("Autor", "Libro", "Autoría"),
            ("SensorIndustrial", "Estación", "LecturaAsignada"),
            ("Entidad_27", "Entidad_93", "Vinculo_42"),
        ):
            with self.subTest(source=source, target=target):
                context = {"diagrama": {"contenido": {"nodes": [
                    {"id": "s", "data": {"name": source}},
                    {"id": "t", "data": {"name": target}},
                ]}}}
                message = f"Relaciona {source} y {target} muchos a muchos y crea clase intermedia {middle}"
                self.assertEqual(relation_request_issues(message, plan(middle, source, target), context), [])

    def test_accepts_product_sale_and_other_domains(self):
        self.assertEqual(relation_request_issues(MESSAGE, plan(), CONTEXT), [])
        context = {"diagrama": {"contenido": {"nodes": [
            {"id": "a", "data": {"name": "Estudiante"}},
            {"id": "b", "data": {"name": "Materia"}},
        ]}}}
        self.assertEqual(relation_request_issues(
            "Relaciona Estudiante y Materia muchos a muchos y crea tabla intermedia Inscripcion",
            plan("Inscripcion", "Estudiante", "Materia"), context), [])

    def test_rejects_summary_without_relation_action(self):
        response = plan()
        response.actions = []
        self.assertTrue(relation_request_issues(MESSAGE, response, CONTEXT))

    def test_rejects_missing_or_late_intermediate(self):
        for order in (None, 3):
            response = plan()
            if order is None:
                response.actions.pop(0)
            else:
                response.actions[0].order = order
            self.assertTrue(relation_request_issues(MESSAGE, response, CONTEXT))

    def test_reuses_existing_intermediate(self):
        response = plan()
        response.actions.pop(0)
        context = {"diagrama": {"contenido": {"nodes": [
            *CONTEXT["diagrama"]["contenido"]["nodes"],
            {"id": "d", "data": {"name": "DetalleVenta"}},
        ]}}}
        self.assertEqual(relation_request_issues(MESSAGE, response, context), [])

    def test_rejects_wrong_multiplicity_and_missing_endpoint(self):
        response = plan()
        response.actions[1].arguments.update(sourceCardinality="1", targetName="OtraClase")
        self.assertEqual(len(relation_request_issues(MESSAGE, response, CONTEXT)), 2)

    def test_allows_clarification_and_explanations(self):
        response = PlannerResponse(intent="needs_clarification", summary="Confirmar mínimos", questions=["¿Opcional u obligatorio?"])
        self.assertEqual(relation_request_issues(MESSAGE, response, {}), [])
        response = PlannerResponse(intent="explain_diagram", summary="Explicación")
        self.assertEqual(relation_request_issues("Qué es muchos a muchos con clase intermedia", response, CONTEXT), [])


class LocalRelationRetryTest(unittest.IsolatedAsyncioTestCase):
    @patch("app.agents.local.planner_agent.configure_ai_provider")
    @patch("app.agents.local.planner_agent.interpret_request", new_callable=AsyncMock)
    async def test_unnecessary_question_is_retried_as_modification(self, interpreter, configure):
        from app.agents.local.commands import Interpretation, Command
        interpreter.side_effect = [Interpretation(intent="needs_clarification", questions=["¿Crear intermedia?"]),
            Interpretation(intent="modify_diagram", commands=[Command(operation="create_relation", source="Producto", target="Venta", relation="associationClass", intermediate="DetalleVenta")])]
        result = await run_planner(MESSAGE, CONTEXT)
        self.assertEqual(interpreter.await_count, 2)
        self.assertTrue(result.can_execute)
        self.assertEqual([a.tool for a in result.actions], ["create_class", "create_relation"])

    @patch("app.agents.local.planner_agent.configure_ai_provider")
    @patch("app.agents.local.planner_agent.interpret_request", new_callable=AsyncMock)
    async def test_repeated_bad_relation_blocks_execution(self, interpreter, configure):
        from app.agents.local.commands import Interpretation, Command
        interpreter.return_value = Interpretation(intent="modify_diagram", commands=[Command(operation="create_relation", source="Producto", target="Venta", relation="associationClass", intermediate="DetalleVenta", source_cardinality="1")])
        result = await run_planner(MESSAGE, CONTEXT)
        self.assertFalse(result.can_execute)
        self.assertEqual(result.actions, [])
        self.assertTrue(result.questions)
