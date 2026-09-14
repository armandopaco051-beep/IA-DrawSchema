from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.chat import PlannerAction


class DiagramExecutePlanRequest(BaseModel):
    diagrama_id: int
    autor_codigo: str
    actions: list[PlannerAction] = Field(min_length=1)
    confirmed: bool = False


class DiagramActionResult(BaseModel):
    order: int
    tool: str
    success: bool
    message: str
    data: dict[str, Any] | None = None


class DiagramExecutePlanResponse(BaseModel):
    success: bool
    message: str
    executed: list[DiagramActionResult] = Field(default_factory=list)
    failed_action: PlannerAction | None = None
    diagrama: dict[str, Any] | None = None


class DiagramExecutionStatus(BaseModel):
    status: Literal["ready"]
    supported_tools: list[str]
