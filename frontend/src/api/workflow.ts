import { ApiError } from './errors'
import type { components } from './schema'

export type Dto = components['schemas']

export async function publicRequest<T>(
  path: string,
  submission?: Dto['TouristSubmission'],
  key?: string,
): Promise<T> {
  const headers = new Headers({ Accept: 'application/json' })
  if (submission && key) {
    headers.set('Content-Type', 'application/json')
    headers.set('Idempotency-Key', key)
  }
  const response = await fetch('/api/public' + path, {
    method: submission ? 'PUT' : 'GET',
    headers,
    body: submission ? JSON.stringify(submission) : undefined,
    credentials: 'omit',
    cache: 'no-store',
    referrerPolicy: 'no-referrer',
  })
  if (!response.ok) {
    if (response.status === 404)
      throw new ApiError(404, 'not_found', 'Ссылка недействительна или истекла.')
    const error = await response.json().catch(() => null)
    throw new ApiError(
      response.status,
      error?.code ?? 'unknown',
      error?.message ?? 'Не удалось выполнить запрос.',
      error?.fields ?? [],
    )
  }
  return response.json() as Promise<T>
}

export function decimalAmount(value: string): string | null {
  const amount = value.trim().replace(',', '.')
  if (!/^\d{1,12}(\.\d{1,2})?$/.test(amount)) return null
  const [rubles, fraction = ''] = amount.split('.')
  return String(Number(rubles)) + '.' + fraction.padEnd(2, '0')
}

export function validatePositiveAmount(input: string, limit: string) {
  const amount = decimalAmount(input)
  if (!amount || amount === '0.00') {
    return { amount: null, error: 'Введите сумму больше нуля с точностью до копеек.' }
  }
  const cents = (value: string) => BigInt(value.replace('.', ''))
  if (cents(amount) > cents(limit)) {
    return { amount: null, error: 'Сумма превышает доступный остаток.' }
  }
  return { amount, error: '' }
}
