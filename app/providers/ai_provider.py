import os

from app.config.settings import settings


def get_ai_provider():
    return settings.AI_PROVIDER.strip().lower()


def configure_ai_provider():
    provider = get_ai_provider()

    if provider == "openai":
        if settings.OPENAI_API_KEY:
            os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)
            return

        raise RuntimeError("OPENAI_API_KEY no esta configurada en el archivo .env")

    if provider == "litellm":
        if settings.OPENAI_API_KEY:
            os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

        if settings.GEMINI_API_KEY:
            os.environ.setdefault("GEMINI_API_KEY", settings.GEMINI_API_KEY)
            os.environ.setdefault("GOOGLE_API_KEY", settings.GEMINI_API_KEY)

        if not settings.GEMINI_API_KEY and not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "Configura GEMINI_API_KEY u OPENAI_API_KEY en el archivo .env para usar LiteLLM"
            )

        os.environ.setdefault("OPENAI_AGENTS_ENABLE_LITELLM_SERIALIZER_PATCH", "true")
        return

    raise RuntimeError(f"Proveedor IA no soportado: {settings.AI_PROVIDER}")
