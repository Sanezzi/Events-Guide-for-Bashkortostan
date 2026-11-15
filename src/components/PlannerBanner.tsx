import { ArrowUpRight, Route } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { art } from '../data/events'
import { Kuskar } from './OrnamentDivider'

export function PlannerBanner({ navigate }: { navigate: (path: string) => void }) {
  const reduced = useReducedMotion()
  return <motion.aside className="planner-banner wrap" aria-labelledby="planner-banner-title"
    initial={reduced ? false : { opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
    transition={{ duration: .65, ease: [0.22, 1, 0.36, 1] }} viewport={{ once: true, amount: .2 }}>
    <div className="planner-banner-copy">
      <span className="planner-banner-icon"><Route size={21}/></span>
      <h2 id="planner-banner-title">Соберите свой<br/> выходной</h2>
      <p>Выберите город, время и бюджет. Планировщик подберёт события и оставит время на дорогу.</p>
      <a className="button button-amber" href="/planner" onClick={event => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
        event.preventDefault()
        navigate('/planner')
      }}>Открыть планировщик <ArrowUpRight size={17}/></a>
    </div>
    <div className="planner-banner-art">
      <img src={art('urals')} alt="" loading="lazy" width={768} height={512}/>
      <Kuskar className="planner-banner-ornament"/>
    </div>
  </motion.aside>
}
