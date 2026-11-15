import { useRef, type PointerEvent } from 'react'
import { MapPin } from 'lucide-react'
import { motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from 'motion/react'
import { art } from '../data/events'

const ease = [0.22, 1, 0.36, 1] as const
const petals = [
  'M491 182Q437 184 402 152Q438 135 468 159Q484 171 491 182Z',
  'M491 182Q444 156 438 118Q459 123 476 144Q489 163 491 182Z',
  'M491 182Q465 143 472 103Q494 117 497 145Q498 162 491 182Z',
  'M491 182Q485 130 511 102Q526 127 511 153Q501 172 491 182Z',
  'M491 182Q517 135 545 128Q545 153 521 170Q505 180 491 182Z',
  'M491 182Q529 150 568 154Q555 183 522 183Q502 185 491 182Z',
  'M491 182Q548 177 575 195Q558 210 531 202Q504 192 491 182Z',
]
const contours = [
  'M-22 386C91 333 154 375 215 361S317 291 398 306s102 55 165 37 98-82 151-78',
  'M-13 397c95-43 153-14 224-25s121-67 191-54 105 58 167 39 95-79 143-77',
  'M-12 408c86-37 153-15 220-24s110-64 194-51 107 53 171 35 83-64 137-72',
  'M-16 421c85-34 155-15 219-25s125-59 192-52 106 54 181 36 95-61 135-68',
  'M-16 435c70-31 147-12 218-26s122-56 190-53 113 56 186 36 87-59 137-64',
  'M-10 446c76-28 127-11 208-26s125-56 195-51 108 54 189 31 82-47 127-56',
]

export function Landscape() {
  const frame = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const mx = useMotionValue(0), my = useMotionValue(0)
  const x = useSpring(mx, { stiffness: 100, damping: 24 })
  const y = useSpring(my, { stiffness: 100, damping: 24 })
  const farX = useTransform(x, value => value * -.55)
  const farY = useTransform(y, value => value * -.45)
  const { scrollYProgress } = useScroll({ target: frame, offset: ['start start', 'end start'] })
  const scrollY = useTransform(scrollYProgress, [0, 1], [0, 28])

  function move(event: PointerEvent<HTMLDivElement>) {
    if (reduced || event.pointerType !== 'mouse') return
    const rect = event.currentTarget.getBoundingClientRect()
    mx.set(((event.clientX - rect.left) / rect.width - .5) * 28)
    my.set(((event.clientY - rect.top) / rect.height - .5) * 20)
  }

  return <motion.div ref={frame} className="landscape landscape-liquid" onPointerMove={move}
    onPointerLeave={() => { mx.set(0); my.set(0) }}
    initial={reduced ? false : { opacity: 0, scale: .975 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: .9, ease }}
    role="img" aria-label="Художественная панорама Южного Урала и семь лепестков курая">
    <motion.div className="landscape-photo" style={{ x: farX, y: farY }}>
      <motion.picture style={{ y: reduced ? 0 : scrollY }}>
        <source media="(max-width: 680px)" srcSet={art('urals-dawn-small')}/>
        <img src={art('urals-dawn')} alt="" fetchPriority="high" width={1536} height={1024}/>
      </motion.picture>
    </motion.div>
    <div className="landscape-veil" aria-hidden="true"/>
    <div className="valley-mist" aria-hidden="true"/>
    <svg className="landscape-ink" viewBox="0 0 680 500" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <motion.g style={{ x: farX, y: farY }} className="landscape-contours">
        {contours.map(path => <path key={path} d={path}/>)}
      </motion.g>
      <motion.g style={{ x, y }}>
        <g className="kurai-sway">
          <circle cx="490" cy="166" r="103" className="kurai-orbit"/>
          <circle cx="490" cy="166" r="114" className="kurai-orbit orbit-dashed"/>
          <motion.path className="kurai-stem" d="M398 474Q388 383 437 294T491 182M429 312Q447 273 487 263Q476 290 429 312ZM414 345Q382 322 375 289Q408 301 414 345Z"
            initial={{ pathLength: reduced ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.6, delay: .24, ease }}/>
          {petals.map((path, index) => <motion.path className="kurai-petal" key={path} d={path} initial={{ pathLength: reduced ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.05, delay: .45 + index * .085, ease }}/>)}
          <circle cx="491" cy="182" r="3.5" className="kurai-center"/>
        </g>
      </motion.g>
    </svg>
    <div className="landscape-label mono"><MapPin size={15}/> ЮЖНЫЙ УРАЛ</div>
  </motion.div>
}
