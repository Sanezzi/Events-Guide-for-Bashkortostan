from collections import deque
from asyncio import Lock
from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import os
from secrets import token_urlsafe
import time

from fastapi import HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from ai_agent.schemas import AgentRequest, Message
from tg_bot.models.db import AppSetting


async def session_secret(database) -> bytes:
    configured = os.environ.get("SESSION_SECRET")
    if configured:
        return configured.encode()
    key = "session_secret"
    async with database.sessions() as session:
        row = await session.get(AppSetting, key)
        if row is not None:
            return row.value.encode()
        generated = token_urlsafe(48)
        session.add(AppSetting(key=key, value=generated))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            row = await session.get(AppSetting, key)
            if row is None:
                raise
            return row.value.encode()
        return generated.encode()


def require_bot(request: Request):
    expected = os.environ.get("INTERNAL_API_TOKEN", "")
    provided = request.headers.get("X-Internal-Token", "")
    if not expected or not hmac.compare_digest(expected.encode(), provided.encode()):
        raise HTTPException(401, "Нужен сервисный токен")
