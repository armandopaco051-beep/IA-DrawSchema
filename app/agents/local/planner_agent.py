from agents import Agent, AgentOutputSchema, ModelSettings

from app.config.agents_models import get_agent_model, select_text_provider
from app.config.settings import settings
from app.providers.ai_provider import configure_ai_provider
from .rules import LOCAL_RULES
from app.services.plan_grounding import grounding_issues
from app.services.plan_validation import prepare_association_actions
from .relation_checks import relation_request_issues
from .interpreter import interpret_request, INSTRUCTIONS
from .plan_builder import build_plan

from .commands import Interpretation


def create_planner_agent():
    with select_text_provider("local"):
        return Agent(
            name="Local Planner Agent",
            instructions=LOCAL_RULES + "\n" + INSTRUCTIONS,
            model=get_agent_model("planner"),
            output_type=AgentOutputSchema(Interpretation, strict_json_schema=False),
            model_settings=ModelSettings(
                temperature=0.1,
                max_tokens=1536,
                extra_args={"timeout": settings.AI_REQUEST_TIMEOUT, "num_retries": 0},
            ),
        )


async def _run_planner(message: str, context: dict | None = None):
    configure_ai_provider("planner")

    parsed = await interpret_request(message, context)
    plan = build_plan(parsed, context)
    issues = grounding_issues(message, plan, context) + relation_request_issues(message, plan, context)
    if issues:
        parsed = await interpret_request(message, context, correction=issues)
        plan = build_plan(parsed, context)
        issues = grounding_issues(message, plan, context) + relation_request_issues(message, plan, context)
        if issues:
            plan = plan.model_copy(update={
                "intent": "needs_clarification", "actions": [], "can_execute": False,
                "summary": "La interpretación local no coincide con la petición. No se aplicaron cambios.",
                "questions": ["No pude interpretar de forma fiable los participantes y el cambio solicitado."],
            })
    conversation = (context or {}).get("conversacion") or {}
    requester = (context or {}).get("solicitante") or conversation.get("solicitante") or {}
    if conversation.get("tipo") == "grupal" and requester.get("nombre"):
        # Explicit recipient even if the model omits their name in its prose.
        name = str(requester["nombre"]).strip()
        if not plan.summary.casefold().startswith(name.casefold() + ","):
            plan = plan.model_copy(update={"summary": f"{name}, {plan.summary}"})
    actions, issues = prepare_association_actions(plan.actions, (context or {}).get("diagrama"))
    # ask_user no es un cambio aplicable al lienzo.
    issues.extend(str(action.arguments.get("question") or action.arguments.get("message") or action.description)
                  for action in actions if action.tool == "ask_user")
    return plan.model_copy(update={
        "actions": actions,
        "questions": list(dict.fromkeys([*plan.questions, *issues])),
        "can_execute": plan.can_execute and bool(actions) and not issues and not plan.questions,
    })


async def run_planner(message: str, context: dict | None = None):
    with select_text_provider("local"):
        return await _run_planner(message, context)
