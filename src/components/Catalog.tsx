import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowDown, Search, SlidersHorizontal, X } from 'lucide-react'
import { AnimatePresence, LayoutGroup, motion } from 'motion/react'
import { api, capital, categories, getEvents, params, periods, type Category, type EventCard as Event, type EventResults, type Filters, type Period } from '../data/events'
import { criteria, parseQuery, readFilters } from '../data/search'
import { EventCard } from './EventCard'
import { pillSpring } from './Header'

const dateChips = [['', 'Все даты'], ...Object.entries(periods)]
const empty = { events: [], total: 0, explanation: null }

function relaxation(filters: Filters, reason?: string | null): { filters: Filters; label: string } | null {
  const budget = filters.is_free || filters.price_max !== undefined
  if (budget && (reason === 'price' || !filters.period && !filters.date_from || !filters.city)) {
    const price_max = filters.price_max === undefined || filters.price_max < 1500 ? 1500 : undefined
    return { filters: { ...filters, is_free: undefined, price_max }, label: price_max ? 'Расширить бюджет до 1 500 ₽' : 'Искать с любым бюджетом' }
  }
  if (filters.period || filters.date_from || filters.date_to) return { filters: { ...filters, period: undefined, date_from: undefined, date_to: undefined }, label: 'Посмотреть все даты' }
  if (filters.venue) return { filters: { ...filters, venue: undefined }, label: 'Посмотреть все площадки' }
  if (filters.category) return { filters: { ...filters, category: undefined }, label: 'Посмотреть все жанры' }
  if (filters.city) return { filters: { ...filters, city: undefined }, label: 'Искать по всей республике' }
  if (filters.text) return { filters: { ...filters, text: undefined }, label: 'Убрать ключевое слово' }
  if (filters.language) return { filters: { ...filters, language: undefined }, label: 'Посмотреть события на всех языках' }
  if (budget) return { filters: { ...filters, is_free: undefined, price_max: undefined }, label: 'Искать с любым бюджетом' }
  return null
}
