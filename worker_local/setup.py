"""Configura secretos locales sin mostrarlos ni modificar el servicio desplegado."""
import argparse
from pathlib import Path
import secrets
from dotenv import dotenv_values, set_key
from .main import WorkerSettings

ROOT = Path(__file__).resolve().parents[1]


def configure(root=ROOT, server_url="https://iabackend-copia.onrender.com"):
    env_path = root / ".env"
    local = dotenv_values(env_path)
    worker_token = local.get("OLLAMA_WORKER_TOKEN") or secrets.token_urlsafe(32)
    bridge_token = local.get("OLLAMA_BRIDGE_TOKEN") or secrets.token_urlsafe(32)
    if len(worker_token) < 32 or len(bridge_token) < 32 or worker_token == bridge_token:
        raise ValueError("Los tokens existentes deben ser distintos y tener al menos 32 caracteres")
    model = local.get("OLLAMA_MODEL") or "qwen2.5-coder:1.5b"
    config = WorkerSettings(WORKER_SERVER_URL=server_url, OLLAMA_WORKER_TOKEN=worker_token, OLLAMA_MODEL=model)
    folder = root / "worker_local"
    folder.mkdir(exist_ok=True)
    for key, value in {"OLLAMA_WORKER_TOKEN": worker_token, "OLLAMA_BRIDGE_TOKEN": bridge_token}.items():
        set_key(str(env_path), key, value, quote_mode="never")
    # Mantiene el modo directo en desarrollo; el export para Render habilita worker.
    if not local.get("OLLAMA_TRANSPORT"):
        set_key(str(env_path), "OLLAMA_TRANSPORT", "direct", quote_mode="never")
    for key, value in {
        "WORKER_SERVER_URL": config.WORKER_SERVER_URL,
        "OLLAMA_WORKER_TOKEN": worker_token, "OLLAMA_MODEL": model,
    }.items():
        set_key(str(folder / ".env"), key, value, quote_mode="never")
    values = {
        "OLLAMA_TRANSPORT": "worker", "OLLAMA_WORKER_TOKEN": worker_token,
        "OLLAMA_BRIDGE_TOKEN": bridge_token, "OLLAMA_MODEL": model,
        "AI_REQUEST_TIMEOUT": "600",
        "BACKEND_API_URL": local.get("BACKEND_API_URL", "https://backendcopia-software.onrender.com").rstrip("/").removesuffix("/docs"),
        "FRONTEND_URL": local.get("FRONTEND_URL", "https://frontend-copia-software.vercel.app"),
    }
    (folder / "render.env").write_text(
        "# PRIVADO: copiar variables al servicio de IA en Render; no subir a Git.\n"
        + "\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
    return folder


def main():
    parser = argparse.ArgumentParser(description="Preparar worker y variables de Render")
    parser.add_argument("--server-url", default="https://iabackend-copia.onrender.com")
    args = parser.parse_args()
    folder = configure(server_url=args.server_url)
    print("Configuración creada; no se muestran secretos.")
    print("Copia las variables de", folder / "render.env", "al servicio IA de Render y vuelve a desplegarlo.")
    print("Luego ejecuta: .\\venv\\Scripts\\python.exe -m worker_local.main --check")
    print("Para iniciar: .\\venv\\Scripts\\python.exe -m worker_local.main")


if __name__ == "__main__":
    main()
