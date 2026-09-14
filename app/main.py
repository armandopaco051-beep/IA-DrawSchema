import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agents.planner_agent import run_planner
from app.config.agents_models import get_agent_model_name
from app.config.settings import settings
from app.schemas.chat import ChatRequest, ChatResponse, PlannerRequest, PlannerResponse
from app.services.backend_client import get_diagrama, get_proyecto

from app.agents.diagram_agent import execute_plan
from app.schemas.diagram_execution import DiagramExecutePlanRequest, DiagramExecutePlanResponse


from app.agents.suggestion_agent import run_suggestion
from app.schemas.suggestion import SuggestionRequest, SuggestionResponse

app = FastAPI(
    title="DrawSchema AI Service",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def extract_token(authorization: str | None):
    if not authorization:
        return None

    if authorization.lower().startswith("bearer "):
        return authorization[7:]

    return authorization


async def build_context(
    proyecto_id: int | None,
    diagrama_id: int | None,
    token: str | None,
):
    context = {}

    try:
        if proyecto_id is not None:
            context["proyecto"] = await get_proyecto(proyecto_id, token)

        if diagrama_id is not None:
            context["diagrama"] = await get_diagrama(diagrama_id, token)

    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code

        try:
            detail = exc.response.json().get("detail", "No se pudo leer el contexto")
        except Exception:
            detail = "No se pudo leer el contexto"

        raise HTTPException(status_code=status_code, detail=detail) from exc

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo conectar con el backend principal",
        ) from exc

    return context


@app.get("/")
def inicio():
    return {
        "mensaje": "DrawSchema AI funcionando correctamente",
    }


@app.get("/health")
def health():
    return {
        "estado": "ok",
        "servicio": "DrawSchemaAI",
        "backend_principal": settings.BACKEND_API_URL,
        "proveedor": settings.AI_PROVIDER,
        "modelo_planner": get_agent_model_name("planner"),
        "modelo_diagram": get_agent_model_name("diagram"),
        "modelo_suggestion": get_agent_model_name("suggestion"),
        "modelo_validation": get_agent_model_name("validation"),
        "modelo_codegen": get_agent_model_name("codegen"),
    }


@app.post("/ai/chat", response_model=ChatResponse)
async def chat(datos: ChatRequest):
    return ChatResponse(
        respuesta=f"Recibi tu mensaje: {datos.message}",
        actions=[],
    )


# Endpoint para el planner
@app.post("/ai/planner", response_model=PlannerResponse)
async def planner(
    datos: PlannerRequest,
    authorization: str | None = Header(default=None),
):
    token = extract_token(authorization)
    context = await build_context(datos.proyecto_id, datos.diagrama_id, token)

    try:
        return await run_planner(datos.message, context)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error del proveedor IA: {exc}",
        ) from exc

# Endpoint para ejecutar un plan de diagrama
@app.post("/ai/diagram/execute-plan", response_model=DiagramExecutePlanResponse)
async def execute_diagram_plan(
    datos: DiagramExecutePlanRequest,
    authorization: str | None = Header(default=None),
):
    token = extract_token(authorization)
    return await execute_plan(datos, token)
    
    
@app.post("/ai/suggestions", response_model=SuggestionResponse)
async def suggestions(
    datos: SuggestionRequest,
    authorization: str | None = Header(default=None),
):
    token = extract_token(authorization)
    context = await build_context(datos.proyecto_id, datos.diagrama_id, token)

    try:
        return await run_suggestion(datos.message, context)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error del proveedor IA: {exc}",
        ) from exc