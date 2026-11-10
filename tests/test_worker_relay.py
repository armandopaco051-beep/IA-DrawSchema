import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import httpx
from dotenv import dotenv_values

from app.config.settings import settings
from app.config.agents_models import select_text_provider, get_litellm_api_base, get_litellm_api_key
from app.providers.ollama_connection import native_chat
from app.routers.local_worker import router
from app.services.worker_relay import WorkerRelay, WorkerConnection, WorkerRelayError, worker_relay
from worker_local.main import WorkerSettings, local_ready, run_inference
from worker_local.setup import configure

WORKER_TOKEN, BRIDGE_TOKEN = "w" * 40, "b" * 40
MODEL = "qwen2.5-coder:1.5b"
BODY = {"model": MODEL, "messages": [{"role": "user", "content": "Texto privado de prueba"}], "stream": False}


class FakeSocket:
    def __init__(self):
        self.messages = asyncio.Queue()
        self.close = AsyncMock()

    async def send_json(self, message):
        await self.messages.put(message)


class RelayTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.relay = WorkerRelay()
        self.socket = FakeSocket()
        self.connection = WorkerConnection("pc-test", MODEL, self.socket, True)
        await self.relay.register(self.connection)
        self.patch = patch.object(settings, "OLLAMA_MODEL", MODEL)
        self.patch.start()

    async def asyncTearDown(self):
        self.relay.remove(self.connection)
        self.patch.stop()

    async def test_result_matches_request_and_is_not_stored_after_completion(self):
        task = asyncio.create_task(self.relay.infer("api/chat", BODY))
        message = await self.socket.messages.get()
        self.assertEqual(message["body"]["messages"], BODY["messages"])
        result = {"message": {"content": "respuesta"}}
        self.relay.receive(self.connection, {"type": "result", "id": message["id"], "result": result})
        self.assertEqual(await task, result)
        self.assertEqual(self.connection.pending, {})
        self.assertEqual(self.connection.waiting, 0)

    async def test_jobs_for_one_pc_run_serially(self):
        first = asyncio.create_task(self.relay.infer("api/chat", BODY))
        message = await self.socket.messages.get()
        second = asyncio.create_task(self.relay.infer("api/chat", BODY))
        await asyncio.sleep(0)
        self.assertTrue(self.socket.messages.empty())
        self.relay.receive(self.connection, {"type": "result", "id": message["id"], "result": {"n": 1}})
        self.assertEqual(await first, {"n": 1})
        next_message = await self.socket.messages.get()
        self.relay.receive(self.connection, {"type": "result", "id": next_message["id"], "result": {"n": 2}})
        self.assertEqual(await second, {"n": 2})

    async def test_disconnection_fails_pending_request_instead_of_hanging(self):
        task = asyncio.create_task(self.relay.infer("api/chat", BODY))
        await self.socket.messages.get()
        self.relay.remove(self.connection)
        with self.assertRaises(WorkerRelayError):
            await task

    async def test_cancellation_tells_local_worker_and_ignores_late_reply(self):
        task = asyncio.create_task(self.relay.infer("api/chat", BODY))
        message = await self.socket.messages.get()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        cancel = await self.socket.messages.get()
        self.assertEqual(cancel, {"type": "cancel", "id": message["id"]})
        self.relay.receive(self.connection, {"type": "result", "id": message["id"], "result": {"late": True}})
        self.assertFalse(self.connection.pending)

    async def test_offline_stale_or_wrong_model_does_not_accept_jobs(self):
        for field, value in (("ready", False), ("last_seen", 0), ("model", "different-model")):
            original = getattr(self.connection, field)
            setattr(self.connection, field, value)
            with self.assertRaises(WorkerRelayError):
                await self.relay.infer("api/chat", BODY)
            setattr(self.connection, field, original)

    async def test_reconnect_does_not_remove_replacement_connection(self):
        replacement = WorkerConnection("pc-test", MODEL, FakeSocket(), True)
        await self.relay.register(replacement)
        self.relay.remove(self.connection)
        self.assertIs(self.relay.workers["pc-test"], replacement)
        self.relay.remove(replacement)

    async def test_worker_native_transport_uses_relay(self):
        with patch.object(settings, "OLLAMA_TRANSPORT", "worker"), patch.object(settings, "OLLAMA_WORKER_TOKEN", WORKER_TOKEN), patch.object(settings, "OLLAMA_BRIDGE_TOKEN", BRIDGE_TOKEN), patch.object(worker_relay, "infer", new_callable=AsyncMock, return_value={"message": {"content": "ok"}}) as infer:
            response = await native_chat(BODY)
        self.assertEqual(response.json()["message"]["content"], "ok")
        infer.assert_awaited_once_with("api/chat", BODY)


class WorkerHttpIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(settings, "OLLAMA_TRANSPORT", "worker"), patch.object(settings, "OLLAMA_WORKER_TOKEN", WORKER_TOKEN), patch.object(settings, "OLLAMA_BRIDGE_TOKEN", BRIDGE_TOKEN), patch.object(settings, "OLLAMA_MODEL", MODEL)]
        for p in self.patches:
            p.start()
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):
            p.stop()

    def test_http_bridge_and_websocket_deliver_openai_response(self):
        with self.client as client:
            with client.websocket_connect("/internal/worker/connect", headers={"Authorization": f"Bearer {WORKER_TOKEN}"}) as ws:
                ws.send_json({"type": "hello", "worker_id": "test-pc", "model": MODEL, "ready": True})
                self.assertEqual(ws.receive_json()["type"], "welcome")
                with ThreadPoolExecutor(max_workers=1) as pool:
                    request = pool.submit(client.post, "/internal/ollama/v1/chat/completions", json=BODY, headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
                    job = ws.receive_json()
                    output = {"id": "chat-test", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}
                    ws.send_json({"type": "result", "id": job["id"], "result": output})
                    response = request.result(timeout=5)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), output)

    def test_role_tokens_cannot_be_interchanged(self):
        self.assertEqual(self.client.get("/internal/worker/status", headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"}).status_code, 401)
        self.assertEqual(self.client.post("/internal/ollama/api/chat", json=BODY, headers={"Authorization": f"Bearer {WORKER_TOKEN}"}).status_code, 401)
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/internal/worker/connect", headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"}):
                pass

    def test_offline_worker_has_useful_error(self):
        response = self.client.post("/internal/ollama/api/chat", json=BODY, headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "LOCAL_UNAVAILABLE")

    def test_sdk_worker_connection_preserves_gemini(self):
        with patch.dict("os.environ", {"PORT": "10000"}), select_text_provider("local"):
            self.assertEqual(get_litellm_api_base("openai/" + MODEL), "http://127.0.0.1:10000/internal/ollama/v1")
            self.assertEqual(get_litellm_api_key("openai/" + MODEL), BRIDGE_TOKEN)
            self.assertNotIn("internal/ollama", get_litellm_api_base("gemini/test") or "")


class LocalWorkerTest(unittest.IsolatedAsyncioTestCase):
    def config(self):
        return WorkerSettings(OLLAMA_WORKER_TOKEN=WORKER_TOKEN, OLLAMA_MODEL=MODEL, WORKER_SERVER_URL="https://iabackend-copia.onrender.com")

    async def test_worker_visits_only_fixed_local_ollama_and_preserves_schema(self):
        def handle(request):
            self.assertEqual(str(request.url), "http://127.0.0.1:11434/api/chat")
            self.assertEqual(json.loads(request.content)["format"], {"type": "object"})
            return httpx.Response(200, json={"message": {"content": "ok"}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await run_inference(self.config(), client, "api/chat", {**BODY, "format": {"type": "object"}})
            self.assertIn("message", result)
            with self.assertRaises(ValueError):
                await run_inference(self.config(), client, "../../diagram/execute-plan", BODY)

    async def test_readiness_requires_installed_model(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"models": [{"name": MODEL}]}))) as client:
            self.assertTrue(await local_ready(self.config(), client))

    async def test_setup_is_idempotent_and_does_not_export_gemini_key(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".env").write_text("GEMINI_API_KEY=do-not-export\nOLLAMA_MODEL=" + MODEL + "\n", encoding="utf-8")
            folder = configure(root=root)
            first = dotenv_values(folder / ".env")
            configure(root=root)
            self.assertEqual(first["OLLAMA_WORKER_TOKEN"], dotenv_values(folder / ".env")["OLLAMA_WORKER_TOKEN"])
            self.assertNotIn("do-not-export", (folder / "render.env").read_text())
            self.assertEqual(dotenv_values(root / ".env")["OLLAMA_TRANSPORT"], "direct")
