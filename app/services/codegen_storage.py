from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from app.schemas.codegen import GeneratedFile


GENERATED_ROOT = Path("generated_projects")

#hace la parte 
def sanitize_relative_path(path: str):
    clean_path = Path(path.replace("\\", "/"))

    if clean_path.is_absolute() or ".." in clean_path.parts:
        raise ValueError(f"Ruta de archivo no permitida: {path}")

    return clean_path

#guarda lo generado 
def save_generated_project(project_name: str, files: list[GeneratedFile]):
    generation_id = f"gen-{uuid4().hex[:12]}"
    project_slug = project_name.strip().replace(" ", "-").lower() or "generated-backend"

    output_dir = GENERATED_ROOT / generation_id / project_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        relative_path = sanitize_relative_path(file.path)
        target_path = output_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(file.content, encoding="utf-8")

    zip_path = GENERATED_ROOT / generation_id / f"{project_slug}.zip"

    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zip_file:
        for target_file in output_dir.rglob("*"):
            if target_file.is_file():
                zip_file.write(
                    target_file,
                    target_file.relative_to(output_dir.parent),
                )

    return generation_id, zip_path

#genera el zip
def get_generated_zip_path(generation_id: str):
    generation_dir = GENERATED_ROOT / generation_id

    if not generation_dir.exists():
        return None

    zip_files = list(generation_dir.glob("*.zip"))

    if not zip_files:
        return None

    return zip_files[0]