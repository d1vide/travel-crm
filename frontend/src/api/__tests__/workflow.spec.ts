import { afterEach, describe, expect, it, vi } from 'vitest'
import { decimalAmount, publicRequest, validatePositiveAmount } from '../workflow'

afterEach(() => vi.unstubAllGlobals())

describe('public workflow', () => {
  it('loads a public selection anonymously without caching the response', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({ items: [] }))
    vi.stubGlobal('fetch', fetch)
    await publicRequest('/selections/token')
    expect(fetch).toHaveBeenCalledWith(
      '/api/public/selections/token',
      expect.objectContaining({
        method: 'GET',
        credentials: 'omit',
        cache: 'no-store',
        referrerPolicy: 'no-referrer',
      }),
    )
    expect(new Headers(fetch.mock.calls[0]?.[1]?.headers).has('Authorization')).toBe(false)
  })

  it('submits the full tourist list with its version and key', async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(Response.json({ accepted_count: 1 }))
    vi.stubGlobal('fetch', fetch)
    const body = {
      request_version: 7,
      tourists: [
        {
          id: null,
          full_name: 'Test Tourist',
          birth_date: '1991-03-20',
          document_type: 'passport' as const,
          document_number: 'DEMO-0001',
          document_expires_on: null,
        },
      ],
    }
    await publicRequest('/tourist-forms/token', body, 'unit-key')
    const init = fetch.mock.calls[0]?.[1]
    expect(init?.method).toBe('PUT')
    expect(init?.body).toBe(JSON.stringify(body))
    expect(new Headers(init?.headers).get('Idempotency-Key')).toBe('unit-key')
  })

  it.each([
    ['1200,5', '1200.50'],
    ['0', '0.00'],
    ['12.999', null],
    ['-1', null],
  ])('normalizes %s as %s', (input, result) => {
    expect(decimalAmount(input!)).toBe(result)
  })
})

it.each(['0', '-1', '1000.01', '10.001'])(
  'rejects invalid amounts before sending a command: %s',
  (value) => {
    expect(validatePositiveAmount(value, '1000.00').amount).toBeNull()
  },
)

it('allows the exact available amount without rounding', () => {
  expect(validatePositiveAmount('999999999999,99', '999999999999.99').amount).toBe(
    '999999999999.99',
  )
})
