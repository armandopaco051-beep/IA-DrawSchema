import os
import httpx
from app.config.settings import settings


def get_ollama_base_url():
    if settings.OLLAMA_TRANSPORT == "worker":
        return (settings.OLLAMA_BRIDGE_BASE_URL or
                f"http://127.0.0.1:{os.environ.get('PORT', '8000')}/internal/ollama/v1").rstrip("/")
    return settings.OLLAMA_BASE_URL.rstrip("/")


def get_ollama_api_key():
    return settings.OLLAMA_BRIDGE_TOKEN if settings.OLLAMA_TRANSPORT == "worker" else settings.OLLAMA_API_KEY


def validate_worker_config():
    if settings.OLLAMA_TRANSPORT == "worker":
        if (not settings.OLLAMA_WORKER_TOKEN or not settings.OLLAMA_BRIDGE_TOKEN
                or settings.OLLAMA_WORKER_TOKEN == settings.OLLAMA_BRIDGE_TOKEN):
            raise RuntimeError("Configura OLLAMA_WORKER_TOKEN y OLLAMA_BRIDGE_TOKEN con valores distintos")


async def native_chat(payload):
    if settings.OLLAMA_TRANSPORT == "worker":
        validate_worker_config()
        from app.services.worker_relay import worker_relay
        data = await worker_relay.infer("api/chat", payload)
        return httpx.Response(200, json=data, request=httpx.Request("POST", "http://worker/api/chat"))
    base = get_ollama_base_url().removesuffix("/v1")
    headers = {"Authorization": f"Bearer {settings.OLLAMA_API_KEY}"} if settings.OLLAMA_API_KEY else {}
    async with httpx.AsyncClient(timeout=settings.AI_REQUEST_TIMEOUT) as client:
        response = await client.post(base + "/api/chat", headers=headers, json=payload)
        response.raise_for_status()
    return response
