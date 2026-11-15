"""Extract event details from known organizer pages."""
from __future__ import annotations
import html, json, re, urllib.parse, urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo
from ai_agent.schemas import EventCard
from contour.tags import event_tags

TZ = ZoneInfo('Asia/Yekaterinburg')
AGES = (0, 6, 12, 16, 18)
MONTHS = {'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12,'январь':1,'февраль':2,'март':3,'апрель':4,'май':5,'июнь':6,'июль':7,'август':8,'сентябрь':9,'октябрь':10,'ноябрь':11,'декабрь':12}
CATEGORIES = ('концерт','спектакль','выставка','фестиваль','кино','экскурсия','другое')

def fold(s):
    return (s or '').casefold().replace('ё','е')

def strip_html(raw):
    raw = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', raw)
    raw = re.sub(r'(?s)<[^>]+>', '\n', raw)
    lines = [html.unescape(x).strip() for x in raw.splitlines()]
    return '\n'.join(x for x in lines if x)

def fetch_text(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 (contour-parser)'})
    with urllib.request.urlopen(req, timeout=12) as r:
        data = r.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("Source page is too large")
    return data.decode('utf-8', errors='replace')

def ddg_links(query, limit=10):
    url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(query)
    raw = fetch_text(url)
    out = []
    for m in re.finditer(r'uddg=([^&"\']+)', raw):
        link = urllib.parse.unquote(m.group(1))
        if link.startswith('http') and link not in out:
            out.append(link)
        if len(out) >= limit:
            break
    return out

def parse_age(text):
    m = re.search(r'(?<!\d)(0|6|12|16|18)\s*\+', text or '')
    return int(m.group(1)) if m else None

def parse_prices(text):
    t = fold(text or '')
    if re.search(r'бесплатн|вход свободный|свободный вход', t):
        return (0.0, 0.0, True)
    nums = [float(x.replace(' ', '').replace(',', '.')) for x in re.findall(r'(\d[\d ]{1,7})\s*(?:₽|руб)', text or '')]
    nums = [n for n in nums if 0 < n <= 100000]
    if not nums:
        return None  # unknown price: caller must NOT write 0 RUB
    return (min(nums), max(nums), False)
