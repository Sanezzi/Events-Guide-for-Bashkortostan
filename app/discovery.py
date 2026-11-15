from datetime import datetime, timezone
import json
import os
import re
from email.utils import format_datetime
from html import escape
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from .dates import aware

router = APIRouter(include_in_schema=False)
SITE_TITLE = 'Афиша культуры Башкортостана'
DESCRIPTION = 'Концерты, спектакли, выставки, фестивали, кино и экскурсии в Башкортостане.'
PUBLIC_PAGES = ('/', '/about', '/docs')


def public_origin():
    value = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')
    try:
        parsed = urlsplit(value)
        if parsed.scheme == 'https' and parsed.hostname and not (
            parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
        ):
            return value
    except ValueError:
        pass
    return ''


def indexnow_key():
    key = os.environ.get('INDEXNOW_KEY', '')
    return key if re.fullmatch(r'[a-zA-Z0-9-]{8,128}', key) else None


def root_url(request):
    return public_origin() or str(request.base_url).rstrip('/')


def event_path(event):
    return f'/event?id={event.id}'


def is_fixture(event):
    return (
        (event.source_hash or '').startswith('demo-')
        or (event.dedup_key or '').startswith('demo-')
        or event.source_url.startswith('https://example.invalid/demo/')
    )


def publishable(events):
    return (event for event in events if event.status != 'черновик' and not is_fixture(event))


def safe_link(value):
    try:
        parsed = urlsplit(value or '')
        if parsed.scheme in ('https', 'http') and parsed.hostname and not (parsed.username or parsed.password):
            return value
    except ValueError:
        pass
    return None
