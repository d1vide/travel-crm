const TIME_ZONE = 'Europe/Moscow'

const dateFormat = new Intl.DateTimeFormat('ru-RU', {
  timeZone: TIME_ZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

const dateTimeFormat = new Intl.DateTimeFormat('ru-RU', {
  timeZone: TIME_ZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

/** Дата события (RFC 3339, UTC) в московском времени: ДД.ММ.ГГГГ. */
export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso))
}

/** Дата и время события в московском времени: ДД.ММ.ГГГГ, ЧЧ:ММ. */
export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}
