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

  // The catalog orders results by start time, so a date may span pages.
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
