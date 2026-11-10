from app.config.settings import settings
from contextlib import contextmanager
from contextvars import ContextVar
from app.providers.ollama_connection import get_ollama_api_key, get_ollama_base_url

_text_provider = ContextVar("text_provider", default=None)


@contextmanager
def select_text_provider(provider: str):
    if provider not in {"gemini", "local"}:
        raise ValueError("Proveedor de texto no permitido")
    token = _text_provider.set("litellm" if provider == "gemini" else "ollama")
    try:
        yield
    finally:
        _text_provider.reset(token)


def get_agent_provider(agent_name: str = "planner"):
    if agent_name == "image":
        return "litellm"
    if _text_provider.get() is not None:
        return _text_provider.get()
    provider = settings.AI_PROVIDER.strip().lower()
    if provider == "hybrid":
        return "litellm" if agent_name == "image" else "ollama"
    return provider


def get_agent_model_name(agent_name: str):
    models = {
        "planner": settings.PLANNER_MODEL,
        "diagram": settings.DIAGRAM_MODEL,
        "suggestion": settings.SUGGESTION_MODEL,
        "validation": settings.VALIDATION_MODEL,
        "codegen": settings.CODEGEN_MODEL,
        "image": settings.IMAGE_MODEL,
    }

    try:
        model = models[agent_name]
        if get_agent_provider(agent_name) == "ollama":
            return f"openai/{settings.OLLAMA_MODEL}"
        return model
    except KeyError as exc:
        valid_agents = ", ".join(models.keys())
        raise ValueError(f"Agente no configurado: {agent_name}. Agentes validos: {valid_agents}") from exc


def normalize_litellm_model(model_name: str):
    if model_name.startswith("litellm/"):
        return model_name.removeprefix("litellm/")

    return model_name


def get_litellm_api_key(model_name: str):
    if model_name.startswith("openai/") and get_agent_provider() == "ollama":
        return get_ollama_api_key()
    if model_name.startswith("gemini/"):
        return settings.GEMINI_API_KEY

    raise ValueError(
        f"Modelo no soportado: {model_name}. Configura un modelo con prefijo gemini/"
    )


def get_litellm_api_base(model_name: str | None = None):
    if model_name and model_name.startswith("gemini/"):
        return settings.LITELLM_API_BASE or None
    if get_agent_provider() == "ollama":
        return get_ollama_base_url()
    return settings.LITELLM_API_BASE


def get_image_fallback_models():
    # Never fall back to a paid cloud model in local mode.
    if get_agent_provider("image") == "ollama":
        return []
    return [normalize_litellm_model(item.strip())
            for item in settings.IMAGE_FALLBACK_MODELS.split(",") if item.strip()]


def get_agent_model(agent_name: str):
    provider = get_agent_provider(agent_name)
    model_name = get_agent_model_name(agent_name)

    if provider in {"litellm", "ollama"}:
        from agents.extensions.models.litellm_model import LitellmModel

        litellm_model_name = normalize_litellm_model(model_name)

        return LitellmModel(
            model=litellm_model_name,
            api_key=get_litellm_api_key(litellm_model_name),
            base_url=get_litellm_api_base(litellm_model_name),
        )

    raise ValueError(
        "Proveedor no soportado. Usa AI_PROVIDER=litellm u ollama"
    )
