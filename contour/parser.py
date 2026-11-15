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

def parse_datetime(text, year=None):
    m = re.search(r'(\d{1,2})\s+(' + '|'.join(MONTHS) + r')(?:\s+(\d{4}))?[^0-9]{0,20}?(\d{1,2}):(\d{2})', fold(text or ''), re.I)
    if not m:
        return None
    try:
        return datetime(int(m.group(3) or year or datetime.now(TZ).year),
                        MONTHS[m.group(2)], int(m.group(1)), int(m.group(4)), int(m.group(5)), tzinfo=TZ)
    except ValueError:
        return None

def parse_duration(text):
    m = re.search(r'(\d+)\s*ч(?:\.|ас)?\s*(\d{1,2})?\s*мин', fold(text or ''))
    if m:
        return int(m.group(1)) * 60 + int(m.group(2) or 0)
    m = re.search(r'длительность[^0-9]{0,10}(\d+)\s*мин', fold(text or ''))
    return int(m.group(1)) if m else None

def slugify(s):
    s = fold(s)
    s = re.sub(r'[^0-9a-zа-я]+', '-', s).strip('-')
    return s[:60] or 'event'

def deterministic_id(source_url, title, dt):
    return str(uuid5(NAMESPACE_URL, source_url + '|' + fold(title) + '|' + dt.isoformat()))

def build_fragment(*, title, city, venue, address, source_url, page_text, category='другое', tags=None, description=None, year=None):
    """Build one fragment dict or return None. _verified is set only when
    date, price AND age are all present in page_text (full match rule)."""
    dt = parse_datetime(page_text, year=year)
    if dt is None or dt <= datetime.now(TZ):
        return None
    prices = parse_prices(page_text)
    age = parse_age(page_text)
    verified = prices is not None and age is not None
    if not verified:
        return None
    price_min, price_max, is_free = prices
    dur = parse_duration(page_text)
    item = {
        'id': deterministic_id(source_url, title, dt),
        'title': title.strip(),
        'category': category if category in CATEGORIES else 'другое',
        'tags': event_tags(title, description or "", category, age, is_free, tags or ()),
        'date_start': dt.isoformat(),
        'date_end': (dt + timedelta(minutes=dur)).isoformat() if dur else None,
        'duration_min': dur,
        'city': city, 'venue': venue, 'address': address,
        'description': (description or title).strip()[:12000],
        'price_min': price_min, 'price_max': price_max, 'is_free': is_free,
        'age_limit': age,
        'source_url': source_url,
        'status': 'опубликовано',
        'dedup_key': slugify(city) + '-' + dt.strftime('%Y-%m-%dT%H:%M') + '-' + slugify(venue) + '-' + slugify(title),
        '_verified': bool(verified),
    }
    EventCard.model_validate_json(json.dumps({k: v for k, v in item.items() if k != '_verified'}, ensure_ascii=False))
    return item

def dedup(items):
    seen, out = set(), []
    for e in items:
        k = e.get('dedup_key') or (fold(e['title']), e['date_start'], fold(e['venue']))
        if k in seen:
            continue
        seen.add(k); out.append(e)
    return out

def collect_official_page(url, city, venue, address, title, **kw):
    text = strip_html(fetch_text(url))
    return build_fragment(title=title, city=city, venue=venue, address=address, source_url=url, page_text=text, **kw)


def source_link(base, link):
    if not isinstance(link, str) or not link.strip():
        return None
    try:
        url = urllib.parse.urlsplit(urllib.parse.urljoin(base, link.strip()))
        host = url.hostname
    except ValueError:
        return None
    if url.scheme not in {"http", "https"} or not host or url.username or url.password:
        return None
    return url._replace(fragment="").geturl()


class ListingLinks(HTMLParser):
    def __init__(self, page_url):
        super().__init__()
        self.page_url = page_url
        self.host = urllib.parse.urlsplit(page_url).hostname
        self.links = {}

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        link = source_link(self.page_url, dict(attrs).get("href"))
        if not link:
            return
        target = urllib.parse.urlsplit(link)
        if target.hostname == self.host and re.search(r"/(?:afisha|event|events|show)/[^/]+", target.path):
            self.links.setdefault(link, None)


def event_page_links(raw, page_url):
    parser = ListingLinks(page_url)
    parser.feed(raw)
    return [url for url in parser.links if url.rstrip("/") != page_url.rstrip("/")][:30]
