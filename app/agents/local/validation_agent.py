from agents import Agent, AgentOutputSchema, ModelSettings, Runner

from app.config.agents_models import get_agent_model, select_text_provider
from app.config.settings import settings
from app.providers.ai_provider import configure_ai_provider
from app.schemas.validation import ValidationResponse
from .context import build_local_input
from .rules import LOCAL_RULES


INSTRUCTIONS = """
Eres el agente de validación UML. Responde en español con ValidationResponse: summary, valid, score e issues. Evalúa SOLO las clases y relaciones del diagrama actual, no ejemplos ni diagramas históricos. Los nombres pertenecen al dominio del usuario; no exijas entidades fijas. Comprueba extremos existentes, duplicados, ciclos de herencia, multiplicidades y clase de asociación válida. Generalización: hija a padre sin multiplicidades. Realización: implementadora a interfaz sin multiplicidades. Composición: Todo a Parte; como máximo un Todo por Parte. No deduzcas composición solo por nombres. Si faltan requisitos, indica incertidumbre; no inventes reglas de negocio. Cada issue lleva id, severity (error/warning/info), type, title y message. type: diagram/class/attribute/method/relationship/cardinality/naming/permission/quality. No ejecutes cambios. valid=false si hay errores o si no hay clases. score entre 0 y 100.
"""


def create_validation_agent():
    with select_text_provider("local"):
        return Agent(
            name="Local Validation Agent",
            instructions=LOCAL_RULES + "\n" + INSTRUCTIONS,
            model=get_agent_model("validation"),
            output_type=AgentOutputSchema(ValidationResponse, strict_json_schema=False),
            model_settings=ModelSettings(
                temperature=0.1,
                
                extra_args={"timeout": settings.AI_REQUEST_TIMEOUT, "num_retries": 0},
            ),
        )


async def run_validation(message: str, context: dict | None = None):
    with select_text_provider("local"):
        configure_ai_provider("validation")
        result = await Runner.run(create_validation_agent(), build_local_input(message, context))
    return result.final_output
