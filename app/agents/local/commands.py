"""Contrato pequeño: Ollama interpreta; el compilador construye las acciones."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Attribute(BaseModel):
    name: str
    type: str | None = None
    primaryKey: bool | None = None
    foreignKey: bool | None = None
    nullable: bool | None = None


class Parameter(BaseModel):
    name: str
    type: str


class Method(BaseModel):
    name: str
    returnType: str = "void"
    parameters: list[Parameter] = Field(default_factory=list)


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["create_class", "update_class", "delete_class", "move_class",
                       "create_relation", "update_relation", "delete_relation"]
    name: str | None = None
    new_name: str | None = None
    attributes: list[Attribute] = Field(default_factory=list)
    remove_attributes: list[str] = Field(default_factory=list)
    rename_attributes: dict[str, str] = Field(default_factory=dict)
    methods: list[Method] = Field(default_factory=list)
    remove_methods: list[str] = Field(default_factory=list)
    rename_methods: dict[str, str] = Field(default_factory=dict)
    source: str | None = None
    target: str | None = None
    relation: Literal["association", "associationClass", "aggregation", "composition",
                      "generalization", "realization", "templateBinding"] | None = None
    source_cardinality: Literal["1", "0..1", "0..*", "1..*"] | None = None
    target_cardinality: Literal["1", "0..1", "0..*", "1..*"] | None = None
    intermediate: str | None = None
    relation_id: str | None = None
    old_participant: str | None = None
    new_participant: str | None = None
    x: float | None = None
    y: float | None = None
    kind: Literal["class", "interface"] | None = None
    template_parameters: list[str] = Field(default_factory=list)
    template_bindings: dict[str, str] = Field(default_factory=dict)


class Interpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["modify_diagram", "explain_diagram", "suggest_model", "validate_model",
                    "generate_code", "needs_clarification"]
    answer: str = ""
    commands: list[Command] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
