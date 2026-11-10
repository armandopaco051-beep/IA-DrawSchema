import asyncio
import json
from contextlib import suppress
from secrets import compare_digest
from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.config.settings import settings
from app.services.worker_relay import WorkerConnection, WorkerRelayError, worker_relay, MAX_BYTES

router = APIRouter(tags=["Worker Ollama"])


def authorized(header, expected):
    return bool(expected and compare_digest(header.encode(), f"Bearer {expected}".encode()))


def enabled():
    return (settings.OLLAMA_TRANSPORT == "worker" and settings.OLLAMA_WORKER_TOKEN
            and settings.OLLAMA_BRIDGE_TOKEN and len(settings.OLLAMA_WORKER_TOKEN) >= 32
            and len(settings.OLLAMA_BRIDGE_TOKEN) >= 32 and settings.OLLAMA_WORKER_TOKEN != settings.OLLAMA_BRIDGE_TOKEN)


def worker_auth(authorization: str = Header(default="")):
    if not enabled():
        raise HTTPException(503, "Configura el transporte worker y sus dos tokens distintos")
    if not authorized(authorization, settings.OLLAMA_WORKER_TOKEN):
        raise HTTPException(401, "Token del worker inválido")


def bridge_auth(authorization: str = Header(default="")):
    if not enabled():
        raise HTTPException(503, "El transporte worker no está configurado")
    if not authorized(authorization, settings.OLLAMA_BRIDGE_TOKEN):
        raise HTTPException(401, "Token del puente inválido")


class WorkerHello(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    worker_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    model: str = Field(min_length=1, max_length=150)
    ready: bool


@router.get("/internal/worker/status", dependencies=[Depends(worker_auth)])
async def status():
    return worker_relay.status()


@router.websocket("/internal/worker/connect")
async def connect(socket: WebSocket):
    if not enabled() or not authorized(socket.headers.get("authorization", ""), settings.OLLAMA_WORKER_TOKEN):
        await socket.close(code=1008)
        return
    # No es un endpoint para navegadores: el token nunca debe ir al frontend.
    if socket.headers.get("origin"):
        await socket.close(code=1008)
        return
    await socket.accept()
    connection = None
    try:
        async with asyncio.timeout(10):
            hello = WorkerHello.model_validate(await socket.receive_json())
        if hello.type != "hello" or hello.model != settings.OLLAMA_MODEL or hello.model.endswith("-cloud"):
            await socket.close(code=1008, reason="Modelo o protocolo del worker incorrecto")
            return
        connection = WorkerConnection(hello.worker_id, hello.model, socket, hello.ready)
        await worker_relay.register(connection)
        await connection.send({"type": "welcome", "model": hello.model})
        while True:
            raw = await socket.receive_text()
            if len(raw.encode()) > MAX_BYTES:
                await socket.close(code=1009)
                break
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise ValueError("Mensaje inválido")
            worker_relay.receive(connection, message)
    except WebSocketDisconnect:
        pass
    except (ValueError, ValidationError, WorkerRelayError, TimeoutError, TypeError, RuntimeError):
        with suppress(RuntimeError, WebSocketDisconnect):
            await socket.close(code=1008)
    finally:
        if connection is not None:
            worker_relay.remove(connection)


@router.post("/internal/ollama/{path:path}", dependencies=[Depends(bridge_auth)])
async def bridge(path: str, body: dict):
    try:
        return await worker_relay.infer(path, body)
    except WorkerRelayError as exc:
        # Formato de error compatible con LiteLLM/OpenAI Agents.
        return JSONResponse(status_code=exc.status, content={"error": {
            "message": str(exc), "type": "local_worker_error", "code": exc.code}})
