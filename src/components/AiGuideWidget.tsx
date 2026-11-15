import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowRight, Send, ShieldCheck, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { api, date, getEvents, json, price, time, type EventCard, type Filters } from '../data/events'
import { criteria, parseQuery } from '../data/search'

const samples = ['Куда сходить с ребёнком 8 лет в Стерлитамаке до 1000 ₽?', 'Бесплатные выставки в Уфе на выходных']
const refinements = ['Дешевле', 'Ближе к центру', 'Только бесплатные', 'На башкирском', 'В другой день']
type Reply = { reply_text: string; events: EventCard[]; clarifying_question: string | null; is_fallback: boolean; requires_confirmation?: { version: string } }
type Entry = { id: number; role: 'user' | 'assistant'; text: string; events?: EventCard[]; version?: string; filters?: Filters }

function Flower() {
  return <svg viewBox="0 0 32 32" width="29" height="29" fill="none" aria-hidden="true">
    {Array.from({ length: 7 }, (_, n) => <path key={n} transform={`rotate(${n * 360 / 7} 16 16)`} d="M16 15C11 9 13 5 16 3c3 2 5 6 0 12Z" stroke="currentColor" strokeWidth="1.4"/>)}
    <circle cx="16" cy="16" r="2" fill="currentColor"/>
  </svg>
}

function why(event: EventCard, filters: Filters = {}) {
  const facts = [
    filters.city === event.city && `событие в выбранном городе — ${event.city}`,
    filters.age_limit !== undefined && event.age_limit <= filters.age_limit && `рейтинг ${event.age_limit}+ подходит для указанного возраста`,
    filters.price_max !== undefined && event.price_known !== false && event.price_max <= filters.price_max && 'укладывается в бюджет',
    event.is_free && 'вход бесплатный',
    filters.language === 'ba' && event.language?.includes('ba') && 'событие на башкирском',
  ].filter(Boolean)
  return facts.length ? `Подходит: ${facts.join(', ')}.` : `В программе — ${event.category}. Событие пройдёт на площадке «${event.venue}».`
}

export function AiGuideWidget({ visible, setVisible, cities, open }: { visible: boolean; setVisible: (value: boolean) => void; cities: string[]; open: (event: EventCard) => void }) {
  const [messages, setMessages] = useState<Entry[]>([])
  const [input, setInput] = useState('')
  const [offline, setOffline] = useState(false)
  const [busy, setBusy] = useState(false)
  const [latestFilters, setLatestFilters] = useState<Filters>({})
  const historyRef = useRef<HTMLDivElement>(null)
  const field = useRef<HTMLInputElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const session = useRef(crypto.randomUUID())
  const counter = useRef(0)
  const close = () => { setVisible(false); trigger.current?.focus() }
  useEffect(() => { if (visible) field.current?.focus({ preventScroll: true }) }, [visible])
  useEffect(() => { if (visible && historyRef.current) historyRef.current.scrollTop = historyRef.current.scrollHeight }, [visible, messages, busy])
  const add = (entry: Omit<Entry, 'id'>) => {
    const id = ++counter.current
    setMessages(current => [...current, { id, ...entry }])
  }
  async function send(value: string, version?: string, refine = false) {
    const text = value.trim()
    if (!text || busy) return
    setInput(''); setBusy(true)
    const followup = refine || (messages.length > 0 && text.length < 35 && !/куда|подбери|найди|\?/iu.test(text))
    const filters = version ? latestFilters : parseQuery(text, cities, followup ? latestFilters : {})
    setLatestFilters(filters)
    setMessages(old => old.map(entry => ({ ...entry, version: undefined })))
    add({ role: 'user', text })
    try {
      if (offline) {
        const result = await getEvents(filters, 5)
        const filterText = criteria(filters).join(' · ')
        const center = /ближе к центру/i.test(text) ? ' Расстояние до центра в этом режиме не определяю.' : ''
        add({
          role: 'assistant', filters, events: result.events,
          text: (result.total ? 'Подобрал события из каталога.' : 'По этим условиям подходящих событий пока нет.') + (filterText ? '\n' + filterText : '') + center,
        })
      } else {
        const response = await api<Reply>('/api/chat', json('POST', {
          session_id: session.current, message: text, confirm_action: Boolean(version), confirmation_version: version,
        }))
        const notice = response.is_fallback ? '\nРезервный поиск по каталогу.' : ''
        const center = /ближе к центру/i.test(text) ? '\nСверьте адрес в карточке: в каталоге нет подтверждённого расстояния до центра.' : ''
        const clarification = response.clarifying_question && !response.reply_text.includes(response.clarifying_question) ? '\n' + response.clarifying_question : ''
        add({ role: 'assistant', text: response.reply_text + clarification + notice + center, events: response.events, version: response.requires_confirmation?.version, filters })
      }
    } catch (e) { add({ role: 'assistant', text: (e as Error).message }) }
    finally { setBusy(false) }
  }
  const submit = (event: FormEvent) => { event.preventDefault(); void send(input) }
  return <div className="guide-shell">
    <AnimatePresence>
      {visible && <motion.section role="dialog" aria-modal="false" aria-labelledby="guide-title" className="guide"
        initial={{ opacity: 0, scale: .94, y: 18 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: .96, y: 12 }}
        transition={{ type: 'spring', stiffness: 380, damping: 30 }} onKeyDown={e => { if (e.key === 'Escape') close() }}>
        <div className="guide-head"><Flower/><div><h2 id="guide-title">Гид по афише</h2><p>{offline ? 'Поиск по фильтрам' : 'ИИ-помощник'}</p></div><button className="icon-button" aria-label="Закрыть гида" onClick={close}><X size={21}/></button></div>
        <div className="guide-history" ref={historyRef} aria-live="polite">
          <p className="bubble assistant">Куда хотите сходить? Укажите город, день, бюджет или возраст ребёнка.</p>
          {!messages.length && <div className="guide-examples">{samples.map(text => <button key={text} onClick={() => send(text)}>{text}<ArrowRight size={15}/></button>)}</div>}
          {messages.map(entry => <div className={`guide-entry ${entry.role}`} key={entry.id}>
            <p className={`bubble ${entry.role}`}>{entry.text}</p>
            {entry.events?.map(event => <button className="guide-event" key={event.id} onClick={() => open(event)}>
              <strong>{event.title} <ArrowRight size={15}/></strong><span className="mono">{date(event.date_start)} · {time(event.date_start)} · {price(event)}</span><small>{why(event, entry.filters)}</small>
            </button>)}
            {entry.version && !offline && <button className="button button-forest" onClick={() => send('Подтверждаю', entry.version)}>Подтвердить действие</button>}
          </div>)}
          {busy && <p className="bubble assistant">Ищу в афише…</p>}
        </div>
        {messages.length > 0 && <div className="guide-refinements">{refinements.map(label => <button key={label} disabled={busy} onClick={() => send(label, undefined, true)}>{label}</button>)}</div>}
        <form className="guide-form" onSubmit={submit}><input ref={field} value={input} onChange={e => setInput(e.target.value)} aria-label="Сообщение гиду" placeholder="Напишите свой запрос…" maxLength={2000}/><button className="icon-button" type="submit" aria-label="Отправить запрос" disabled={busy || !input.trim()}><Send size={19}/></button></form>
        <div className="guide-foot">
          <p><ShieldCheck size={16}/> Ответы строятся строго по проверенной базе событий сервиса</p>
          <label><input type="checkbox" checked={offline} disabled={busy} onChange={e => setOffline(e.target.checked)}/> Резервный режим (поиск без ИИ)</label>
        </div>
      </motion.section>}
    </AnimatePresence>
    <motion.button ref={trigger} aria-expanded={visible} aria-label={visible ? 'Закрыть ИИ-гид' : 'Открыть ИИ-гид'} className="guide-trigger" whileTap={{ scale: .97 }} onClick={() => visible ? close() : setVisible(true)}><Flower/><span>ИИ-гид</span></motion.button>
  </div>
}
