import { useEffect, useRef } from 'react'
import { ArrowUpRight, BadgeCheck, CalendarDays, Clock3, Link2, MapPin, X } from 'lucide-react'
import { motion } from 'motion/react'
import { capital, cover, date, eventPath, price, safeUrl, time, type EventCard } from '../data/events'

export function EventDialog({ event, close, edit }: { event: EventCard; close: () => void; edit: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = dialog.current
    const previous = document.activeElement as HTMLElement | null
    element?.showModal()
    const old = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { element?.close(); document.body.style.overflow = old; previous?.focus() }
  }, [])
  const sources = [...new Set([event.source_url, ...event.sources].map(safeUrl).filter((s): s is string => Boolean(s)))]
  const tickets = safeUrl(event.org_link)
  const map = new URL('https://yandex.ru/maps/')
  map.searchParams.set('text', event.lat !== null && event.lon !== null ? `${event.lat},${event.lon}` : `${event.city}, ${event.address}`)
  const minutes = event.duration_min ?? (event.date_end ? Math.round((Date.parse(event.date_end) - Date.parse(event.date_start)) / 60000) : null)
  const cancelled = event.status === 'отменено'
  return <dialog ref={dialog} className="event-dialog" aria-labelledby="detail-title" onCancel={e => { e.preventDefault(); close() }} onClick={e => { if (e.target === e.currentTarget) close() }}>
    <motion.article className={`detail ${cancelled ? 'cancelled' : ''}`} initial={{ scale: .95, y: 20, opacity: 0 }} animate={{ scale: 1, y: 0, opacity: 1 }} transition={{ type: 'spring', stiffness: 340, damping: 30 }}>
      <button className="icon-button dialog-close" onClick={close} aria-label="Закрыть карточку" autoFocus><X/></button>
      <div className="detail-cover"><img src={cover(event)} alt=""/><span className="cover-caption">Иллюстрация жанра</span>{cancelled && <span className="cancel-ribbon">Отменено</span>}</div>
      <div className="detail-body">
        <p className="eyebrow">{capital(event.category)} · {event.age_limit}+</p>
        <h2 id="detail-title">{event.title}</h2>
        <div className="detail-meta mono"><span><CalendarDays size={17}/> {date(event.date_start)} · {time(event.date_start)}</span><span><Clock3 size={17}/> {minutes ? `${minutes} мин` : 'Длительность уточняется'}</span></div>
        <p className="detail-description">{event.description}</p>
        <div className="detail-address"><MapPin size={22}/><div><strong>{event.venue}</strong><p>{event.city}, {event.address}</p><a href={map.href} target="_blank" rel="noreferrer">Открыть на карте <ArrowUpRight size={15}/></a></div></div>
        <div className="detail-sources">
          <h3><BadgeCheck size={19}/> Первоисточники</h3>
          <p>{event.verified_at ? 'Сверено ' + date(event.verified_at) : 'Дата сверки в каталоге не указана'}</p>
          {sources.map((source, i) => <a key={source} href={source} target="_blank" rel="noreferrer"><Link2 size={14}/> {i === 0 ? 'Основной источник' : new URL(source).hostname}<ArrowUpRight size={13}/></a>)}
        </div>
        <div className="detail-actions"><strong className="mono">{price(event)}</strong>
          {cancelled ? <button className="button button-outline" disabled>Билеты недоступны</button> : tickets ? <a className="button button-amber" href={tickets} target="_blank" rel="noreferrer">К билетам <ArrowUpRight size={17}/></a> : sources[0] && <a className="button button-outline" href={sources[0]} target="_blank" rel="noreferrer">У организатора <ArrowUpRight size={17}/></a>}
        </div>
        <div className="detail-links"><button className="text-button" onClick={edit}>Уточнить данные</button><a href={eventPath(event.id)} target="_blank" rel="noreferrer">Постоянная ссылка <ArrowUpRight size={14}/></a></div>
      </div>
    </motion.article>
  </dialog>
}
