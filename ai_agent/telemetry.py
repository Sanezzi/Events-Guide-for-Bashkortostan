from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Protocol
from .schemas import AgentTrace


class TraceSinkProtocol(Protocol):
    async def save(self, trace: AgentTrace) -> None:
        ...


class JsonlTraceSink:

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
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written == 0:
                    raise OSError("Trace write made no progress")
                view = view[written:]
        finally:
            os.close(fd)
