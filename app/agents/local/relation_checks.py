"""Comprueba que el plan local cumple relaciones explícitas, sin crear planes fijos."""
import re
import unicodedata


def _text(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value)).casefold()
                   if not unicodedata.combining(c))


def relation_request_issues(message, plan, context):
    text = _text(message)
    many = bool(re.search(r"muchos?\s+a\s+muchos?|\bn\s*[:*-]\s*m\b|\bm\s*[:*-]\s*n\b", text))
    intermediate = bool(re.search(r"(?:clase|tabla)\s+(?:de\s+)?(?:asociacion|intermedia|puente)", text))
    if not many or not intermediate:
        return []
    # Solo exigimos acciones ante una petición de modificación, no una explicación.
    if not re.search(r"crea|agrega|relaciona|genera|anade|vincula", text):
        return []
    nodes = (((context or {}).get("diagrama") or {}).get("contenido") or {}).get("nodes", [])
    mentioned = {
        _text((node.get("data") or {}).get("name", "")) for node in nodes
        if (node.get("data") or {}).get("name") and re.search(
            r"(?<!\w)" + re.escape(_text(node["data"]["name"])) + r"(?!\w)", text)
    }
    if plan.questions or plan.intent == "needs_clarification":
        if len(mentioned) == 2:
            return ["Los dos participantes ya están identificados y la clase intermedia debe crearse. Prepara create_class y associationClass; no preguntes por conceptos UML, PK ni mínimos opcionales. Sin mínimos explícitos usa 0..* como convención editable."]
        return []
    relations = [a for a in plan.actions if a.tool in {"create_relation", "update_relation"}
                 and a.arguments.get("relationType") == "associationClass"]
    if not relations:
        return ["La petición requiere una relación muchos a muchos con clase intermedia: falta una acción associationClass; explicarla en summary no basta."]
    nodes = (((context or {}).get("diagrama") or {}).get("contenido") or {}).get("nodes", [])
    names = {_text((n.get("data") or {}).get("name", "")) for n in nodes}
    ids = {str(n.get("id")): _text((n.get("data") or {}).get("name", "")) for n in nodes}
    issues = []
    for relation in relations:
        args = relation.arguments
        name = _text(args.get("associationClassName", "")) or ids.get(str(args.get("associationClassId")), "")
        earlier = {_text(a.arguments.get("name", "")) for a in plan.actions
                   if a.tool == "create_class" and a.order < relation.order}
        if not name or name not in names | earlier:
            issues.append("La clase intermedia debe existir en el diagrama o crearse con create_class antes de associationClass.")
        for endpoint in ("source", "target"):
            participant = _text(args.get(endpoint + "Name", "")) or ids.get(str(args.get(endpoint + "ClassId") or args.get(endpoint)), "")
            if not participant or participant not in names | earlier:
                issues.append(f"El participante {endpoint} debe existir o crearse antes de la relación.")
            if name and participant == name:
                issues.append("La clase intermedia debe ser distinta de ambos participantes.")
            if args.get(endpoint + "Cardinality") not in {"0..*", "1..*"}:
                issues.append("Muchos a muchos requiere 0..* o 1..* en ambos extremos. Sin mínimos explícitos usa 0..* como convención editable, sin preguntar.")
    return list(dict.fromkeys(issues))
