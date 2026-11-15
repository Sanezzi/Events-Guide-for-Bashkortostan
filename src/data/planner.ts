import { day, getEvents, type EventCard, type Filters } from './events'

export interface Stop { event: EventCard; from: number; to: number; transfer: number; durationEstimated: boolean }
export interface Route { stops: Stop[]; cost: number }
export interface RouteSearch {
  city: string
  date: string
  from: string
  to: string
  budget: number
}
const minute = 60_000

const localDateTime = (date: string, time: string) => `${date}T${time}:00+05:00`

async function* eventPages(filters: Filters) {
  let offset = 0
  for (;;) {
    const { events, total } = await getEvents(filters, 100, offset)
    if (!events.length) return
    yield events
    offset += events.length
    if (offset >= total) return
  }
}

function routeOnDay(events: EventCard[], selection: RouteSearch) {
  return planRoute(
    events, Date.parse(localDateTime(selection.date, selection.from)),
    Date.parse(localDateTime(selection.date, selection.to)), selection.budget,
  )
}

export async function searchDay(selection: RouteSearch) {
  const events: EventCard[] = []
  for await (const page of eventPages({
    city: selection.city,
    date_from: localDateTime(selection.date, '00:00'),
    date_to: `${selection.date}T23:59:59.999+05:00`,
  })) events.push(...page)

  const route = routeOnDay(events, selection)
  if (route.stops.length) return { route, explanation: '' }
  if (!events.length) return { route, explanation: 'На эту дату в выбранном городе нет событий.' }
  if (!routeOnDay(events, { ...selection, budget: Infinity }).stops.length) {
    return { route, explanation: 'События в этот день есть. Попробуйте расширить время или уточнить стоимость билетов у организатора.' }
  }
  return { route, explanation: 'В этот день есть события, но они не укладываются в бюджет.' }
}

export async function nextRouteDays(selection: RouteSearch) {
  const nextDay = new Date(Date.parse(localDateTime(selection.date, '00:00')) + 24 * 60 * minute)
  const result: string[] = []
  let currentDay = ''
  let sameDay: EventCard[] = []

  for await (const page of eventPages({
    city: selection.city, date_from: localDateTime(day(nextDay), '00:00'),
    price_max: Number.isFinite(selection.budget) ? selection.budget : undefined,
  })) {
    for (const event of page) {
      const date = day(event.date_start)
      if (date !== currentDay) {
        if (sameDay.length && routeOnDay(sameDay, { ...selection, date: currentDay }).stops.length) {
          result.push(currentDay)
          if (result.length === 3) return result
        }
        currentDay = date
        sameDay = []
      }
      sameDay.push(event)
    }
  }
  if (sameDay.length && routeOnDay(sameDay, { ...selection, date: currentDay }).stops.length) result.push(currentDay)
  return result
}

export function transferMinutes(from: EventCard, to: EventCard): number {
  if (from.venue === to.venue && from.address === to.address) return 0
  if (from.lat === null || from.lon === null || to.lat === null || to.lon === null) return 25
  const rad = Math.PI / 180
  const dLat = (to.lat - from.lat) * rad, dLon = (to.lon - from.lon) * rad
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(from.lat * rad) * Math.cos(to.lat * rad) * Math.sin(dLon / 2) ** 2
  const km = 6371 * 2 * Math.asin(Math.sqrt(Math.min(a, 1)))
  return Math.max(10, Math.ceil(km * 1.35 / 20 * 60) + 7)
}

export function planRoute(events: EventCard[], start: number, end: number, budget: number): Route {
  const candidates = events.filter(event => event.status === 'опубликовано' && event.price_known !== false)
    .map(event => {
      const from = Date.parse(event.date_start)
      const actualEnd = event.date_end ? Date.parse(event.date_end) : NaN
      const durationEstimated = !(actualEnd > from || event.duration_min)
      const to = actualEnd > from ? actualEnd : from + (event.duration_min || 90) * minute
      return { event, from, to, transfer: 0, durationEstimated }
    }).filter(stop => stop.from >= start && stop.to <= end).sort((a, b) => a.from - b.from)
  const layers: Route[][] = candidates.map(() => [])
  let best: Route = { stops: [], cost: 0 }
  candidates.forEach((stop, endIndex) => {
    const cost = stop.event.price_max
    if (cost > budget) return
    layers[endIndex][1] = { stops: [stop], cost }
    for (let previous = 0; previous < endIndex; previous++) {
      const other = candidates[previous]
      const transfer = transferMinutes(other.event, stop.event)
      if (other.to + transfer * minute > stop.from) continue
      for (let count = 1; count < 4; count++) {
        const prefix = layers[previous][count]
        if (!prefix || prefix.cost + cost > budget) continue
        const old = layers[endIndex][count + 1]
        if (!old || old.cost > prefix.cost + cost) {
          layers[endIndex][count + 1] = { stops: [...prefix.stops, { ...stop, transfer }], cost: prefix.cost + cost }
        }
      }
    }
    for (const route of layers[endIndex]) {
      if (route && (route.stops.length > best.stops.length || (route.stops.length === best.stops.length && route.cost < best.cost))) best = route
    }
  })
  return best
}
