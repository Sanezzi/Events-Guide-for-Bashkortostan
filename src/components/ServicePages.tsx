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
