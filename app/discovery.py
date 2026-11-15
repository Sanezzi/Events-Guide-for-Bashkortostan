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


def detail_html(event):
    label = 'Бесплатно' if event.is_free else event.category
    fields = [
        ('Категория', event.category), ('Начало', event_time(event.date_start)),
        ('Город', event.city), ('Площадка', event.venue), ('Адрес', event.address),
        ('Цена', price_text(event)), ('Возрастное ограничение', f'{event.age_limit}+'),
        ('Статус', event.status),
    ]
    if event.date_end:
        fields.insert(2, ('Окончание', event_time(event.date_end)))
    rows = ''.join(f'<dt>{escape(label)}</dt><dd>{escape(value)}</dd>' for label, value in fields)
    source_url, ticket_url = safe_link(event.source_url), safe_link(event.org_link)
    links = []
    if source_url:
        links.append(f'<a class="btn" href="{escape(source_url, quote=True)}" target="_blank" rel="noopener">Источник события</a>')
    if ticket_url:
        links.append(f'<a class="btn ghost" href="{escape(ticket_url, quote=True)}" target="_blank" rel="noopener">Организатор / билеты</a>')
    notice = '<p><strong>Событие отменено.</strong></p>' if event.status == 'отменено' else ''
    badge_class = 'badge free' if event.is_free else 'badge'
    return (
        f'{notice}<span class="{badge_class}">{escape(label)}</span>'
        f'<h1>{escape(event.title)}</h1><p>{escape(event.description)}</p>'
        f'<dl>{rows}</dl><p>{" ".join(links)}</p>'
    )


def catalog_html(events):
    return ''.join(
        f'<article class="card"><div class="card-body"><span class="badge">{escape(event.category)}</span>'
        f'<h3><a href="{event_path(event)}">{escape(event.title)}</a></h3>'
        f'<time class="when" datetime="{aware(event.date_start).isoformat()}">{event_time(event.date_start)}</time>'
        f'<div class="where">{escape(event.city)} · {escape(event.venue)}</div>'
        f'<div class="price">{escape(price_text(event))} · {event.age_limit}+</div>'
        f'<p class="desc">{escape(event.description)}</p>'
        f'<div class="foot"><a class="btn" href="{event_path(event)}">Открыть</a></div></div></article>'
        for event in events
    )


@router.get('/robots.txt', response_class=PlainTextResponse)
def robots():
    rules = ['User-agent: *', 'Allow: /', 'Disallow: /admin', 'Disallow: /api/v1/admin',
             'Disallow: /agent/', 'Disallow: /api/chat', 'Disallow: /metrics', 'Disallow: /health',
             'Disallow: /static/*.html$']
    origin = public_origin()
    if origin:
        rules += ['', f'Sitemap: {origin}/sitemap.xml']
    return '\n'.join(rules) + '\n'


@router.get('/llms.txt', response_class=PlainTextResponse)
def llms(request: Request):
    base = root_url(request)
    return (
        f'# {SITE_TITLE}\n\n> {DESCRIPTION}\n\n'
        f'- [Каталог]({base}/)\n- [Карта сайта]({base}/sitemap.xml)\n'
        f'- [Лента событий]({base}/rss.xml)\n- [Документация API]({base}/docs)\n'
    )


@router.get('/{verification_file}.txt', response_class=PlainTextResponse)
def indexnow_verification(verification_file: str):
    key = indexnow_key()
    if not public_origin() or not key or verification_file != key:
        raise HTTPException(status_code=404, detail='Файл не найден')
    return key


def xml_response(root, media_type):
    return Response(ET.tostring(root, encoding='utf-8', xml_declaration=True), media_type=media_type)


@router.get('/sitemap.xml')
async def sitemap(request: Request):
    base = root_url(request)
    root = ET.Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    for path in PUBLIC_PAGES:
        ET.SubElement(ET.SubElement(root, 'url'), 'loc').text = base + path
    for event in publishable(await request.app.state.catalog.events()):
        entry = ET.SubElement(root, 'url')
        ET.SubElement(entry, 'loc').text = base + event_path(event)
        modified = event.updated_at or event.created_at
        if modified:
            ET.SubElement(entry, 'lastmod').text = aware(modified).isoformat()
    return xml_response(root, 'application/xml')
