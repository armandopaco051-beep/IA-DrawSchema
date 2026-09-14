import httpx

from app.config.settings import settings

#esta parte del archivo permita que el backend IA lea datos del backend principal
def build_headers(token: str | None = None):
    headers = {
        "Content-Type": "application/json",
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


async def get_diagrama(diagrama_id: int, token: str | None = None):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{settings.BACKEND_API_URL}/diagramas/{diagrama_id}",
            headers=build_headers(token),
        )
        response.raise_for_status()
        return response.json()


async def get_proyecto(proyecto_id: int, token: str | None = None):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{settings.BACKEND_API_URL}/proyectos/{proyecto_id}",
            headers=build_headers(token),
        )
        response.raise_for_status()
        return response.json()

#
async def create_class(diagrama_id: int, body: dict, token: str | None = None):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.BACKEND_API_URL}/diagramas/{diagrama_id}/clases",
            json=body,
            headers=build_headers(token),
        )
        response.raise_for_status()
        return response.json()


async def create_relation(diagrama_id: int, body: dict, token: str | None = None):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.BACKEND_API_URL}/diagramas/{diagrama_id}/relaciones",
            json=body,
            headers=build_headers(token),
        )
        response.raise_for_status()
        return response.json()
