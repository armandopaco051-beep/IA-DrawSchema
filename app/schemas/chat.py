from typing import Any, Literal

from pydantic import BaseModel, Field

#define que json entra y que json sale 
PlannerToolName = Literal[
    "create_class",
    "update_class",
    "delete_class",
    "move_class",
    "create_relation",
    "update_relation",
    "delete_relation",
    "ask_user",
]


class PlannerRequest(BaseModel):
    message: str = Field(min_length=1)
    diagrama_id: int | None = None
    proyecto_id: int | None = None
    user_role: str | None = None

class PlannerAction(BaseModel):
    order: int
    tool: PlannerToolName
    description: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False

class PlannerResponse(BaseModel):
    intent: Literal[
        "modify_diagram",
        "explain_diagram",
        "suggest_model",
        "validate_model",
        "generate_code",
        "needs_clarification",
    ]
    summary: str
    actions: list[PlannerAction] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    can_execute: bool = False

class ChatRequest(BaseModel):
    message: str
    diagrama_id: int | None = None
    proyecto_id: int | None = None


class ChatResponse(BaseModel): 
    respuesta : str
    actions : list[PlannerAction] = Field (default_factory = list)

