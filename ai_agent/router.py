"""Optional FastAPI integration; the application owns service construction."""
from __future__ import annotations

try:
    from fastapi import APIRouter, Depends, HTTPException, Request
except ModuleNotFoundError as exc:
    if exc.name != "fastapi":
        raise
    raise ImportError("FastAPI integration requires the optional fastapi dependency") from exc

from .agent import CultureAgentService
from .schemas import AgentRequest, AgentResponse

router = APIRouter(prefix="/agent", tags=["culture-agent"])


def get_service(request: Request) -> CultureAgentService:
    """Override this dependency or set app.state.ai_agent_service at startup.

    The host must derive/validate request.user_id from its authenticated principal;
    this standalone router deliberately does not invent an authentication system.
    """
    service = getattr(request.app.state, "ai_agent_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Culture agent service is not configured")
    return service


@router.post("/message", response_model=AgentResponse)
async def agent_message(payload: AgentRequest,
                        service: CultureAgentService = Depends(get_service)) -> AgentResponse:
    return await service.handle_message(payload)


@router.get("/health")
async def health(service: CultureAgentService = Depends(get_service)) -> dict[str, str]:
    return {"status": "ok", "mode": "llm" if service.settings.api_key.strip() else "offline"}
