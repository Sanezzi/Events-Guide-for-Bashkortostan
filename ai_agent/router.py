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
