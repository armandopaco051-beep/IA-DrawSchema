from typing import Literal
from pydantic import BaseModel, Field

class CodegenRequest(BaseModel):
    proyecto_id: int
    diagrama_id: int
    message: str = "Genera un backend Spring Boot desde este diagrama"
    target: Literal["spring_boot"] = "spring_boot"
    project_name: str = "generated-backend"
    base_package: str = "com.drawschema.generated"
    database_name: str = "generated_db"


class GeneratedFile(BaseModel):
    path: str
    language: str
    content: str


class CodegenResponse(BaseModel):
    success: bool
    summary: str
    target: str = "spring_boot"
    project_name: str
    base_package: str
    database_name: str
    files: list[GeneratedFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generation_id: str | None = None
    download_url: str | None = None
