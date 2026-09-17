from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.chat import PlannerAction


class ValidationRequest(BaseModel):
    message: str = "Valida este diagrama UML"
    proyecto_id: int
    diagrama_id: int


class ValidationIssue(BaseModel):
    id: str
    severity: Literal["error", "warning", "info"]
    type: Literal[
        "diagram",
        "class",
        "attribute",
        "method",
        "relationship",
        "cardinality",
        "naming",
        "permission",
        "quality",
    ]
    title: str
    message: str
    nodeId: str | None = None
    edgeId: str | None = None
    suggested_action: PlannerAction | None = None


class ValidationResponse(BaseModel):
    summary: str
    valid: bool
    score: int = Field(ge=0, le=100)
    issues: list[ValidationIssue] = Field(default_factory=list)