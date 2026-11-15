"""Optional durable trace sink. Traces contain personal data; restrict access."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Protocol
from .schemas import AgentTrace


class TraceSinkProtocol(Protocol):
    async def save(self, trace: AgentTrace) -> None:
        """Persist a trace; implementations must apply retention and access policy."""
        ...


class JsonlTraceSink:
    """Append-only UTF-8 JSONL sink for a single host, with restrictive create mode.

    Intended for demos/small deployments. Use a DB or observability adapter for
    multiple hosts. The parent directory must exist and be trusted. Never serve
    this file publicly; it contains original user requests and tool arguments.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().absolute()
        self._lock = asyncio.Lock()

    async def save(self, trace: AgentTrace) -> None:
        payload = (trace.model_dump_json() + "\n").encode("utf-8")
        async with self._lock:
            await asyncio.to_thread(self._append, payload)

    def _append(self, payload: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.path, flags, 0o600)
        try:
            # A partial write is possible even to a regular file.
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written == 0:
                    raise OSError("Trace write made no progress")
                view = view[written:]
        finally:
            os.close(fd)
