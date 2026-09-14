from typing import Any

from app.schemas.chat import PlannerAction
from app.schemas.diagram_execution import DiagramActionResult
from app.services.backend_client import create_class, create_relation, get_diagrama

#va ser el conjunto de herramientas que se pueden usar en el diagrama
SUPPORTED_TOOLS_V1 = {
    "create_class",
    "create_relation",
    "update_class",
    "delete_class",
    "move_class",
    "update_relation",
    "delete_relation",
}


VALID_RELATION_TYPES = {
    "association",
    "generalization",
    "composition",
    "aggregation",
    "associationClass",
    "realization",
    "templateBinding",
}


VALID_CARDINALITIES = {
    "1",
    "0..1",
    "0..*",
    "1..*",
}

# hace la extraccion de los nodos del diagrama
def get_nodes(diagrama: dict[str, Any]):
    contenido = diagrama.get("contenido") or {}
    nodes = contenido.get("nodes") or []
    return nodes if isinstance(nodes, list) else []

# hace la busqueda de una clase por nombre
def find_class_by_name(diagrama: dict[str, Any], class_name: str):
    expected = class_name.strip().lower()

    for node in get_nodes(diagrama):
        data = node.get("data") or {}
        name = str(data.get("name") or "").strip().lower()

        if name == expected:
            return node

    return None

# hace la normalizacion de los atributos
def normalize_attributes(arguments: dict[str, Any]):
    attributes = arguments.get("attributes", [])
    return attributes if isinstance(attributes, list) else []


# hace la normalizacion de los metodos
def normalize_methods(arguments: dict[str, Any]):
    methods = arguments.get("methods", [])
    return methods if isinstance(methods, list) else []


# hace la construccion del body para crear una clase
def build_create_class_body(arguments: dict[str, Any], autor_codigo: str):
    name = str(arguments.get("name") or "").strip()

    if not name:
        raise ValueError("create_class necesita arguments.name")

    return {
        "id": arguments.get("id"),
        "name": name,
        "x": arguments.get("x", 100),
        "y": arguments.get("y", 100),
        "attributes": normalize_attributes(arguments),
        "methods": normalize_methods(arguments),
        "autor_codigo": autor_codigo,
    }


# hace la construccion del body para crear una relacion
def build_create_relation_body(
    arguments: dict[str, Any],
    diagrama: dict[str, Any],
    autor_codigo: str,
):
    relation_type = arguments.get("relationType", "association")

    if relation_type not in VALID_RELATION_TYPES:
        raise ValueError(f"Tipo de relacion no permitido: {relation_type}")

    source_id = arguments.get("source") or arguments.get("sourceClassId")
    target_id = arguments.get("target") or arguments.get("targetClassId")

    if not source_id and arguments.get("sourceName"):
        source_node = find_class_by_name(diagrama, str(arguments["sourceName"]))

        if source_node is None:
            raise ValueError(f"No se encontro la clase origen: {arguments['sourceName']}")

        source_id = source_node["id"]

    if not target_id and arguments.get("targetName"):
        target_node = find_class_by_name(diagrama, str(arguments["targetName"]))

        if target_node is None:
            raise ValueError(f"No se encontro la clase destino: {arguments['targetName']}")

        target_id = target_node["id"]

    if not source_id or not target_id:
        raise ValueError("create_relation necesita source/target o sourceName/targetName")

    source_cardinality = arguments.get("sourceCardinality", "1")
    target_cardinality = arguments.get("targetCardinality", "0..*")

    if source_cardinality not in VALID_CARDINALITIES:
        raise ValueError(f"Cardinalidad origen no permitida: {source_cardinality}")

    if target_cardinality not in VALID_CARDINALITIES:
        raise ValueError(f"Cardinalidad destino no permitida: {target_cardinality}")

    data = {
        "relationType": relation_type,
        "sourceClassId": source_id,
        "targetClassId": target_id,
        "sourceCardinality": source_cardinality,
        "targetCardinality": target_cardinality,
    }

    for optional_key in (
        "sourceRole",
        "targetRole",
        "associationClassId",
        "templateBindings",
        "name",
    ):
        if optional_key in arguments:
            data[optional_key] = arguments[optional_key]

    return {
        "id": arguments.get("id"),
        "source": source_id,
        "target": target_id,
        "type": "umlRelation",
        "data": data,
        "autor_codigo": autor_codigo,
    }


# hace la ejecucion de la accion en el diagrama
async def execute_diagram_action(
    diagrama_id: int,
    autor_codigo: str,
    action: PlannerAction,
    current_diagrama: dict[str, Any],
    token: str | None,
):
    if action.tool not in SUPPORTED_TOOLS_V1:
        raise ValueError(f"Tool no soportada en Diagram Agent V1: {action.tool}")

    if action.tool == "create_class":
        body = build_create_class_body(action.arguments, autor_codigo)
        diagrama = await create_class(diagrama_id, body, token)

        return diagrama, DiagramActionResult(
            order=action.order,
            tool=action.tool,
            success=True,
            message=f"Clase creada: {body['name']}",
            data={"className": body["name"]},
        )

    if action.tool == "create_relation":
        body = build_create_relation_body(action.arguments, current_diagrama, autor_codigo)
        diagrama = await create_relation(diagrama_id, body, token)

        return diagrama, DiagramActionResult(
            order=action.order,
            tool=action.tool,
            success=True,
            message=f"Relacion creada: {body['source']} -> {body['target']}",
            data={
                "source": body["source"],
                "target": body["target"],
                "relationType": body["data"]["relationType"],
            },
        )

    raise ValueError(f"Tool no implementada: {action.tool}")


async def load_diagram_context(diagrama_id: int, token: str | None):
    return await get_diagrama(diagrama_id, token)
