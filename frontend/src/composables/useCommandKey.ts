import { newIdempotencyKey } from '@/api/http'

/** Стабильная запись тела: порядок полей не влияет на результат. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
    return `{${entries.join(',')}}`
  }
  return JSON.stringify(value) ?? 'null'
}

/**
 * Ключ идемпотентности одной команды формы. Повтор той же команды (сетевой повтор, повторное
 * нажатие после сбоя) получает прежний ключ, изменённое тело — новый. После успешного
 * сохранения вызовите reset(), чтобы следующая команда получила свой ключ.
 */
export function useCommandKey() {
  let lastBody: string | null = null
  let lastKey: string | null = null

  function keyFor(body: unknown): string {
    const serialized = canonical(body)
    if (lastKey === null || serialized !== lastBody) {
      lastKey = newIdempotencyKey()
      lastBody = serialized
    }
    return lastKey
  }

  function reset() {
    lastBody = null
    lastKey = null
  }

  return { keyFor, reset }
}
