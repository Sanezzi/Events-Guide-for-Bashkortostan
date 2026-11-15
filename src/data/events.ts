export const categories = ['концерт', 'спектакль', 'выставка', 'фестиваль', 'кино', 'экскурсия'] as const
export type Category = typeof categories[number] | 'другое'
export const primaryCities = ['Уфа', 'Стерлитамак', 'Салават', 'Нефтекамск', 'Белорецк', 'Бирск']
export type Period = 'today' | 'tomorrow' | 'weekend' | 'week'
export const periods: Record<Period, string> = { today: 'Сегодня', tomorrow: 'Завтра', weekend: 'Выходные', week: 'Неделя' }
export const zone = 'Asia/Yekaterinburg'

export interface EventCard {
  id: string
  title: string
  category: Category
  date_start: string
  date_end: string | null
  duration_min: number | null
  city: string
  venue: string
  address: string
  lat: number | null
  lon: number | null
  description: string
  price_min: number
  price_max: number
  price_known: boolean
  is_free: boolean
  age_limit: number
  language: string | null
  source_url: string
  org_link: string | null
  sources: string[]
  tags: string[]
  verified_at: string | null
  status: 'опубликовано' | 'отменено' | 'черновик'
}

export interface Filters {
  text?: string
  city?: string
  category?: Category
  period?: Period
  price_max?: number
  is_free?: boolean
  age_limit?: number
  venue?: string
  date_from?: string
  date_to?: string
  sort?: string
  language?: string
}

export interface EventResults { events: EventCard[]; total: number; explanation: string | null }
export const money = (value: number) => new Intl.NumberFormat('ru-RU').format(value) + ' ₽'
export const capital = (value: string) => value.charAt(0).toLocaleUpperCase('ru') + value.slice(1)
export const day = (value: string | Date) => new Intl.DateTimeFormat('sv-SE', { timeZone: zone, dateStyle: 'short' }).format(new Date(value))
export const date = (value: string) => new Intl.DateTimeFormat('ru-RU', { timeZone: zone, day: 'numeric', month: 'long' }).format(new Date(value))
export const time = (value: string | number) => new Intl.DateTimeFormat('ru-RU', { timeZone: zone, hour: '2-digit', minute: '2-digit' }).format(new Date(value))
export const price = (e: EventCard) => e.is_free ? 'Бесплатно' : e.price_known === false ? 'Цена уточняется' : e.price_min === e.price_max ? money(e.price_min) : `${money(e.price_min).replace(' ₽', '')}–${money(e.price_max)}`
export const eventPath = (id: string) => '/event?id=' + encodeURIComponent(id)
