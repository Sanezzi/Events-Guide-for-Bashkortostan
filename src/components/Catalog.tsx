import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowDown, Search, SlidersHorizontal, X } from 'lucide-react'
import { AnimatePresence, LayoutGroup, motion } from 'motion/react'
import { api, capital, categories, getEvents, params, periods, type Category, type EventCard as Event, type EventResults, type Filters, type Period } from '../data/events'
import { criteria, parseQuery, readFilters } from '../data/search'
import { EventCard } from './EventCard'
import { pillSpring } from './Header'

const dateChips = [['', 'Все даты'], ...Object.entries(periods)]
const empty = { events: [], total: 0, explanation: null }

function relaxation(filters: Filters, reason?: string | null): { filters: Filters; label: string } | null {
  const budget = filters.is_free || filters.price_max !== undefined
  if (budget && (reason === 'price' || !filters.period && !filters.date_from || !filters.city)) {
    const price_max = filters.price_max === undefined || filters.price_max < 1500 ? 1500 : undefined
    return { filters: { ...filters, is_free: undefined, price_max }, label: price_max ? 'Расширить бюджет до 1 500 ₽' : 'Искать с любым бюджетом' }
  }
  if (filters.period || filters.date_from || filters.date_to) return { filters: { ...filters, period: undefined, date_from: undefined, date_to: undefined }, label: 'Посмотреть все даты' }
  if (filters.venue) return { filters: { ...filters, venue: undefined }, label: 'Посмотреть все площадки' }
  if (filters.category) return { filters: { ...filters, category: undefined }, label: 'Посмотреть все жанры' }
  if (filters.city) return { filters: { ...filters, city: undefined }, label: 'Искать по всей республике' }
  if (filters.text) return { filters: { ...filters, text: undefined }, label: 'Убрать ключевое слово' }
  if (filters.language) return { filters: { ...filters, language: undefined }, label: 'Посмотреть события на всех языках' }
  if (budget) return { filters: { ...filters, is_free: undefined, price_max: undefined }, label: 'Искать с любым бюджетом' }
  return null
}

export function Catalog({ cities, open }: { cities: string[]; open: (event: Event) => void }) {
  const [filters, setFilters] = useState(readFilters)
  const [query, setQuery] = useState(filters.text || '')
  const [recognized, setRecognized] = useState<string[]>([])
  const [data, setData] = useState<EventResults>(empty)
  const [venues, setVenues] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [retry, setRetry] = useState(0)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(false)
  const active = useRef(filters)

  function change(next: Filters) {
    active.current = next
    setFilters(next)
    const url = params(next)
    if (next.language) url.set('language', next.language)
    if (location.pathname === '/') history.replaceState(history.state, '', '/' + (url.size ? '?' + url : '') + location.hash)
  }

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setMore(false); setError('')
    getEvents(filters, 8, 0, controller.signal).then(setData).catch(e => {
      if (!controller.signal.aborted) setError(e.message)
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [filters, retry])

  useEffect(() => {
    const controller = new AbortController()
    setVenues([])
    const city = filters.city ? '?' + new URLSearchParams({ city: filters.city }) : ''
    api<{ venues: string[] }>('/api/v1/venues' + city, { signal: controller.signal }).then(result => setVenues(result.venues)).catch(() => {})
    return () => controller.abort()
  }, [filters.city])

  async function next() {
    setMore(true)
    try {
      const activeFilters = filters
      const result = await getEvents(activeFilters, 8, data.events.length)
      if (active.current === activeFilters) {
        setData(old => ({ ...result, events: [...old.events, ...result.events] }))
      }
    } catch (e) {
      if (active.current === filters) setError((e as Error).message)
    } finally {
      if (active.current === filters) setMore(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const parsed = parseQuery(query, cities)
    setRecognized(criteria(parsed))
    change({ ...parsed, sort: filters.sort })
  }
  const patch = (next: Filters) => { setRecognized([]); change({ ...filters, ...next }) }
  const reset = () => { setQuery(''); setRecognized([]); change({}) }
  const suggestion = relaxation(filters, data.explanation)
  const budget = filters.is_free ? 'free' : String(filters.price_max ?? '')

  return <section className="catalog wrap" id="catalog" aria-labelledby="catalog-title">
    <div className="section-head">
      <div><p className="eyebrow"><span className="hairline"/> СОБЫТИЯ РЕСПУБЛИКИ</p><h2 id="catalog-title">Афиша событий</h2></div>
      <p className="section-note">Концерты, спектакли, выставки и другие события по всему Башкортостану.</p>
    </div>
    <form className="catalog-search" onSubmit={submit} role="search">
      <Search size={21}/>
      <input aria-label="Поиск по афише" value={query} onChange={e => setQuery(e.target.value)} maxLength={250} placeholder="Название события или «куда сходить с ребёнком»" />
      <button className="button button-forest" type="submit">Найти</button>
    </form>
    {recognized.length > 0 && <p className="criteria" role="status">{recognized.map(item => <span key={item}>{item}</span>)}</p>}
    <div className="filter-bar">
      <LayoutGroup id="date-filter"><div className="chips" aria-label="Дата">
        {dateChips.map(([value, label]) => <button type="button" key={value} aria-pressed={(filters.period || '') === value} onClick={() => patch({ period: (value || undefined) as Period | undefined, date_from: undefined, date_to: undefined })}>
          {(filters.period || '') === value && <motion.span className="chip-active" layoutId="activePill" transition={pillSpring}/>}<span>{label}</span>
        </button>)}
      </div></LayoutGroup>
      <button className="button button-outline filter-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}><SlidersHorizontal size={17}/> {expanded ? 'Скрыть фильтры' : 'Фильтры'}</button>
    </div>
    <div className={`facet-panel ${expanded ? 'facet-expanded' : ''}`}>
      <label>Город<select aria-label="Город" value={filters.city || ''} onChange={e => patch({ city: e.target.value || undefined, venue: undefined })}><option value="">Все города</option>{cities.map(city => <option key={city}>{city}</option>)}</select></label>
      <label>Площадка<select aria-label="Площадка" value={filters.venue || ''} onChange={e => patch({ venue: e.target.value || undefined })}><option value="">Все площадки</option>{venues.map(venue => <option key={venue}>{venue}</option>)}</select></label>
      <label>Жанр<select aria-label="Жанр" value={filters.category || ''} onChange={e => patch({ category: (e.target.value || undefined) as Category | undefined })}><option value="">Все жанры</option>{categories.map(item => <option value={item} key={item}>{capital(item)}</option>)}<option value="другое">Другое</option></select></label>
      <label>Бюджет<select aria-label="Бюджет" value={budget} onChange={e => patch({ is_free: e.target.value === 'free' || undefined, price_max: e.target.value && e.target.value !== 'free' ? Number(e.target.value) : undefined })}><option value="">Любой</option><option value="free">Бесплатно</option>{[...new Set([500, 1500, ...(filters.price_max === undefined ? [] : [filters.price_max])])].sort((a, b) => a - b).map(n => <option value={n} key={n}>До {n} ₽</option>)}</select></label>
      <label>Возраст<select aria-label="Возраст" value={filters.age_limit ?? ''} onChange={e => patch({ age_limit: e.target.value === '' ? undefined : Number(e.target.value) })}><option value="">Любой</option>{[...new Set([0, 6, 12, 16, 18, ...(filters.age_limit === undefined ? [] : [filters.age_limit])])].sort((a, b) => a - b).map(n => <option value={n} key={n}>{n}+</option>)}</select></label>
    </div>
    {expanded && <div className="facet-panel facet-expanded facet-extra">
      <label>Дата с<input type="date" value={filters.date_from?.slice(0, 10) || ''} onChange={e => patch({ date_from: e.target.value ? e.target.value + 'T00:00:00+05:00' : undefined, period: undefined })}/></label>
      <label>Дата по<input type="date" value={filters.date_to?.slice(0, 10) || ''} onChange={e => patch({ date_to: e.target.value ? e.target.value + 'T23:59:59+05:00' : undefined, period: undefined })}/></label>
      <label>Сортировка<select value={filters.sort || 'date_start'} onChange={e => patch({ sort: e.target.value })}><option value="date_start">Ближайшие</option><option value="price_min">Сначала дешевле</option><option value="price_max_desc">Сначала дороже</option><option value="price_max">По верхней цене</option><option value="title">По названию</option></select></label>
      <label className="check-field"><input type="checkbox" checked={filters.language === 'ba'} onChange={e => patch({ language: e.target.checked ? 'ba' : undefined })}/> На башкирском</label>
    </div>}
    <div className="catalog-status" aria-live="polite">
      <span className="mono">{loading ? 'Ищем события…' : `Событий: ${data.total}`}</span>
      {Object.values(filters).some(v => v !== undefined) && <button className="text-button" onClick={reset}><X size={15}/> Сбросить</button>}
    </div>
    {error && <div className="state-panel" role="alert"><p>{error}</p><button className="button button-outline" onClick={() => setRetry(n => n + 1)}>Повторить</button></div>}
    {!error && <div className="ticket-grid" aria-busy={loading || more}>
      <AnimatePresence mode="popLayout">
        {loading ? Array.from({ length: 8 }, (_, i) => <motion.div className="ticket-skeleton" key={'skeleton' + i} exit={{ opacity: 0 }} aria-hidden="true"/>) : data.events.map((event, index) => <EventCard key={event.id} event={event} open={open} index={index}/>)}
      </AnimatePresence>
    </div>}
    {!loading && !error && !data.events.length && <div className="state-panel"><Search size={30}/><h3>Ничего не найдено</h3><p>{suggestion ? 'Попробуйте расширить поиск.' : 'По заданным условиям пока нет предстоящих событий.'}</p>
      {suggestion && <button className="button button-amber" onClick={() => { setRecognized([]); if (!suggestion.filters.text) setQuery(''); change(suggestion.filters) }}>{suggestion.label}</button>}
    </div>}
    {!loading && !error && data.events.length < data.total && <div className="load-more"><button className="button button-outline" disabled={more} onClick={next}>{more ? 'Загрузка…' : 'Показать ещё'} <ArrowDown size={17}/></button></div>}
  </section>
}
