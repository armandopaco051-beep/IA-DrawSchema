from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.chat import PlannerAction


class SuggestionRequest(BaseModel):
    message: str = "Sugiere mejoras para este diagrama"
    proyecto_id: int
    diagrama_id: int

# hace falta agregar mas campos al modelo de sugerencia
class DiagramSuggestion(BaseModel):
    id: str
    type: Literal[
        "relationship",
        "class",
        "attribute",
        "method",
        "naming",
        "warning",
    ]
    title: str
    message: str
    confidence: Literal["low", "medium", "high"] = "medium"
    action: PlannerAction | None = None


class SuggestionResponse(BaseModel):
    summary: str
    suggestions: list[DiagramSuggestion] = Field(default_factory=list)