import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import uuid4

request_id: ContextVar[str] = ContextVar("request_id", default="startup")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "request_id": request_id.get(),
                "event": getattr(record, "event", "runtime"),
                "error_type": getattr(record, "error_type", None),
            },
            ensure_ascii=False,
        )


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("uvicorn.access").disabled = True


def new_request_id() -> str:
    return uuid4().hex
