import unittest
from unittest.mock import AsyncMock, patch

from app.schemas.chat import PlannerAction
from app.schemas.diagram_execution import DiagramExecutePlanRequest
from app.services.plan_validation import prepare_association_actions
from app.agents.diagram_agent import execute_plan
from app.tools.diagram_tools import build_create_relation_body


def relation(description="Relacionar producto y ventas usando DetalleVenta"):
    return PlannerAction(order=2, tool="create_relation", description=description, arguments={
        "sourceName": "producto", "targetName": "ventas", "relationType": "associationClass",
        "sourceCardinality": "0..*", "targetCardinality": "0..*",
    })


DIAGRAM = {"contenido": {"nodes": [
    {"id": "p", "data": {"name": "producto"}},
    {"id": "v", "data": {"name": "ventas"}},
    {"id": "d", "data": {"name": "DetalleVenta"}},
], "edges": []}}


class AssociationPlanTest(unittest.TestCase):
    def test_many_many_association_from_any_provider_gets_intermediate(self):
        action = PlannerAction(order=1, tool="create_relation", description="Relacionar", arguments={
            "sourceName": "Autor", "targetName": "Libro", "relationType": "association",
            "sourceCardinality": "1..*", "targetCardinality": "0..*",
        })
        graph = {"contenido": {"nodes": [{"id": "a", "data": {"name": "Autor"}}, {"id": "l", "data": {"name": "Libro"}}]}}
        actions, issues = prepare_association_actions([action], graph)
        self.assertFalse(issues)
        self.assertEqual([a.tool for a in actions], ["create_class", "create_relation"])
        self.assertEqual(actions[1].arguments["associationClassName"], actions[0].arguments["name"])
        self.assertEqual(action.arguments["relationType"], "association")

    def test_recovers_unique_explicit_name_and_resolves_real_id(self):
        actions, issues = prepare_association_actions([relation()], DIAGRAM)
        self.assertEqual(issues, [])
        body = build_create_relation_body(actions[0].arguments, DIAGRAM, "u1")
        self.assertEqual(body["data"]["associationClassId"], "d")
        self.assertEqual((body["source"], body["target"]), ("p", "v"))

    def test_references_class_created_earlier_without_mutating_original(self):
        original = relation()
        create = PlannerAction(order=1, tool="create_class", description="Crear detalle", arguments={"name": "DetalleVenta"})
        actions, issues = prepare_association_actions([create, original])
        self.assertFalse(issues)
        self.assertEqual(actions[1].arguments["associationClassName"], "DetalleVenta")
        self.assertNotIn("associationClassName", original.arguments)

    def test_does_not_guess_an_existing_class(self):
        _actions, issues = prepare_association_actions([relation("Relacionar producto y ventas")], DIAGRAM)
        self.assertTrue(issues)

    def test_new_association_class_matches_frontend_position(self):
        diagram = {"contenido": {"nodes": [
            {"id": "p", "position": {"x": 100, "y": 300}, "data": {"name": "producto"}},
            {"id": "v", "position": {"x": 500, "y": 600}, "data": {"name": "ventas"}},
        ]}}
        creation = PlannerAction(order=1, tool="create_class", description="Crear detalle", arguments={"name": "DetalleVenta"})
        actions, issues = prepare_association_actions([creation, relation()], diagram)
        self.assertFalse(issues)
        self.assertEqual(actions[0].arguments["x"], 300)
        self.assertEqual(actions[0].arguments["y"], 130)

    def test_existing_association_class_is_not_repositioned(self):
        diagram = {"contenido": {"nodes": [*DIAGRAM["contenido"]["nodes"]]}}
        original = __import__('copy').deepcopy(diagram)
        prepare_association_actions([relation()], diagram)
        self.assertEqual(diagram, original)


class PreflightTest(unittest.IsolatedAsyncioTestCase):
    @patch("app.agents.diagram_agent.execute_diagram_action", new_callable=AsyncMock)
    @patch("app.agents.diagram_agent.load_diagram_context", new_callable=AsyncMock)
    async def test_bad_relation_blocks_before_any_class_is_created(self, load, execute):
        load.return_value = DIAGRAM
        create = PlannerAction(order=1, tool="create_class", description="Crear detalle", arguments={"name": "OtraClase"})
        data = DiagramExecutePlanRequest(diagrama_id=1, actions=[create, relation("Relacionar participantes")], confirmed=True)
        result = await execute_plan(data, "test-token")
        self.assertFalse(result.success)
        execute.assert_not_awaited()
