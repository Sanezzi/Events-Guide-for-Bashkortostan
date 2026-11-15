import { forwardRef } from 'react'
import { ArrowRight, BadgeCheck, CalendarDays, MapPin } from 'lucide-react'
import { motion, useMotionTemplate, useMotionValue, useReducedMotion, useSpring } from 'motion/react'
import { capital, cover, date, eventPath, price, time, type EventCard as Event } from '../data/events'

export const EventCard = forwardRef<HTMLElement, { event: Event; open: (event: Event) => void; index: number }>(function EventCard({ event, open, index }, ref) {
  const reduced = useReducedMotion()
  const x = useMotionValue(0), y = useMotionValue(0)
  const rx = useSpring(0, { stiffness: 220, damping: 24 }), ry = useSpring(0, { stiffness: 220, damping: 24 })
  const light = useMotionTemplate`radial-gradient(240px circle at ${x}px ${y}px, #d98a2b80, transparent 75%)`
  const cancelled = event.status === 'отменено'
  const ethno = event.category === 'фестиваль' && event.tags.some(tag => /этно|народн|фольклор/i.test(tag))
  return <motion.article ref={ref} layout className={`ticket ${cancelled ? 'cancelled' : ''}`}
    initial={reduced ? false : { opacity: 0, y: 18 }}
    animate={{ opacity: 1, y: 0, transition: { duration: .3, delay: reduced ? 0 : (index % 8) * .07 } }}
    exit={{ opacity: 0, transition: { duration: reduced ? 0 : .15 } }}
    style={{ rotateX: rx, rotateY: ry }} onMouseMove={e => {
      if (reduced) return
      const rect = e.currentTarget.getBoundingClientRect()
      const left = e.clientX - rect.left, top = e.clientY - rect.top
      x.set(left); y.set(top)
      ry.set((left / rect.width - .5) * 6); rx.set((.5 - top / rect.height) * 6)
    }} onMouseLeave={() => { rx.set(0); ry.set(0) }}>
    <motion.div className="ticket-light" style={{ background: light }}/>
    <div className="ticket-cover">
      <img src={cover(event)} alt="" loading="lazy" />
      <span className="category-tag">{capital(event.category)}</span>
      <span className="age-tag mono">{event.age_limit}+</span>
      {cancelled && <span className="cancel-ribbon">Отменено</span>}
    </div>
    <div className="perforation" aria-hidden="true"/>
    <div className="ticket-body">
      <p className="ticket-date mono"><CalendarDays size={14}/>{date(event.date_start)} · {time(event.date_start)}</p>
      <h3>{event.title}</h3>
      <p className="ticket-location"><MapPin size={15}/><span>{event.city} · {event.venue}</span></p>
      {(event.language?.includes('ba') || ethno) && <div className="ticket-badges">
        {event.language?.includes('ba') && <span lang="ba">Башҡорт телендә</span>}{ethno && <span>Этнофестиваль</span>}
      </div>}
      <div className="ticket-bottom">
        <span className="ticket-price mono">{price(event)}</span>
        {event.source_url && <span className="source-check" tabIndex={0} aria-label="Проверено по источнику" title="Проверено по источнику"><BadgeCheck size={18}/></span>}
        <a href={eventPath(event.id)} onClick={e => { if (!e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) { e.preventDefault(); open(event) } }}>Подробнее <ArrowRight size={16}/></a>
      </div>
    </div>
  </motion.article>
})
