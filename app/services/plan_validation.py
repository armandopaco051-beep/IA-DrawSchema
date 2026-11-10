import re

from app.schemas.chat import PlannerAction


def prepare_association_actions(actions: list[PlannerAction], diagram: dict | None = None):
    """Resolve only explicitly named association classes, never guess a junction."""
    prepared = [action.model_copy(deep=True) for action in actions]
    names = {
        str((node.get("data") or {}).get("name", ""))
        for node in ((diagram or {}).get("contenido") or {}).get("nodes", [])
    }
    names.discard("")
    nodes = ((diagram or {}).get("contenido") or {}).get("nodes", [])
    # Política del editor: una asociación N:M debe visualizar su intermedia.
    expanded = []
    available = {str((n.get("data") or {}).get("name", "")).casefold() for n in nodes}
    for action in sorted(prepared, key=lambda item: item.order):
        args = action.arguments
        if action.tool == "create_class":
            available.add(str(args.get("name", "")).casefold())
        if action.tool in {"create_relation", "update_relation"} and args.get("relationType") == "association" and all(args.get(k) in {"0..*", "1..*"} for k in ("sourceCardinality", "targetCardinality")):
            args["relationType"] = "associationClass"
            if not args.get("associationClassId"):
                def endpoint_name(endpoint):
                    return args.get(endpoint + "Name") or next((
                        (n.get("data") or {}).get("name") for n in nodes
                        if str(n.get("id")) == str(args.get(endpoint) or args.get(endpoint + "ClassId"))
                    ), None)
                source_name, target_name = endpoint_name("source"), endpoint_name("target")
                middle = args.get("associationClassName")
                if not middle and source_name and target_name:
                    middle = f"Vinculo{source_name}{target_name}"
                if middle:
                    args["associationClassName"] = middle
                    if str(middle).casefold() not in available:
                        expanded.append(PlannerAction(order=0, tool="create_class", description=f"Crear clase intermedia {middle}", arguments={"name": middle, "attributes": [], "methods": []}))
                        available.add(str(middle).casefold())
        expanded.append(action)
    prepared = [a.model_copy(update={"order": i}) for i, a in enumerate(expanded, 1)]
    existing_names = {str((node.get("data") or {}).get("name", "")).casefold() for node in nodes}
    created_classes = {}

    def participant(arguments, endpoint):
        node_id = arguments.get(endpoint) or arguments.get(endpoint + "ClassId")
        name = str(arguments.get(endpoint + "Name", "")).casefold()
        return next((node for node in nodes if (
            node_id and node.get("id") == node_id
        ) or (name and str((node.get("data") or {}).get("name", "")).casefold() == name)), None)

    issues = []
    for action in sorted(prepared, key=lambda item: item.order):
        args = action.arguments
        if action.tool == "create_class" and args.get("name"):
            names.add(str(args["name"]))
            created_classes[str(args["name"]).casefold()] = action
        if action.tool not in {"create_relation", "update_relation"}:
            continue
        if args.get("relationType") != "associationClass":
            continue
        if not args.get("associationClassId") and not args.get("associationClassName"):
            # An explicit unique name in the action description can recover a
            # missing field. Existing/planned classes without that evidence cannot.
            candidates = [name for name in names if re.search(
                r"(?<!\w)" + re.escape(name) + r"(?!\w)", action.description, re.IGNORECASE,
            ) and name.casefold() not in {
                str(args.get("sourceName", "")).casefold(),
                str(args.get("targetName", "")).casefold(),
            }]
            if len(candidates) == 1:
                args["associationClassName"] = candidates[0]
            else:
                issues.append(
                    f"Indica la clase de asociación para {args.get('sourceName', 'origen')} "
                    f"y {args.get('targetName', 'destino')} mediante associationClassName. "
                    "Si no existe, debe crearse antes de la relación."
                )
        if args.get("associationClassName") and names and not any(
            name.casefold() == str(args["associationClassName"]).casefold() for name in names
        ):
            issues.append(f"La clase de asociación {args['associationClassName']} no existe ni se crea antes de la relación.")
        association_name = str(args.get("associationClassName", "")).casefold()
        creation = created_classes.get(association_name)
        if creation and association_name not in existing_names:
            source, target = participant(args, "source"), participant(args, "target")
            if source and target:
                source_position, target_position = source.get("position") or {}, target.get("position") or {}
                # Match createAssociationClassNode in EstudiantePage.tsx.
                creation.arguments["x"] = (source_position.get("x", 120) + target_position.get("x", 120)) / 2
                creation.arguments["y"] = min(source_position.get("y", 110), target_position.get("y", 110)) - 170
    return prepared, issues
