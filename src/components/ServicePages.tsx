import { useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, Bell, Check, Code2, Copy, Link2, Send, X } from 'lucide-react'
import { api, capital, categories, date, json, money, type EventCard } from '../data/events'
import { Kuskar, OrnamentDivider } from './OrnamentDivider'

type Subscription = { id: string; city: string; category: string | null }

function PageHead({ label, title, children }: { label: string; title: string; children: React.ReactNode }) {
  return <><p className="eyebrow"><span className="hairline"/> {label}</p><h1>{title}</h1><p className="page-intro">{children}</p></>
}

export function Subscribe({ cities }: { cities: string[] }) {
  const [records, setRecords] = useState<Subscription[]>([])
  const [city, setCity] = useState('')
  const [category, setCategory] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [ready, setReady] = useState(false)
  function load() {
    setBusy(true)
    api<Subscription[]>('/api/v1/subscriptions').then(result => { setRecords(result); setReady(true) })
      .catch(e => setMessage(e.message)).finally(() => setBusy(false))
  }
  useEffect(load, [])
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setMessage('')
    try {
      const result = await api<{ message: string }>('/api/v1/subscriptions', json('POST', { city, category: category || null }))
      setRecords(await api('/api/v1/subscriptions'))
      setMessage(result.message)
    } catch (err) { setMessage((err as Error).message) }
    finally { setBusy(false) }
  }
  async function remove(id: string) {
    setBusy(true); setMessage('')
    try {
      await api('/api/v1/subscriptions/' + id, { method: 'DELETE' })
      setRecords(old => old.filter(item => item.id !== id))
      setMessage('Подписка удалена.')
    } catch (err) { setMessage((err as Error).message) }
    finally { setBusy(false) }
  }
  return <section className="inner-page wrap">
    <PageHead label="МОЯ АФИША" title="Подписка">Сохраните город и жанр. Управляйте подписками в этом браузере.</PageHead>
    <div className="two-col">
      <form className="panel form-grid subscription-form" onSubmit={submit}>
        <Kuskar className="watermark"/><h2><Bell/> Новая подписка</h2>
        <label>Город<select required value={city} onChange={e => setCity(e.target.value)}><option value="">Выберите город</option>{cities.map(c => <option key={c}>{c}</option>)}</select></label>
        <label>Жанр<select value={category} onChange={e => setCategory(e.target.value)}><option value="">Все жанры</option>{categories.map(c => <option key={c} value={c}>{capital(c)}</option>)}</select></label>
        <button className="button button-amber" disabled={busy || !ready}>Подписаться <ArrowRight size={18}/></button>
      </form>
      <div className="panel"><h2>Ваши подписки</h2>
        {ready && !records.length && <p>Подписок пока нет.</p>}
        {!ready && <p>{busy ? 'Загружаем…' : <button onClick={load} className="text-button">Загрузить повторно</button>}</p>}
        <ul className="subscription-list">{records.map(row => <li key={row.id}><div><strong>{row.city}</strong><p>{row.category ? capital(row.category) : 'Все жанры'}</p></div><button className="icon-button" title="Отписаться" aria-label={`Отписаться: ${row.city}`} disabled={busy} onClick={() => remove(row.id)}><X size={19}/></button></li>)}</ul>
        <p role="status">{message}</p>
      </div>
    </div><OrnamentDivider/>
  </section>
}

export function Organizers({ cities, event }: { cities: string[]; event: EventCard | null }) {
  const [fields, setFields] = useState({
    title: '', city: '', venue: '', address: '', start: '', price: '0', age: '0',
    category: 'концерт', source: '', details: '', website: '',
  })
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const field = (key: keyof typeof fields) => ({
    value: fields[key], onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      const value = e.target.value
      setFields(old => ({ ...old, [key]: value }))
    },
  })
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMessage('')
    try {
      const result = event
        ? await api<{ message: string }>('/api/v1/feedback', json('POST', { event_id: event.id, text: fields.details + (fields.source ? '\nИсточник: ' + fields.source : ''), website: fields.website }))
        : await api<{ message: string }>('/api/v1/event-submissions', json('POST', {
          website: fields.website, event: {
            title: fields.title, city: fields.city, venue: fields.venue, address: fields.address,
            date_start: fields.start + ':00+05:00', price_min: Number(fields.price),
            age_limit: Number(fields.age), category: fields.category, source_url: fields.source, description: fields.details,
          },
        }))
      setMessage(result.message); setSent(true)
    } catch (err) { setMessage((err as Error).message) }
    finally { setBusy(false) }
  }
  return <section className="inner-page wrap">
    <PageHead label="ДЛЯ ОРГАНИЗАТОРОВ" title={event ? 'Уточнить событие' : 'Расскажите о событии'}>Отправьте информацию модератору. Понадобится ссылка, по которой можно сверить данные.</PageHead>
    <div className="two-col"><form className="panel form-grid" onSubmit={submit}>
      <h2>{event ? event.title : 'Данные события'}</h2>
      {!event && <>
        <label>Название<input required maxLength={300} {...field('title')}/></label>
        <label>Город<input list="organizer-cities" required maxLength={150} {...field('city')}/><datalist id="organizer-cities">{cities.map(c => <option key={c} value={c}/>)}</datalist></label>
        <label>Площадка<input required maxLength={300} {...field('venue')}/></label>
        <label>Адрес<input required maxLength={500} {...field('address')}/></label>
        <label>Дата и время (местное)<input required type="datetime-local" {...field('start')}/></label>
        <label>Жанр<select {...field('category')}>{categories.map(c => <option key={c} value={c}>{capital(c)}</option>)}<option value="другое">Другое</option></select></label>
        <label>Цена билета, ₽<input required type="number" min="0" max="1000000" {...field('price')}/></label>
        <label>Возрастной рейтинг<select {...field('age')}>{[0, 6, 12, 16, 18].map(n => <option key={n} value={n}>{n}+</option>)}</select></label>
      </>}
      <label>Ссылка на источник<input required={!event} type="url" maxLength={2048} {...field('source')}/></label>
      <label>{event ? 'Что нужно изменить' : 'Описание'}<textarea required maxLength={event ? 1800 : 4000} rows={4} {...field('details')}/></label>
      <div hidden aria-hidden="true"><label>Сайт<input tabIndex={-1} autoComplete="off" {...field('website')}/></label></div>
      <button className="button button-amber" disabled={busy || sent}>{sent ? 'Отправлено' : 'Отправить на проверку'} {sent ? <Check size={18}/> : <Send size={17}/>}</button>
      <p role="status">{message}</p>
    </form><div className="panel live-preview"><p className="eyebrow">ПРЕДПРОСМОТР</p>
      <h2>{event?.title || fields.title || 'Название события'}</h2>
      <p className="mono">{event ? date(event.date_start) : fields.start ? fields.start.replace('T', ' · ') : 'Дата и время'} · {event?.age_limit ?? fields.age}+</p>
      <p>{event ? event.city + ' · ' + event.venue : [fields.city, fields.venue].filter(Boolean).join(' · ') || 'Город и площадка'}</p>
      {!event && <strong className="mono">{Number(fields.price) ? money(Number(fields.price)) : 'Бесплатно'}</strong>}
      <p className="preview-description">{fields.details || (event ? 'Здесь появится ваше уточнение.' : 'Описание появится здесь.')}</p>
    </div></div><OrnamentDivider/>
  </section>
}
