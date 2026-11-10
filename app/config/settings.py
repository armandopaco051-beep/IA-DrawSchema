from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GEMINI_API_KEY: str | None = None
    LITELLM_API_BASE: str | None = None

    AI_PROVIDER: str = "litellm"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434/v1"
    OLLAMA_MODEL: str = "qwen2.5-coder:1.5b"
    OLLAMA_API_KEY: str = "ollama"
    OLLAMA_CONTEXT_SIZE: int = 8192
    OLLAMA_PLAN_TOKENS: int = 1536
    AI_REQUEST_TIMEOUT: float = 180.0

    PLANNER_MODEL: str = "gemini/gemini-3.5-flash-lite"
    DIAGRAM_MODEL: str = "gemini/gemini-3.5-flash-lite"
    SUGGESTION_MODEL: str = "gemini/gemini-3.5-flash-lite"
    VALIDATION_MODEL: str = "gemini/gemini-3.5-flash-lite"
    CODEGEN_MODEL: str = "gemini/gemini-3.5-flash-lite"
    IMAGE_MODEL: str = "gemini/gemini-3.5-flash-lite"
    IMAGE_FALLBACK_MODELS: str = ""

    IMAGE_MAX_BYTES: int = 10 * 1024 * 1024

    BACKEND_API_URL: str = "https://backendcopia-software.onrender.com/docs"
    FRONTEND_URL: str = "https://frontend-copia-software.vercel.app"
    #FRONTEND_URL: str = "http://localhos"
    #BACKEND_API_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
