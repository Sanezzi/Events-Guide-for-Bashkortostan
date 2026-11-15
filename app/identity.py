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


def web_identity(request: Request, response: Response) -> str:
    secret = request.app.state.session_secret

    def signature(value):
        return hmac.new(secret, value.encode(), sha256).hexdigest()

    cookie = request.cookies.get("afisha_id", "")
    identifier, _, signed = cookie.partition(".")
    if len(identifier) != 32 or not hmac.compare_digest(signature(identifier), signed):
        identifier = token_urlsafe(24)
        response.set_cookie("afisha_id", f"{identifier}.{signature(identifier)}", httponly=True,
                            secure=request.url.scheme == "https", samesite="strict", max_age=30 * 86400)
    return f"web:{identifier}"


def bot_identity(user_id: str) -> str:
    return f"tg:{user_id}"


@dataclass
class Dialogue:
    history: deque = field(default_factory=lambda: deque(maxlen=12))
    touched: float = field(default_factory=time.monotonic)
    lock: Lock = field(default_factory=Lock)


class Dialogues:
    def __init__(self, agent):
        self.agent = agent
        self.sessions = {}

    async def ask(self, user_id, session_id, message, confirmation=None):
        key = user_id, session_id
        now = time.monotonic()
        if len(self.sessions) >= 10000:
            for old, state in list(self.sessions.items()):
                if now - state.touched >= 3600 and not state.lock.locked():
                    self.sessions.pop(old, None)
            if key not in self.sessions and len(self.sessions) >= 10000:
                raise HTTPException(429, "Сервис занят, попробуйте позже")
        state = self.sessions.setdefault(key, Dialogue())
        state.touched = now
        async with state.lock:
            reply = await self.agent.handle_message(AgentRequest(
                session_id=session_id, user_id=user_id, message=message,
                history=list(state.history), confirm_action=confirmation is not None,
                confirmation_version=confirmation,
            ))
            state.history.extend((Message(role="user", content=message),
                                  Message(role="assistant", content=reply.reply_text)))
            return reply
