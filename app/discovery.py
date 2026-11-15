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


def metadata(title, description, canonical, *, noindex=False, structured=None):
    tags = [
        f'<title>{escape(title)}</title>',
        f'<meta name="description" content="{escape(description, quote=True)}">',
        f'<link rel="canonical" href="{escape(canonical, quote=True)}">',
        '<link rel="alternate" type="application/rss+xml" title="Афиша культуры Башкортостана" href="/rss.xml">',
    ]
    if noindex:
        tags.append('<meta name="robots" content="noindex, follow">')
    if structured:
        data = json.dumps(structured, ensure_ascii=False).replace('<', '\\u003c')
        tags.append(f'<script type="application/ld+json">{data}</script>')
    return '\n'.join(tags)


def event_schema(event, canonical):
    data = {
        '@context': 'https://schema.org',
        '@type': 'Event',
        'name': event.title,
        'description': event.description,
        'url': canonical,
        'startDate': aware(event.date_start).isoformat(),
        'eventStatus': 'https://schema.org/EventCancelled' if event.status == 'отменено' else 'https://schema.org/EventScheduled',
        'eventAttendanceMode': 'https://schema.org/OfflineEventAttendanceMode',
        'location': {
            '@type': 'Place',
            'name': event.venue,
            'address': {
                '@type': 'PostalAddress',
                'addressLocality': event.city,
                'streetAddress': event.address,
                'addressCountry': 'RU',
            },
        },
    }
    if event.date_end:
        data['endDate'] = aware(event.date_end).isoformat()
    ticket_url = safe_link(event.org_link)
    if ticket_url and event.price_known and event.status != 'отменено':
        data['offers'] = {
            '@type': 'Offer' if event.price_min == event.price_max else 'AggregateOffer',
            'url': ticket_url, 'priceCurrency': 'RUB',
            **({'price': event.price_min} if event.price_min == event.price_max else {
                'lowPrice': event.price_min, 'highPrice': event.price_max,
            }),
        }
    return data


def price_text(event):
    if not event.price_known:
        return 'Уточняйте у организатора'
    if event.is_free or event.price_max == 0:
        return 'Бесплатно'
    if event.price_min == event.price_max:
        return f'{event.price_min:g} ₽'
    return f'{event.price_min:g} – {event.price_max:g} ₽'


def event_time(date):
    return aware(date).strftime('%d.%m.%Y, %H:%M')
