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
