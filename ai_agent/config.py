"""Explicit settings; no dotenv loading, clients or network calls at import time."""
import os
from pydantic import BaseModel, ConfigDict, Field
from zoneinfo import ZoneInfo


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    api_key: str = Field(default="", repr=False)
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timezone: str = "Asia/Yekaterinburg"
    timeout_seconds: float = Field(default=12, gt=0, le=120)
    max_output_tokens: int = Field(default=800, ge=64, le=4096)
    input_usd_per_million: float = Field(default=0.15, ge=0)
    output_usd_per_million: float = Field(default=0.60, ge=0)
    request_budget_usd: float = Field(default=0.03, ge=0)
    session_budget_usd: float = Field(default=0.25, ge=0)
    user_daily_budget_usd: float = Field(default=1, ge=0)
    requests_per_minute: int = Field(default=20, ge=1)
    repository_timeout_seconds: float = Field(default=5, gt=0)
    confirmation_ttl_seconds: int = Field(default=300, ge=1)
    transfer_buffer_min: int = Field(default=30, ge=0)

    @classmethod
    def from_env(cls) -> "AgentSettings":
        names = {
            "api_key": "LLM_API_KEY", "base_url": "LLM_BASE_URL", "model": "LLM_MODEL",
            "timezone": "AGENT_TIMEZONE", "timeout_seconds": "LLM_TIMEOUT_SECONDS",
            "max_output_tokens": "LLM_MAX_OUTPUT_TOKENS",
            "input_usd_per_million": "LLM_INPUT_USD_PER_MILLION",
            "output_usd_per_million": "LLM_OUTPUT_USD_PER_MILLION",
            "request_budget_usd": "AGENT_REQUEST_BUDGET_USD",
            "session_budget_usd": "AGENT_SESSION_BUDGET_USD",
            "user_daily_budget_usd": "AGENT_USER_DAILY_BUDGET_USD",
            "requests_per_minute": "AGENT_REQUESTS_PER_MINUTE",
        }
        result = cls(**{key: os.environ[name] for key, name in names.items() if name in os.environ})
        ZoneInfo(result.timezone)
        return result
