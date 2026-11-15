import { useRef } from 'react'
import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react'

export function Ornament({ size = 26 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <path d="M16 2 22 8 16 14 10 8 16 2ZM16 18l6 6-6 6-6-6 6-6ZM2 16l6-6 6 6-6 6-6-6Zm16 0 6-6 6 6-6 6-6-6Z" stroke="currentColor" strokeWidth="1.5"/>
    <path d="m16 12 4 4-4 4-4-4 4-4Z" fill="currentColor"/>
  </svg>
}

export function Kuskar({ className }: { className?: string }) {
  return <svg className={className} viewBox="0 0 80 30" fill="none" aria-hidden="true">
    <path d="M1 15h10l6-7 8 7-8 7-6-7m14 0 8-8 7 8-7 8-8-8Zm15 0 7-8 8 8-8 8-7-8Zm15 0 8-7 6 7-6 7-8-7Zm14 0h10M27 6l5-5 8 8 8-8 5 5M27 24l5 5 8-8 8 8 5-5" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
  </svg>
}

export function OrnamentDivider() {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] })
  const x = useTransform(scrollYProgress, [0, 1], [-30, 30])
  return <div ref={ref} className="ornament-divider" aria-hidden="true">
    <span /><motion.div style={{ x: reduced ? 0 : x }}><Kuskar /></motion.div><span />
  </div>
}
