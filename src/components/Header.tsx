import { useEffect, useState } from 'react'
import { ArrowUpRight, Menu, X } from 'lucide-react'
import { AnimatePresence, LayoutGroup, motion } from 'motion/react'
import { Ornament } from './OrnamentDivider'

const links = [
  ['/', 'Каталог'], ['/planner', 'Планировщик'], ['/subscribe', 'Подписка'],
  ['/organizers', 'Организаторам'], ['/about', 'О сервисе'],
]
export const pillSpring = { type: 'spring', stiffness: 380, damping: 30 } as const

export function Header({ path, navigate, openGuide }: { path: string; navigate: (path: string) => void; openGuide: () => void }) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [open])
  const active = path === '/event' || path === '/chat' ? '/' : path
  const go = (event: React.MouseEvent, href: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return
    event.preventDefault()
    setOpen(false)
    navigate(href)
  }
  return <header className="site-header">
    <div className="header-inner backdrop-blur-xl">
      <a className="brand" href="/" onClick={event => go(event, '/')} aria-label="Афиша культуры Башкортостана">
        <span className="brand-mark"><Ornament size={24}/></span><span>АФИША<span className="brand-sub">БАШКОРТОСТАН</span></span>
      </a>
      <LayoutGroup id="navigation"><nav className="desktop-nav" aria-label="Основная навигация">
        {links.map(([href, label]) => <a key={href} href={href} aria-current={active === href ? 'page' : undefined} onClick={event => go(event, href)}>
          {active === href && <motion.span className="nav-pill" layoutId="activePill" transition={pillSpring}/>}<span>{label}</span>
        </a>)}
      </nav></LayoutGroup>
      <button className="header-guide" onClick={openGuide}>ИИ-гид <ArrowUpRight size={15}/></button>
      <button className="menu-toggle icon-button" aria-expanded={open} aria-controls="mobile-nav" aria-label={open ? 'Закрыть меню' : 'Открыть меню'} onClick={() => setOpen(!open)}>{open ? <X/> : <Menu/>}</button>
    </div>
    <AnimatePresence>{open && <motion.nav id="mobile-nav" className="mobile-nav" aria-label="Меню" initial={{ opacity: 0, y: -18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -18 }}>
      {links.map(([href, label]) => <a key={href} href={href} aria-current={active === href ? 'page' : undefined} onClick={event => go(event, href)}>{label}<ArrowUpRight size={21}/></a>)}
      <button className="button button-amber" onClick={() => { setOpen(false); openGuide() }}>Открыть ИИ-гида</button>
    </motion.nav>}</AnimatePresence>
  </header>
}
