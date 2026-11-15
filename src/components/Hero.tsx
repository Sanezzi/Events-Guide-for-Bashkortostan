import type { ReactNode } from 'react'
import { ArrowDown, ArrowUpRight } from 'lucide-react'
import { motion, useMotionValue, useReducedMotion, useSpring } from 'motion/react'
import { Ornament } from './OrnamentDivider'
import { Landscape } from './Landscape'

const ease = [0.22, 1, 0.36, 1] as const
const ticker = ['Уфа', 'Театр', 'Стерлитамак', 'Музыка', 'Салават', 'Выставки', 'Белорецк', 'Экскурсии', 'Бирск', 'Фестивали', 'Учалы', 'Кино']

export function MagneticButton({ children, action, className = '' }: { children: ReactNode; action: () => void; className?: string }) {
  const reduced = useReducedMotion()
  const mx = useMotionValue(0), my = useMotionValue(0)
  const x = useSpring(mx, { stiffness: 280, damping: 22 }), y = useSpring(my, { stiffness: 280, damping: 22 })
  return <motion.button type="button" className={`button ${className}`} style={{ x, y }} whileTap={{ scale: .97 }} onClick={action}
    onMouseMove={event => {
      if (reduced) return
      const rect = event.currentTarget.getBoundingClientRect()
      mx.set((event.clientX - rect.left - rect.width / 2) * .12)
      my.set((event.clientY - rect.top - rect.height / 2) * .16)
    }} onMouseLeave={() => { mx.set(0); my.set(0) }}>{children}</motion.button>
}

export function Hero({ openGuide }: { openGuide: () => void }) {
  const reduced = useReducedMotion()
  return <>
    <section className="hero hero-liquid wrap" aria-labelledby="hero-title">
      <div className="hero-copy">
        <p className="eyebrow"><span className="hairline"/> КУЛЬТУРНАЯ АФИША РЕСПУБЛИКИ</p>
        <h1 id="hero-title" aria-label="Куда пойти в Башкортостане?">{['Куда пойти', 'в Башкорто-', 'стане?'].map((line, i) => <span className="hero-line overflow-hidden" key={line}>
          <motion.span className={i ? 'forest-text' : ''} initial={reduced ? false : { y: '110%' }} animate={{ y: '0%' }} transition={{ duration: .95, delay: i * .10, ease }}>{line}</motion.span>
        </span>)}</h1>
        <motion.div initial={reduced ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .65, delay: .22, ease }}>
          <p className="hero-description">От сцены до горных троп. Найдите концерт, спектакль или выставку и составьте свой маршрут по республике.</p>
          <div className="hero-actions">
            <MagneticButton className="button-amber" action={() => document.getElementById('catalog')?.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth' })}>Смотреть афишу <ArrowDown size={17}/></MagneticButton>
            <button className="button button-outline" onClick={openGuide}><Ornament size={17}/> Спросить ИИ <ArrowUpRight size={16}/></button>
          </div>
        </motion.div>
      </div>
      <Landscape/>
    </section>
    <div className="marquee liquid-ribbon" aria-label="Города и жанры афиши">
      <div className="marquee-track">{[0, 1].map(run => <div className="marquee-run" key={run} aria-hidden={run === 1}>
        {ticker.map(item => <span key={item}><Ornament size={15}/>{item}</span>)}
      </div>)}</div>
    </div>
  </>
}
