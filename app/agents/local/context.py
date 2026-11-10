"""Contexto compacto utilizado exclusivamente por Ollama."""
import json


def build_local_input(message: str, context: dict | None = None):
    if not context:
        return message
    conversation = context.get("conversacion") or {}
    requester = context.get("solicitante") or conversation.get("solicitante")
    current = context.get("consulta_actual") or conversation.get("consulta_actual")
    diagram = context.get("diagrama") or {}
    content = diagram.get("contenido") or {}
    project = context.get("proyecto") or {}
    history = (context.get("conversacion") or {}).get("mensajes", [])
    return json.dumps({
        "solicitante": requester, "consulta_actual": current,
        "rol": context.get("user_role"),
        "proyecto": {k: project[k] for k in ("id", "nombre", "descripcion") if k in project},
        "diagrama_actual": {
            "id": diagram.get("id"), "nombre": diagram.get("nombre"), "version": diagram.get("version"),
            "nodes": [{k: n[k] for k in ("id", "data", "position") if k in n} for n in content.get("nodes", [])],
            "edges": [{k: e[k] for k in ("id", "source", "target", "data") if k in e} for e in content.get("edges", [])],
        },
        "historial_reciente": [
            {k: (m[k][:500] if k == "texto" else m[k]) for k in ("id", "rol", "autor_codigo", "autor_nombre", "texto") if k in m}
            for m in history[-6:] if not current or m.get("id") != current.get("id")
        ],
        "peticion_actual": message,
    }, ensure_ascii=False, separators=(",", ":"))
