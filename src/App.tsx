import { useEffect, useState } from 'react'
import { MotionConfig } from 'motion/react'
import { ArrowUpRight } from 'lucide-react'
import { api, primaryCities, type EventCard } from './data/events'
import { Header } from './components/Header'
import { Hero } from './components/Hero'
import { Catalog } from './components/Catalog'
import { EventDialog } from './components/EventDialog'
import { Planner } from './components/Planner'
import { PlannerBanner } from './components/PlannerBanner'
import { About, Organizers, Subscribe } from './components/ServicePages'
import { AiGuideWidget } from './components/AiGuideWidget'
import { Ornament, OrnamentDivider } from './components/OrnamentDivider'

export function App() {
  const [url, setUrl] = useState(() => new URL(location.href))
  const [cities, setCities] = useState(primaryCities)
  const [guide, setGuide] = useState(url.pathname === '/chat')
  const [event, setEvent] = useState<EventCard | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<EventCard | null>(null)
  const path = url.pathname
  const id = url.searchParams.get('id')
  const standalone = path === '/event'
  const catalog = ['/', '/event', '/chat'].includes(path)

  useEffect(() => {
    function sync() {
      setUrl(new URL(location.href))
      setSelected(null)
      if (location.pathname === '/chat') setGuide(true)
    }
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])

  useEffect(() => {
    api<{ cities: string[] }>('/api/v1/cities').then(data => setCities([...new Set([...primaryCities, ...data.cities])])).catch(() => {})
  }, [])

  useEffect(() => {
    if (path !== '/event' && path !== '/organizers' || !id) { setEvent(null); setError(''); return }
    const controller = new AbortController()
    setEvent(null); setError('')
    api<EventCard>('/api/v1/events/' + encodeURIComponent(id), { signal: controller.signal }).then(setEvent)
      .catch(e => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [path, id])

  function navigate(href: string) {
    if (href === location.pathname + location.search) return
    history.pushState(null, '', href)
    setUrl(new URL(location.href))
    setSelected(null)
    window.scrollTo({ top: 0, behavior: 'instant' })
  }
  const shown = selected || (standalone && event)
  const close = () => { if (selected) setSelected(null); else navigate('/') }
  const openGuide = () => setGuide(true)

  return <MotionConfig reducedMotion="user">
    <a className="skip-link" href="#main">Перейти к содержанию</a>
    <Header path={path} navigate={navigate} openGuide={openGuide}/>
    <main id="main">
      {catalog && <><Hero openGuide={openGuide}/><Catalog key={path} cities={cities} open={setSelected}/><div className="wrap"><OrnamentDivider/></div><PlannerBanner navigate={navigate}/></>}
      {path === '/planner' && <Planner cities={cities} open={setSelected}/>}
      {path === '/subscribe' && <Subscribe cities={cities}/>}
      {path === '/organizers' && (!id || event) && <Organizers key={id || 'new'} cities={cities} event={id ? event : null}/>}
      {path === '/about' && <About cities={cities}/>}
      {error && (standalone || path === '/organizers') && <div className="wrap state-panel" role="alert"><p>{error}</p><button className="button button-outline" onClick={() => navigate('/')}>К каталогу</button></div>}
    </main>
    <footer className="site-footer"><div className="wrap footer-inner"><a className="brand footer-brand" href="/"><span className="brand-mark"><Ornament size={24}/></span><span>АФИША<span className="brand-sub">БАШКОРТОСТАН</span></span></a><p>Независимый агрегатор культурных событий Республики Башкортостан.</p><a href="/about" onClick={e => { e.preventDefault(); navigate('/about') }}>О сервисе <ArrowUpRight size={17}/></a></div></footer>
    <AiGuideWidget visible={guide} setVisible={setGuide} cities={cities} open={setSelected}/>
    {shown && <EventDialog key={shown.id} event={shown} close={close} edit={() => navigate('/organizers?id=' + shown.id)}/>}
  </MotionConfig>
}
