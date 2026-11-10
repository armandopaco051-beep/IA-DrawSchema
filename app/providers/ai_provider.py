import os

from agents import set_tracing_disabled

from app.config.settings import settings


def get_ai_provider():
    return settings.AI_PROVIDER.strip().lower()


def configure_ai_provider(agent_name: str = "planner"):
    from app.config.agents_models import get_agent_provider
    provider = get_agent_provider(agent_name)

    if provider == "ollama":
        if not settings.OLLAMA_BASE_URL.startswith(("http://", "https://")):
            raise RuntimeError("OLLAMA_BASE_URL debe ser una URL HTTP o HTTPS")
        if not settings.OLLAMA_MODEL.strip() or settings.OLLAMA_MODEL.endswith("-cloud"):
            raise RuntimeError("OLLAMA_MODEL debe indicar un modelo descargado localmente")
        os.environ.setdefault("OPENAI_AGENTS_ENABLE_LITELLM_SERIALIZER_PATCH", "true")
        set_tracing_disabled(True)
        return

    if provider != "litellm":
        raise RuntimeError(
            "Proveedor no soportado. Usa AI_PROVIDER=litellm u ollama"
        )

    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY no esta configurada en el archivo .env")

    os.environ.setdefault("GEMINI_API_KEY", settings.GEMINI_API_KEY)
    os.environ.setdefault("GOOGLE_API_KEY", settings.GEMINI_API_KEY)
    os.environ.setdefault("OPENAI_AGENTS_ENABLE_LITELLM_SERIALIZER_PATCH", "true")

    # OpenAI Agents se usa como orquestador; las inferencias se envian a Gemini.
    set_tracing_disabled(True)
