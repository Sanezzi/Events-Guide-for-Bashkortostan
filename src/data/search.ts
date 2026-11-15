import { categories, capital, day, money, periods, primaryCities, zone, type Filters } from './events'

const aliases: Record<string, string> = {
  Уфа: 'уф[аеуы]|уфим[а-я]+', Стерлитамак: 'стерлитамак[аеуы]?',
  Салават: 'салават[аеуы]?', Нефтекамск: 'нефтекамск[аеуы]?',
  Белорецк: 'белорецк[аеуы]?', Бирск: 'бирск[аеуы]?', Учалы: 'учалы|учалах|учалов',
  Мелеуз: 'мелеуз[ае]?', Кумертау: 'кумертау', Сибай: 'сибай|сибае',
  Янаул: 'янаул[ае]?', Давлеканово: 'давлеканово|давлеканове',
}
const boundary = (pattern: string) => new RegExp(`(?<![а-яa-z])(?:${pattern})(?![а-яa-z])`, 'iu')
const forms = ['концерт[а-я]*', 'спектакл[а-я]*', 'выставк[а-я]*', 'фестивал[а-я]*', 'кино|фильм[а-я]*', 'экскурси[а-я]*']
const months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

export function parseQuery(raw: string, cities: string[] = primaryCities, previous: Filters = {}): Filters {
  let rest = raw.toLowerCase().replaceAll('ё', 'е').trim()
  const result = { ...previous }
  const remove = (pattern: RegExp) => { rest = rest.replace(pattern, ' ') }
  for (const city of [...new Set([...cities, ...Object.keys(aliases)])].sort((a, b) => b.length - a.length)) {
    const pattern = boundary(aliases[city] ?? city.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    if (pattern.test(rest)) { result.city = city; remove(pattern); break }
  }
  for (let i = 0; i < forms.length; i++) {
    const pattern = boundary(forms[i])
    if (pattern.test(rest)) { result.category = categories[i]; remove(pattern); break }
  }
  for (const [label, period] of [[/сегодня/iu, 'today'], [/завтра/iu, 'tomorrow'], [/выходн[а-я]+/iu, 'weekend'], [/недел[а-я]+/iu, 'week']] as const) {
    if (label.test(rest)) { result.period = period; delete result.date_from; delete result.date_to; remove(label); break }
  }
  const exact = rest.match(new RegExp(`(?<!\\d)([1-9]|[12]\\d|3[01])\\s+(${months.join('|')})(?:\\s+(20\\d{2})(?:\\s+года)?)?(?![а-я\\d])`, 'iu'))
  if (exact) {
    const year = Number(exact[3] || day(new Date()).slice(0, 4))
    const month = months.indexOf(exact[2]) + 1
    const dateNumber = Number(exact[1])
    if (dateNumber <= new Date(Date.UTC(year, month, 0)).getUTCDate()) {
      const dateKey = `${year}-${String(month).padStart(2, '0')}-${String(dateNumber).padStart(2, '0')}`
      delete result.period
      result.date_from = dateKey + 'T00:00:00+05:00'
      result.date_to = dateKey + 'T23:59:59+05:00'
      rest = rest.replace(exact[0], ' ')
    }
  }
  const age = rest.match(/(\d{1,2})\s*(?:лет|года|год|летним|летней)(?![а-я])|(?<!\d)(0|6|12|16|18)\s*\+/iu)
  if (age) { result.age_limit = Number(age[1] ?? age[2]); remove(new RegExp(age[0].replace('+', '\\+'), 'iu')) }
  const max = rest.match(/(?:до|не дороже)\s*(\d+(?:[ .]\d{3})*)\s*(?:₽|руб[а-я.]*)?/iu)
  if (max) { result.price_max = Number(max[1].replace(/[ .]/g, '')); delete result.is_free; rest = rest.replace(max[0], ' ') }
  if (/бесплатн|без оплаты/iu.test(rest)) { result.is_free = true; delete result.price_max; remove(/бесплатн[а-я]*|без оплаты/iu) }
  if (/башкирск|башҡорт/iu.test(rest)) { result.language = 'ba'; remove(/(?:на\s+)?башкирск[а-я]*(?:\s+языке)?|башҡорт телендә/iu) }
  if (/дешевле/iu.test(rest)) { result.sort = 'price_min'; result.price_max = result.price_max ? Math.floor(result.price_max * 0.8) : 500; remove(/дешевле/iu) }
  if (/другой день/iu.test(rest)) { result.period = result.period === 'tomorrow' ? 'weekend' : 'tomorrow'; delete result.date_from; delete result.date_to; remove(/(?:в\s+)?другой день/iu) }
  remove(/куда\s+(?:мне\s+)?(?:пойти|сходить)|что\s+(?:посмотреть|есть)|подбери[а-я]*|найди[а-я]*|с\s+ребенком|семьей|ближе к центру/giu)
  rest = rest.replace(/(?<![а-я])(?:в|во|на|с|и|мне|пожалуйста|для|куда|только|можно|афиша|мероприятия|события)(?![а-я])/giu, ' ').replace(/[?!.;,]+/g, ' ').replace(/\s+/g, ' ').trim()
  if (rest) result.text = rest
  return result
}

export function criteria(filters: Filters): string[] {
  return [
    filters.city, filters.category && capital(filters.category), filters.period && periods[filters.period],
    filters.date_from && filters.date_from.slice(0, 10) === filters.date_to?.slice(0, 10) && new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeZone: zone }).format(new Date(filters.date_from)),
    filters.is_free ? 'Бесплатно' : filters.price_max !== undefined && 'До ' + money(filters.price_max),
    filters.age_limit !== undefined && `Подходит для ${filters.age_limit} лет`,
    filters.language === 'ba' && 'Башҡорт телендә',
  ].filter((value): value is string => Boolean(value))
}

export function readFilters(): Filters {
  const query = new URLSearchParams(location.search)
  const filters: Filters = {}
  for (const key of ['text', 'city', 'venue', 'category', 'period', 'date_from', 'date_to', 'sort', 'language'] as const) {
    const value = query.get(key)
    if (value) Object.assign(filters, { [key]: value })
  }
  for (const key of ['age_limit', 'price_max'] as const) {
    const value = query.get(key)
    if (value !== null && value.trim() && Number.isFinite(Number(value))) filters[key] = Number(value)
  }
  if (query.get('is_free') === 'true') filters.is_free = true
  return filters
}
