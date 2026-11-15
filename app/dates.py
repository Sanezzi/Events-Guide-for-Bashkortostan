from datetime import datetime
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo("Asia/Yekaterinburg")


def aware(value: datetime) -> datetime:
    return value if value.utcoffset() is not None else value.replace(tzinfo=LOCAL_TIMEZONE)
