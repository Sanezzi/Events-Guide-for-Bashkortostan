import { useState, type FormEvent } from 'react'
import { ArrowRight, CalendarDays, Clock3, MapPin, Route as RouteIcon } from 'lucide-react'
import { motion } from 'motion/react'
import { date as displayDate, day, money, price, time, type EventCard } from '../data/events'
import { nextRouteDays, searchDay, type Route } from '../data/planner'
import { OrnamentDivider } from './OrnamentDivider'

export function Planner({ cities, open }: { cities: string[]; open: (event: EventCard) => void }) {
  const [city, setCity] = useState('Стерлитамак')
  const [date, setDate] = useState(() => day(new Date()))
  const [budget, setBudget] = useState('')
  const [from, setFrom] = useState('00:00')
  const [to, setTo] = useState('23:59')
  const [busy, setBusy] = useState(false)
  const [route, setRoute] = useState<Route | null>(null)
  const [explanation, setExplanation] = useState('')
  const [alternatives, setAlternatives] = useState<string[]>([])
  const [error, setError] = useState('')

  function clearResult() {
    setRoute(null); setError(''); setExplanation(''); setAlternatives([])
  }

  async function search(selectedDate: string) {
    clearResult()
    if (from >= to) { setError('Конец маршрута должен быть позже начала.'); return }
    const selection = { city, date: selectedDate, from, to, budget: budget === '' ? Infinity : Number(budget) }
    setBusy(true)
    try {
      const result = await searchDay(selection)
      setRoute(result.route)
      setExplanation(result.explanation)
      if (!result.route.stops.length) setAlternatives(await nextRouteDays(selection))
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    void search(date)
  }

  function useDate(next: string) {
    setDate(next)
    void search(next)
  }

  return <section className="inner-page wrap">
    <p className="eyebrow"><span className="hairline"/> ПЛАНЫ НА ДЕНЬ</p><h1>Планировщик выходного</h1>
    <p className="page-intro">Соберите маршрут из реальных событий с запасом времени на дорогу.</p>
    <div className="two-col">
      <form className="panel form-grid" onSubmit={submit} onChange={clearResult}>
        <h2><RouteIcon/> Ваш маршрут</h2>
        <label>Город<select disabled={busy} value={city} onChange={e => setCity(e.target.value)}>{cities.map(c => <option key={c}>{c}</option>)}</select></label>
        <label>День<input type="date" required disabled={busy} min={day(new Date())} value={date} onChange={e => setDate(e.target.value)}/></label>
        <label>Бюджет на билеты, ₽<input type="number" inputMode="numeric" disabled={busy} min="0" max="1000000" placeholder="Без ограничения" value={budget} onChange={e => setBudget(e.target.value)}/></label>
        <label>Свободны с<input type="time" required disabled={busy} value={from} onChange={e => setFrom(e.target.value)}/></label>
        <label>Свободны до<input type="time" required disabled={busy} value={to} onChange={e => setTo(e.target.value)}/></label>
        <button className="button button-amber" disabled={busy}>{busy ? 'Составляем маршрут…' : 'Составить маршрут'} <ArrowRight size={18}/></button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
      <div className="panel timeline" aria-live="polite" aria-busy={busy}>
        <h2><CalendarDays/> План дня</h2>
        {!route && !error && <p>{busy ? 'Ищем события…' : 'Выберите параметры и найдите события для маршрута.'}</p>}
        {explanation && <p>{explanation}</p>}
        {explanation && busy && <p>Ищем ближайшие подходящие даты…</p>}
        {alternatives.length > 0 && <div className="planner-alternatives">
          <p><strong>Ближайшие даты с подходящими событиями</strong></p>
          <div>{alternatives.map(next => <button key={next} className="button button-outline" type="button" disabled={busy} onClick={() => useDate(next)}>
            {displayDate(next + 'T12:00:00+05:00')} <ArrowRight size={16}/>
          </button>)}</div>
        </div>}
        {route?.stops.length === 1 && <p>Нашли одно подходящее событие. Добавить второе без пересечения по времени не получилось.</p>}
        {route?.stops.map((stop, i) => <motion.div key={stop.event.id} className="timeline-item" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * .08 }}>
          {i > 0 && <p className="transfer"><MapPin size={14}/> {stop.transfer ? `Дорога ≈ ${stop.transfer} мин` : 'Та же площадка'}</p>}
          <p className="mono"><Clock3 size={15}/> {time(stop.from)}–{time(stop.to)}{stop.durationEstimated && ' ≈'}</p>
          <button className="text-button" onClick={() => open(stop.event)}>{stop.event.title} <ArrowRight size={16}/></button>
          <p>{stop.event.venue} · {price(stop.event)}</p>
        </motion.div>)}
        {Boolean(route?.stops.length) && <div className="route-total"><strong className="mono">До {money(route!.cost)} за билеты</strong><p>Дорога оценочная. Если координат нет, закладываем 25 минут. При неизвестной длительности планируем 90 минут.</p></div>}
      </div>
    </div><OrnamentDivider/>
  </section>
}
