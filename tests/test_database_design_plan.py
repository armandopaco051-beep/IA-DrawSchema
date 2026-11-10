import unittest
import json
from unittest.mock import AsyncMock, patch
import httpx
from app.agents.local.interpreter import DesignSketch, DesignTable, DesignForeignKey, DesignAssociation, design_commands, interpret_request, connected_design
from app.agents.local.commands import Interpretation
from app.agents.local.plan_builder import build_plan
from app.services.plan_grounding import grounding_issues
from app.schemas.chat import PlannerResponse, PlannerAction


class DatabaseDesignPlanTest(unittest.TestCase):
    def test_optional_disconnected_table_is_not_added_to_initial_core(self):
        sketch = DesignSketch(tables=[DesignTable(name=n, attributes=["nombre"]) for n in ("Cliente", "Venta", "Opcional")],
                              foreign_keys=[DesignForeignKey(table="Venta", column="cliente_id", references="Cliente")])
        repaired = connected_design(sketch, "Genera una base de datos", {})
        self.assertEqual({t.name for t in repaired.tables}, {"Cliente", "Venta"})
        self.assertEqual(len(design_commands(repaired, {})), 3)

    def test_required_or_existing_disconnected_table_is_not_silently_omitted(self):
        sketch = DesignSketch(tables=[DesignTable(name=n, attributes=["nombre"]) for n in ("Cliente", "Venta", "Producto")],
                              foreign_keys=[DesignForeignKey(table="Venta", column="cliente_id", references="Cliente")])
        with self.assertRaises(ValueError):
            connected_design(sketch, "Incluye la tabla Producto", {})
        with self.assertRaises(ValueError):
            connected_design(sketch, "Genera una base de datos", {"diagrama": {"contenido": {"nodes": [{"id": "p", "data": {"name": "Producto"}}]}}})

    def test_id_fk_is_separate_from_own_primary_key(self):
        sketch = DesignSketch(tables=[DesignTable(name="Cliente", attributes=["nombre"]), DesignTable(name="Venta", attributes=["fecha"])],
                              foreign_keys=[DesignForeignKey(table="Venta", column="id", references="Clientes.id")])
        self.assertEqual(sketch.foreign_keys[0].references, "Cliente")
        self.assertEqual(sketch.foreign_keys[0].column, "cliente_id")

    def test_generation_has_tables_then_relations(self):
        sketch = DesignSketch(tables=[DesignTable(name="Cliente", attributes=["nombre"]), DesignTable(name="Venta", attributes=["fecha", "cliente_id"])],
                              foreign_keys=[DesignForeignKey(table="Venta", column="cliente_id", references="Cliente")])
        plan = build_plan(Interpretation(intent="modify_diagram", commands=design_commands(sketch, {})), {})
        self.assertTrue(plan.can_execute)
        self.assertEqual([a.tool for a in plan.actions], ["create_class", "create_class", "create_relation"])
        self.assertEqual(plan.actions[-1].arguments["sourceName"], "Cliente")
        self.assertEqual(plan.actions[-1].arguments["targetName"], "Venta")
        self.assertEqual(plan.actions[-1].arguments["sourceCardinality"], "1")
        self.assertEqual(plan.actions[-1].arguments["targetCardinality"], "0..*")
        self.assertNotIn("cliente_id", [a["name"] for a in plan.actions[1].arguments["attributes"]])

    def test_many_many_uses_association_class_not_extra_relations(self):
        sketch = DesignSketch(tables=[DesignTable(name="Producto", attributes=["nombre"]), DesignTable(name="Venta", attributes=["fecha"]), DesignTable(name="DetalleVenta", attributes=["cantidad"])],
            foreign_keys=[DesignForeignKey(table="DetalleVenta", column="producto_id", references="Producto"), DesignForeignKey(table="DetalleVenta", column="venta_id", references="Venta")],
            association_classes=[DesignAssociation(source="Producto", target="Venta", intermediate="DetalleVenta")])
        plan = build_plan(Interpretation(intent="modify_diagram", commands=design_commands(sketch, {})), {})
        self.assertTrue(plan.can_execute)
        self.assertEqual([a.tool for a in plan.actions], ["create_class"] * 3 + ["create_relation"])
        self.assertEqual(plan.actions[-1].arguments["relationType"], "associationClass")
        self.assertEqual(plan.actions[-1].arguments["associationClassName"], "DetalleVenta")

    def test_disconnected_proposal_cannot_be_presented_as_complete(self):
        sketch = DesignSketch(tables=[DesignTable(name=n, attributes=["nombre"]) for n in ("Cliente", "Venta", "Producto")],
                              foreign_keys=[DesignForeignKey(table="Venta", column="cliente_id", references="Cliente")])
        with self.assertRaises(ValueError):
            design_commands(sketch, {})

    def test_whole_database_plan_without_relationships_is_rejected(self):
        plan = PlannerResponse(intent="modify_diagram", summary="Crear tablas", can_execute=True, actions=[
            PlannerAction(order=i, tool="create_class", description="Crear", arguments={"name": n}) for i, n in enumerate(("Cliente", "Venta"), 1)])
        self.assertTrue(grounding_issues("Genera una base de datos para un restaurante", plan, {}))
        self.assertFalse(grounding_issues("Genera una base de datos solo tablas sin relaciones", plan, {}))


class DatabaseDesignInferenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_repairs_links_with_fixed_table_names_before_building_plan(self):
        raw = {"tables": [{"name": "Cliente", "attributes": ["nombre"]}, {"name": "Venta", "attributes": ["fecha"]}],
               "foreign_keys": [{"table": "Venta", "column": "cliente_id", "references": "Ausente"}], "association_classes": []}
        fixed = {"foreign_keys": [{"table": "Venta", "column": "cliente_id", "references": "Cliente"}], "association_classes": []}
        client = AsyncMock()
        client.post.side_effect = [httpx.Response(200, json={"message": {"content": json.dumps(data)}}, request=httpx.Request("POST", "http://test/api/chat")) for data in (raw, fixed)]
        with patch("app.agents.local.interpreter.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            parsed = await interpret_request("Genera una base de datos para un restaurante con tablas y relaciones", {})
        plan = build_plan(parsed, {})
        self.assertTrue(plan.can_execute)
        self.assertEqual([a.tool for a in plan.actions], ["create_class", "create_class", "create_relation"])
        schema = client.post.call_args_list[1].kwargs["json"]["format"]
        self.assertEqual(schema["properties"]["foreign_keys"]["items"]["properties"]["references"]["enum"], ["Cliente", "Venta"])
