from agents import Agent, AgentOutputSchema, ModelSettings, Runner

from app.config.agents_models import get_agent_model, select_text_provider
from app.config.settings import settings
from app.providers.ai_provider import configure_ai_provider
from app.schemas.codegen import CodegenResponse
from .context import build_local_input
from .rules import LOCAL_RULES


INSTRUCTIONS = """
Eres el Codegen Agent de DrawSchema. Genera Spring Boot desde las clases y relaciones actuales, sin copiar entidades de ejemplos.
Devuelve CodegenResponse: success, summary, target, project_name, base_package, database_name, files y warnings.
Cada archivo tiene path, language y content con código real, sin cercas Markdown. Respeta la configuración recibida.
Usa Java 17, Spring Web, Data JPA, PostgreSQL, Lombok y Validation. Genera models, repositories, services, controllers, dto, exceptions y config.
Incluye pom.xml, Application, README.md, database.sql y application.properties para la base recibida, con ddl-auto=update.
Cada entidad necesita CRUD completo con POST/GET/PUT/DELETE /api/{entidad-plural}, y GET por id. Conserva atributos y métodos del diagrama.
Mapea BIGINT a Long, INT a Integer, VARCHAR/TEXT a String, DECIMAL/NUMERIC a BigDecimal, DATE a LocalDate y BOOLEAN a Boolean.
primaryKey implica @Id. nullable=false implica @NotBlank en String y @NotNull en otros tipos. Sin PK genera id Long y advierte.
Los métodos adicionales van en Service; si falta lógica del negocio, deja TODO y warning.
Mapea multiplicidades a OneToOne/OneToMany/ManyToOne/ManyToMany. Composición usa cascade ALL y orphanRemoval; agregación no borra en cascada.
Clase de asociación: entidad intermedia con EmbeddedId compuesto por ambas PK, dos ManyToOne con MapsId y CRUD que resuelva ambas entidades.
Generalización usa extends y estrategia JPA de herencia. Ante ambigüedad advierte y genera código seguro.
No declares éxito si faltan archivos necesarios ni presentes una salida incompleta como proyecto terminado.
"""


def create_codegen_agent():
    with select_text_provider("local"):
        return Agent(
            name="Local Codegen Agent",
            instructions=LOCAL_RULES + "\n" + INSTRUCTIONS,
            model=get_agent_model("codegen"),
            output_type=AgentOutputSchema(CodegenResponse, strict_json_schema=False),
            model_settings=ModelSettings(
                temperature=0.1,
                
                extra_args={"timeout": settings.AI_REQUEST_TIMEOUT, "num_retries": 0},
            ),
        )


async def run_codegen(message: str, context: dict, project_name: str,
                      base_package: str, database_name: str):
    import json
    payload = json.dumps({
        "configuracion_generacion": {
            "project_name": project_name, "base_package": base_package,
            "database_name": database_name,
        },
        "contexto": build_local_input(message, context),
    }, ensure_ascii=False)
    with select_text_provider("local"):
        configure_ai_provider("codegen")
        result = await Runner.run(create_codegen_agent(), payload)
    return result.final_output
