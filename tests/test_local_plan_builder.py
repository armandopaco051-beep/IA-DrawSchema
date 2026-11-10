import json
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch
import httpx

from app.agents.local.commands import Interpretation, Command, Attribute, Method
from app.agents.local.plan_builder import build_plan
from app.agents.local.interpreter import interpret_request, ClassExtraction, RelationReplacementExtraction, LocalInferenceError, RelationExtraction, NewClass
from app.agents.diagram_agent import execute_plan
from app.schemas.diagram_execution import DiagramExecutePlanRequest


def context(source="Producto", target="Venta"):
    return {"user_role": "EDITOR", "diagrama": {"id": 1, "version": 1, "contenido": {"nodes": [
        {"id": "a", "data": {"name": source, "attributes": [{"name": "id", "type": "BIGINT", "primaryKey": True}]}},
        {"id": "b", "data": {"name": target, "attributes": []}},
    ], "edges": []}}}


def compile(commands, ctx=None):
    return build_plan(Interpretation(intent="modify_diagram", commands=commands), ctx or context())


class BuilderTest(unittest.TestCase):
    def test_identical_relation_repeated_inside_plan_is_created_once(self):
        relation = Command(operation="create_relation", source="Producto", target="Venta", relation="association", source_cardinality="1", target_cardinality="0..*")
        result = compile([relation, relation.model_copy(deep=True)])
        self.assertTrue(result.can_execute)
        self.assertEqual(len(result.actions), 1)

    def test_conflicting_relation_repeated_inside_plan_is_rejected(self):
        a = Command(operation="create_relation", source="Producto", target="Venta", relation="association", source_cardinality="1", target_cardinality="0..*")
        b = a.model_copy(update={"target_cardinality": "1..*"})
        self.assertFalse(compile([a, b]).can_execute)

    def test_attribute_rename_keeps_type_and_does_not_rename_class(self):
        ctx = context()
        ctx["diagrama"]["contenido"]["nodes"][0]["data"]["attributes"].append({"name": "marca", "type": "VARCHAR", "nullable": False})
        result = compile([Command(operation="update_class", name="Producto", rename_attributes={"marca": "fabricante"})], ctx)
        self.assertTrue(result.can_execute)
        args = result.actions[0].arguments
        self.assertNotIn("newName", args)
        self.assertEqual(args["attributes"][1], {"name": "fabricante", "type": "VARCHAR", "nullable": False})

    def test_unspecified_relation_does_not_default_to_many_many(self):
        result = compile([Command(operation="create_relation", source="Producto", target="Venta", relation="association")])
        self.assertTrue(result.can_execute)
        self.assertEqual([a.tool for a in result.actions], ["create_relation"])
        self.assertEqual(result.actions[0].arguments["sourceCardinality"], "1")
        self.assertEqual(result.actions[0].arguments["targetCardinality"], "0..*")

    def test_explicit_many_many_creates_intermediate_even_without_requesting_it(self):
        result = compile([Command(operation="create_relation", source="Producto", target="Venta", relation="association", source_cardinality="0..*", target_cardinality="1..*")])
        self.assertEqual([a.tool for a in result.actions], ["create_class", "create_relation"])
        self.assertEqual(result.actions[-1].arguments["relationType"], "associationClass")
        self.assertEqual(result.actions[-1].arguments["associationClassName"], result.actions[0].arguments["name"])

    def test_reassigns_either_endpoint_preserving_intermediate_and_multiplicities(self):
        for source, target in (("a", "b"), ("b", "a")):
            ctx = context("Cliente", "Producto")
            graph = ctx["diagrama"]["contenido"]
            graph["nodes"] += [{"id": "v", "data": {"name": "Venta"}}, {"id": "d", "data": {"name": "DetalleVenta"}}]
            graph["edges"] = [{"id": "rel-real", "source": source, "target": target, "data": {
                "relationType": "associationClass", "associationClassId": "d", "sourceCardinality": "1..*", "targetCardinality": "0..*"}}]
            result = compile([Command(operation="update_relation", relation_id="rel-real", old_participant="Cliente", new_participant="Venta")], ctx)
            self.assertTrue(result.can_execute)
            self.assertEqual(len(result.actions), 1)
            action = result.actions[0]
            self.assertEqual(action.tool, "update_relation")
            self.assertEqual({action.arguments["sourceName"], action.arguments["targetName"]}, {"Producto", "Venta"})
            self.assertEqual(action.arguments["associationClassName"], "DetalleVenta")
            self.assertEqual(action.arguments["sourceCardinality"], "1..*")
            self.assertEqual(action.arguments["targetCardinality"], "0..*")

    def test_missing_participant_does_not_show_none_as_a_class(self):
        result = compile([Command(operation="delete_relation", source="Producto")])
        self.assertFalse(result.can_execute)
        self.assertNotIn("None", result.summary)

    def test_rejects_replacing_class_outside_selected_relation(self):
        ctx = context()
        ctx["diagrama"]["contenido"]["nodes"].append({"id": "c", "data": {"name": "Cliente"}})
        ctx["diagrama"]["contenido"]["edges"] = [{"id": "r", "source": "a", "target": "b", "data": {"relationType": "association"}}]
        result = compile([Command(operation="update_relation", relation_id="r", old_participant="Cliente", new_participant="Venta")], ctx)
        self.assertFalse(result.can_execute)

    def test_update_does_not_reset_type_or_primary_key(self):
        result = compile([Command(operation="update_class", name="Producto", attributes=[Attribute(name="id", nullable=False)])])
        attribute = result.actions[0].arguments["attributes"][0]
        self.assertEqual(attribute["type"], "BIGINT")
        self.assertTrue(attribute["primaryKey"])

    def test_method_addition_keeps_existing_methods(self):
        ctx = context()
        ctx["diagrama"]["contenido"]["nodes"][0]["data"]["methods"] = [{"name": "consultar", "returnType": "void"}]
        result = compile([Command(operation="update_class", name="Producto", methods=[Method(name="registrar")])], ctx)
        self.assertEqual([m["name"] for m in result.actions[0].arguments["methods"]], ["consultar", "registrar"])

    def test_realization_and_template_binding_have_no_multiplicity(self):
        for kind in ("realization", "templateBinding"):
            ctx = context()
            target = ctx["diagrama"]["contenido"]["nodes"][1]["data"]
            target["kind"] = "interface"
            target["templateParameters"] = ["T"]
            result = compile([Command(operation="create_relation", source="Producto", target="Venta", relation=kind, template_bindings={"T": "String"})], ctx)
            self.assertTrue(result.can_execute)
            self.assertNotIn("sourceCardinality", result.actions[0].arguments)

    def test_generalization_cycle_is_blocked(self):
        ctx = context()
        ctx["diagrama"]["contenido"]["edges"] = [{"id": "r", "source": "b", "target": "a", "data": {"relationType": "generalization"}}]
        result = compile([Command(operation="create_relation", source="Producto", target="Venta", relation="generalization")], ctx)
        self.assertFalse(result.can_execute)

    def test_dynamic_intermediate_before_relation_and_known_keys(self):
        for source, target, middle in (("Producto", "Venta", "DetalleVenta"), ("Autor", "Libro", "Autoria"), ("Paciente", "Tratamiento", "Prescripcion")):
            ctx = context(source, target)
            original = deepcopy(ctx)
            result = compile([Command(operation="create_relation", source=source, target=target, relation="associationClass", intermediate=middle)], ctx)
            self.assertTrue(result.can_execute)
            self.assertEqual([a.tool for a in result.actions], ["create_class", "create_relation"])
            self.assertEqual(result.actions[0].arguments["name"], middle)
            self.assertTrue(result.actions[0].arguments["attributes"][0]["foreignKey"])
            self.assertEqual(result.actions[1].arguments["sourceName"], source)
            self.assertEqual(result.actions[1].arguments["associationClassName"], middle)
            self.assertEqual(result.actions[1].arguments["sourceCardinality"], "0..*")
            self.assertEqual(ctx, original)

    def test_existing_middle_is_reused(self):
        ctx = context()
        ctx["diagrama"]["contenido"]["nodes"].append({"id": "m", "data": {"name": "DetalleVenta"}})
        result = compile([Command(operation="create_relation", source="Producto", target="Venta", relation="associationClass", intermediate="DetalleVenta")], ctx)
        self.assertEqual([a.tool for a in result.actions], ["create_relation"])

    def test_update_preserves_existing_attributes(self):
        result = compile([Command(operation="update_class", name="Producto", attributes=[Attribute(name="nombre", type="VARCHAR")])])
        self.assertEqual([a["name"] for a in result.actions[0].arguments["attributes"]], ["id", "nombre"])

    def test_no_partial_plan_when_endpoint_is_missing(self):
        result = compile([Command(operation="create_class", name="Reserva"), Command(operation="create_relation", source="Reserva", target="Ausente")])
        self.assertFalse(result.can_execute)
        self.assertEqual(result.actions, [])

    def test_no_multiplicity_for_generalization(self):
        result = compile([Command(operation="create_relation", source="Producto", target="Venta", relation="generalization", source_cardinality="1..*")])
        self.assertNotIn("sourceCardinality", result.actions[0].arguments)

    def test_composition_rejects_many_owners(self):
        result = compile([Command(operation="create_relation", source="Producto", target="Venta", relation="composition", source_cardinality="1..*")])
        self.assertFalse(result.can_execute)

    def test_viewer_cannot_modify(self):
        ctx = context()
        ctx["user_role"] = "VIEWER"
        self.assertFalse(compile([Command(operation="delete_class", name="Producto")], ctx).can_execute)

    def test_delete_requires_confirmation_and_move_has_coordinates(self):
        result = compile([Command(operation="move_class", name="Producto", x=300, y=220), Command(operation="delete_class", name="Venta")])
        self.assertEqual(result.actions[0].arguments["x"], 300)
        self.assertTrue(result.actions[1].requires_confirmation)


class NativeInterpreterTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_and_relate_orders_dependencies_and_obeys_explicit_one_many(self):
        output = RelationExtraction(source="Cliente", target="Producto", relation="associationClass",
                                    source_cardinality="0..*", target_cardinality="0..*",
                                    new_classes=[NewClass(name="Cliente")])
        response = httpx.Response(200, json={"message": {"content": output.model_dump_json()}}, request=httpx.Request("POST", "http://test/api/chat"))
        client = AsyncMock()
        client.post.return_value = response
        ctx = context()
        ctx["diagrama"]["contenido"]["nodes"] = ctx["diagrama"]["contenido"]["nodes"][:1]
        with patch("app.agents.local.interpreter.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            parsed = await interpret_request("agrega la clase cliente y relacion de 1 a muchos", ctx)
        plan = build_plan(parsed, ctx)
        self.assertTrue(plan.can_execute)
        self.assertEqual([a.tool for a in plan.actions], ["create_class", "create_relation"])
        self.assertEqual(plan.actions[0].arguments["name"], "Cliente")
        self.assertEqual(plan.actions[1].arguments["relationType"], "association")
        self.assertEqual(plan.actions[1].arguments["sourceCardinality"], "1")
        self.assertEqual(plan.actions[1].arguments["targetCardinality"], "0..*")

    async def test_attribute_deletion_cannot_become_class_deletion(self):
        output = ClassExtraction(operation="delete_class", name="Producto", remove_attributes=["marca"])
        response = httpx.Response(200, json={"message": {"content": output.model_dump_json()}}, request=httpx.Request("POST", "http://test/api/chat"))
        client = AsyncMock()
        client.post.return_value = response
        ctx = context()
        ctx["diagrama"]["contenido"]["nodes"][0]["data"]["attributes"].append({"name": "marca", "type": "VARCHAR"})
        with patch("app.agents.local.interpreter.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            parsed = await interpret_request("elimina el atributo marca de la clase Producto", ctx)
        plan = build_plan(parsed, ctx)
        self.assertEqual([a.tool for a in plan.actions], ["update_class"])
        self.assertEqual([a["name"] for a in plan.actions[0].arguments["attributes"]], ["id"])

    async def test_target_before_verb_overrides_stale_class_name(self):
        response = httpx.Response(200, json={"message": {"content": ClassExtraction(
            operation="create_class", name="Cliente", attributes=[Attribute(name="marca")]
        ).model_dump_json()}}, request=httpx.Request("POST", "http://test/api/chat"))
        client = AsyncMock()
        client.post.return_value = response
        ctx = context()
        ctx["conversacion"] = {"mensajes": [{"id": 1, "texto": "Crear Cliente"}]}
        with patch("app.agents.local.interpreter.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            parsed = await interpret_request("a la clase producto agrega el atributo marca", ctx)
        sent = client.post.call_args.kwargs["json"]
        self.assertEqual(sent["format"]["title"], "ClassExtraction")
        payload = json.loads(sent["messages"][1]["content"])
        self.assertEqual(payload["destino_identificado"], "Producto")
        self.assertNotIn("Cliente", sent["messages"][1]["content"])
        result = build_plan(parsed, ctx)
        self.assertTrue(result.can_execute)
        self.assertEqual(result.actions[0].tool, "update_class")
        self.assertEqual(result.actions[0].arguments["className"], "Producto")
        self.assertEqual([a["name"] for a in result.actions[0].arguments["attributes"]], ["id", "marca"])

    async def test_business_design_question_uses_explanation_not_editor_commands(self):
        for domain in ("restaurante", "biblioteca", "clinica"):
            response = httpx.Response(200, json={"message": {"content": json.dumps({"tables": [{"name": "EntidadA", "attributes": ["nombre"]}, {"name": "EntidadB", "attributes": ["fecha"]}], "foreign_keys": [{"table": "EntidadB", "column": "entidad_a_id", "references": "EntidadA"}]})}}, request=httpx.Request("POST", "http://test/api/chat"))
            client = AsyncMock()
            client.post.return_value = response
            with patch("app.agents.local.interpreter.httpx.AsyncClient") as factory:
                factory.return_value.__aenter__.return_value = client
                result = await interpret_request(f"quiero crear una base de datos para un {domain} entonces como seriia la base de datos", context())
            self.assertEqual(client.post.call_args.kwargs["json"]["format"]["title"], "DesignSketch")
            self.assertEqual(result.intent, "explain_diagram")
            self.assertEqual(result.commands, [])
            self.assertIn("entidad_a_id (FK", result.answer)

    async def test_truncated_answer_has_specific_error(self):
        response = httpx.Response(200, json={"done_reason": "length", "message": {"content": '{"answer":'}}, request=httpx.Request("POST", "http://test/api/chat"))
        client = AsyncMock()
        client.post.return_value = response
        with patch("app.agents.local.interpreter.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            with self.assertRaises(LocalInferenceError) as caught:
                await interpret_request("Que es una clave?", context())
        self.assertEqual(caught.exception.code, "LOCAL_OUTPUT_TRUNCATED")

    async def test_remove_and_reconnect_extracts_replacement_not_deletion(self):
        output = RelationReplacementExtraction(relation_id="r1", old_participant="Cliente", new_participant="Venta")
        response = httpx.Response(200, json={"message": {"content": output.model_dump_json()}}, request=httpx.Request("POST", "http://test/api/chat"))
        client = AsyncMock()
        client.post.return_value = response
        ctx = context("Cliente", "Producto")
        ctx["diagrama"]["contenido"]["nodes"].append({"id": "v", "data": {"name": "Venta"}})
        ctx["diagrama"]["contenido"]["edges"] = [{"id": "r1", "source": "a", "target": "b", "data": {"relationType": "association"}}]
        with patch("app.agents.local.interpreter.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            parsed = await interpret_request("elimina la relacion con cliente y producto de muchos a muchos y relacionalo con venta y no con cliente", ctx)
        self.assertEqual(client.post.call_args.kwargs["json"]["format"]["title"], "RelationReplacementExtraction")
        self.assertEqual(parsed.commands[0].operation, "update_relation")
        result = build_plan(parsed, ctx)
        self.assertTrue(result.can_execute)
        self.assertEqual(result.actions[-1].tool, "update_relation")
        self.assertEqual(result.actions[-1].arguments["sourceName"], "Venta")
        self.assertFalse(any(a.tool == "delete_relation" for a in result.actions))

    async def test_native_request_sends_schema_and_bounded_context(self):
        output = ClassExtraction(operation="create_class", name="Reserva")
        response = httpx.Response(200, json={"message": {"content": output.model_dump_json()}}, request=httpx.Request("POST", "http://test/api/chat"))
        client = AsyncMock()
        client.post.return_value = response
        with patch("app.agents.local.interpreter.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            result = await interpret_request("Crea Reserva", context())
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["format"]["title"], "ClassExtraction")
        self.assertEqual(payload["options"]["temperature"], 0)
        self.assertEqual(result.commands[0].name, "Reserva")

    async def test_compiled_plan_runs_through_existing_executor(self):
        ctx = context()
        result = compile([Command(operation="create_relation", source="Producto", target="Venta", relation="associationClass", intermediate="DetalleVenta")], ctx)
        graph = deepcopy(ctx["diagrama"])

        async def create_class(diagram_id, body, token):
            graph["contenido"]["nodes"].append({"id": "real-middle", "data": body})
            return deepcopy(graph)

        async def create_relation(diagram_id, body, token):
            self.assertEqual(body["data"]["associationClassId"], "real-middle")
            graph["contenido"]["edges"].append({"id": "real-edge", **body})
            return deepcopy(graph)

        with patch("app.agents.diagram_agent.load_diagram_context", new_callable=AsyncMock, return_value=deepcopy(graph)), \
             patch("app.tools.diagram_tools.create_class", side_effect=create_class), \
             patch("app.tools.diagram_tools.create_relation", side_effect=create_relation):
            applied = await execute_plan(DiagramExecutePlanRequest(diagrama_id=1, actions=result.actions, confirmed=True), "test-token")
        self.assertTrue(applied.success)
        self.assertEqual(len(applied.diagrama["contenido"]["nodes"]), 3)
        self.assertEqual(len(applied.diagrama["contenido"]["edges"]), 1)
