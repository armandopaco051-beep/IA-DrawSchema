"""Ejecutar desde la raíz: python -m worker_local.main"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import socket
from urllib.parse import urlsplit, urlunsplit
import httpx
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

MAX_BYTES = 2 * 1024 * 1024
ALLOWED_PATHS = {"api/chat", "v1/chat/completions"}


class WorkerSettings(BaseSettings):
    WORKER_SERVER_URL: str = "https://iabackend-copia.onrender.com"
    OLLAMA_WORKER_TOKEN: SecretStr = Field(min_length=32)
    OLLAMA_MODEL: str = "qwen2.5-coder:1.5b"
    OLLAMA_URL: str = "http://127.0.0.1:11434"
    WORKER_ID: str = Field(default_factory=lambda: re.sub(r"[^a-zA-Z0-9_.-]", "_", socket.gethostname())[:90])
    WORKER_HEARTBEAT_SECONDS: float = Field(default=10, ge=2, le=30)
    WORKER_INFERENCE_TIMEOUT: float = Field(default=540, ge=5, le=1800)
    model_config = SettingsConfigDict(env_file=Path(__file__).with_name(".env"), extra="ignore", hide_input_in_errors=True)

    @field_validator("WORKER_SERVER_URL")
    @classmethod
    def validate_server(cls, value):
        url = urlsplit(value)
        if url.username or url.password or url.query or url.fragment or not url.hostname:
            raise ValueError("URL del servicio IA inválida")
        if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise ValueError("Usa HTTPS para el servidor desplegado")
        return value.rstrip("/")

    @field_validator("OLLAMA_URL")
    @classmethod
    def validate_local_ollama(cls, value):
        url = urlsplit(value)
        if (url.hostname not in {"localhost", "127.0.0.1", "::1"} or url.scheme not in {"http", "https"}
                or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}):
            raise ValueError("OLLAMA_URL debe apuntar al Ollama de esta computadora")
        return value.rstrip("/")

    @field_validator("WORKER_ID")
    @classmethod
    def validate_id(cls, value):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", value):
            raise ValueError("WORKER_ID inválido")
        return value

    @field_validator("OLLAMA_MODEL")
    @classmethod
    def validate_model(cls, value):
        if not value.strip() or value.endswith("-cloud"):
            raise ValueError("Usa un modelo descargado localmente")
        return value.strip()

    @property
    def websocket_url(self):
        url = urlsplit(self.WORKER_SERVER_URL)
        return urlunsplit(("wss" if url.scheme == "https" else "ws", url.netloc,
                           url.path.rstrip("/") + "/internal/worker/connect", "", ""))


async def local_ready(config, client):
    try:
        response = await client.get(config.OLLAMA_URL + "/api/tags", timeout=5)
        response.raise_for_status()
        names = {str(item.get("name") or item.get("model") or "").removesuffix(":latest") for item in response.json().get("models", [])}
        return config.OLLAMA_MODEL.removesuffix(":latest") in names
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return False


async def run_inference(config, client, path, body, timeout=None):
    if path not in ALLOWED_PATHS or not isinstance(body, dict) or body.get("stream"):
        raise ValueError("Trabajo de inferencia inválido")
    if str(body.get("model", "")).removeprefix("openai/") != config.OLLAMA_MODEL:
        raise ValueError("El modelo solicitado no coincide con el configurado")
    if len(json.dumps(body).encode()) > MAX_BYTES:
        raise ValueError("La petición supera el límite permitido")
    # La nube nunca proporciona una URL para que el PC la visite.
    async with client.stream("POST", config.OLLAMA_URL + "/" + path,
                             json={**body, "model": config.OLLAMA_MODEL, "stream": False},
                             timeout=timeout or config.WORKER_INFERENCE_TIMEOUT) as response:
        response.raise_for_status()
        raw = bytearray()
        async for chunk in response.aiter_bytes():
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise ValueError("La respuesta supera el límite permitido")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Respuesta local inválida")
    return data


async def connected_session(config, ws, client):
    send_lock, tasks = asyncio.Lock(), {}

    async def send(data):
        async with send_lock:
            await ws.send(json.dumps(data, ensure_ascii=False))

    await send({"type": "hello", "worker_id": config.WORKER_ID, "model": config.OLLAMA_MODEL,
                "ready": await local_ready(config, client)})

    async def heartbeat():
        while True:
            await asyncio.sleep(config.WORKER_HEARTBEAT_SECONDS)
            await send({"type": "heartbeat", "ready": await local_ready(config, client)})

    async def infer(message):
        answer = {"type": "result", "id": message["id"]}
        try:
            result = await run_inference(config, client, message["path"], message["body"])
            answer["result"] = result
        except httpx.TimeoutException:
            answer["error"] = "LOCAL_TIMEOUT"
        except httpx.HTTPError:
            answer["error"] = "LOCAL_UNAVAILABLE"
        except (ValueError, KeyError, TypeError):
            answer["error"] = "LOCAL_INVALID_RESPONSE"
        await send(answer)

    def finished(request_id, task):
        tasks.pop(request_id, None)
        if not task.cancelled():
            task.exception()  # Consume errores de conexión; el bucle reconectará.

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        async for raw in ws:
            message = json.loads(raw)
            if message.get("type") == "welcome":
                print("Worker conectado. Las consultas se procesan en Ollama local.", flush=True)
            elif message.get("type") == "cancel":
                if message.get("id") in tasks:
                    tasks[message["id"]].cancel()
            elif message.get("type") == "infer":
                request_id = message.get("id")
                if not isinstance(request_id, str) or len(request_id) > 100 or request_id in tasks:
                    raise ValueError("Identificador de trabajo inválido")
                if any(not t.done() for t in tasks.values()):
                    await send({"type": "result", "id": request_id, "error": "LOCAL_UNAVAILABLE"})
                    continue
                task = asyncio.create_task(infer(message))
                tasks[request_id] = task
                task.add_done_callback(lambda t, rid=request_id: finished(rid, t))
    finally:
        heartbeat_task.cancel()
        running = list(tasks.values())
        for task in running:
            task.cancel()
        await asyncio.gather(heartbeat_task, *running, return_exceptions=True)


async def check(config):
    async with httpx.AsyncClient() as client:
        ready = await local_ready(config, client)
        print("Ollama y modelo:", "disponibles" if ready else "NO disponibles", flush=True)
        try:
            response = await client.get(config.WORKER_SERVER_URL + "/internal/worker/status",
                                        headers={"Authorization": "Bearer " + config.OLLAMA_WORKER_TOKEN.get_secret_value()}, timeout=75)
        except httpx.HTTPError:
            print("El servicio IA desplegado no respondió a la comprobación. Revisa que Render haya terminado de desplegar y vuelve a intentar.")
            return False
        if response.status_code == 404:
            print("El servicio desplegado todavía no incluye el worker. Vuelve a desplegar DrawSchemaAI.")
            return False
        if response.status_code in {401, 503}:
            print("Revisa OLLAMA_TRANSPORT y los tokens en Render; el token local debe coincidir.")
            return False
        response.raise_for_status()
        status = response.json()
        print("Servicio IA:", config.WORKER_SERVER_URL)
        print("Modelo del servidor:", status.get("model"))
        print("Workers conectados:", len(status.get("workers", [])))
        return ready and status.get("model") == config.OLLAMA_MODEL


async def run(config):
    delay = 2
    async with httpx.AsyncClient() as client:
        print("Conectando con", config.WORKER_SERVER_URL, "— modelo:", config.OLLAMA_MODEL, flush=True)
        while True:
            try:
                async with websockets.connect(config.websocket_url,
                        additional_headers={"Authorization": "Bearer " + config.OLLAMA_WORKER_TOKEN.get_secret_value()},
                        ping_interval=20, ping_timeout=20, open_timeout=75, max_size=MAX_BYTES, compression=None) as ws:
                    delay = 2
                    await connected_session(config, ws, client)
            except InvalidStatus as exc:
                print(f"Conexión rechazada (HTTP {exc.response.status_code}). Revisa despliegue, transporte y token.", flush=True)
            except ConnectionClosed as exc:
                if exc.rcvd and exc.rcvd.code == 1008:
                    print("El servidor rechazó el modelo o el protocolo. Comprueba OLLAMA_MODEL en Render y en worker_local/.env.", flush=True)
                else:
                    print("Conexión interrumpida; reintentando sin perder el historial guardado.", flush=True)
            except (OSError, TimeoutError, ValueError):
                print("Conexión interrumpida; reintentando sin perder el historial guardado.", flush=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


def main():
    parser = argparse.ArgumentParser(description="Worker Ollama para DrawSchemaAI")
    parser.add_argument("--check", action="store_true", help="Comprobar configuración y despliegue")
    args = parser.parse_args()
    try:
        config = WorkerSettings()
        if args.check:
            raise SystemExit(0 if asyncio.run(check(config)) else 1)
        asyncio.run(run(config))
    except KeyboardInterrupt:
        print("Worker detenido.")
    except Exception as exc:
        # No imprimir configuración ni mensajes del modelo: pueden contener datos privados.
        print(f"No se pudo iniciar el worker ({type(exc).__name__}). Revisa worker_local/.env y usa --check.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
