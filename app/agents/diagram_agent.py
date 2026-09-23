import httpx

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

        for action in sorted(datos.actions, key=lambda item: item.order):
            current_diagrama, result = await execute_diagram_action(
                diagrama_id=datos.diagrama_id,
                autor_codigo=datos.autor_codigo,
                action=action,
                current_diagrama=current_diagrama,
                token=token,
            )
            executed.append(result)

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