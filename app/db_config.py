import os
from urllib.parse import quote


def database_url() -> str:
    configured = os.environ.get("DATABASE_URL")
    if configured:
        for prefix in ("postgres://", "postgresql://"):
            if configured.startswith(prefix):
                return "postgresql+asyncpg://" + configured[len(prefix):]
        return configured
    if os.environ.get("POSTGRES_PASSWORD"):
        password = quote(os.environ["POSTGRES_PASSWORD"], safe="")
        return f"postgresql+asyncpg://afisha:{password}@db:5432/afisha"
    return "sqlite+aiosqlite:///./afisha.db"
