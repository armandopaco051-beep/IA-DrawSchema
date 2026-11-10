from copy import deepcopy

import httpx

from app.services.plan_validation import prepare_association_actions

from app.schemas.diagram_execution import (
    DiagramExecutePlanRequest,
    DiagramExecutePlanResponse,
)
from app.tools.diagram_tools import execute_diagram_action, load_diagram_context


from app.services.rbac_guard import verify_user_permission


async def execute_plan(datos: DiagramExecutePlanRequest, token: str | None):
    executed = []

    if not token:
        return DiagramExecutePlanResponse(
            success=False,
            message="Token requerido para ejecutar el plan.",
            executed=[],
            diagrama=None,
        )

    pending_questions = [action for action in datos.actions if action.tool == "ask_user"]
    if pending_questions:
        return DiagramExecutePlanResponse(
            success=False,
            message="El plan todavía necesita una aclaración: " + " ".join(
                str(action.arguments.get("question") or action.arguments.get("message") or action.description)
                for action in pending_questions
            ),
            executed=[], failed_action=pending_questions[0], diagrama=None,
        )

    # Validar permisos RBAC si se proporciona el id del proyecto
    if datos.proyecto_id is not None:
        await verify_user_permission(datos.proyecto_id, token, min_role="EDITOR")


    for action in datos.actions:
        if action.requires_confirmation and not datos.confirmed:
            return DiagramExecutePlanResponse(
                success=False,
                message="El plan contiene acciones que requieren confirmacion.",
                executed=executed,
                failed_action=action,
                diagrama=None,
            )

    try:
        current_diagrama = await load_diagram_context(datos.diagrama_id, token)
        original_content = deepcopy(current_diagrama.get("contenido"))
        if datos.expected_version is not None and current_diagrama.get("version") != datos.expected_version:
            return DiagramExecutePlanResponse(
                success=False, message="El diagrama cambió desde esta respuesta. Solicita un plan actualizado.",
                executed=[], diagrama=current_diagrama,
            )

        prepared_actions, issues = prepare_association_actions(datos.actions, current_diagrama)
        if issues:
            return DiagramExecutePlanResponse(
                success=False, message=" ".join(issues), executed=[], diagrama=current_diagrama,
            )

        for action in sorted(prepared_actions, key=lambda item: item.order):
            current_diagrama, result = await execute_diagram_action(
                diagrama_id=datos.diagrama_id,
                autor_codigo=datos.autor_codigo,
                action=action,
                current_diagrama=current_diagrama,
                token=token,
            )
            executed.append(result)

        if not isinstance(current_diagrama, dict) or not isinstance(current_diagrama.get("contenido"), dict):
            return DiagramExecutePlanResponse(
                success=False, message="El backend no devolvió el contenido actualizado del diagrama. Recarga el diagrama antes de volver a aplicar el plan.",
                executed=executed, diagrama=None,
            )
        if current_diagrama["contenido"] == original_content:
            return DiagramExecutePlanResponse(
                success=False, message="No se detectaron cambios en el contenido del diagrama. El plan no produjo una modificación nueva.",
                executed=executed, diagrama=current_diagrama,
            )

        return DiagramExecutePlanResponse(
            success=True,
            message="Plan ejecutado correctamente.",
            executed=executed,
            diagrama=current_diagrama,
        )

    except ValueError as exc:
        return DiagramExecutePlanResponse(
            success=False,
            message=str(exc),
            executed=executed,
            diagrama=None,
        )

    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", "Error del backend principal")
        except Exception:
            detail = "Error del backend principal"

        return DiagramExecutePlanResponse(
            success=False,
            message=detail,
            executed=executed,
            diagrama=None,
        )
