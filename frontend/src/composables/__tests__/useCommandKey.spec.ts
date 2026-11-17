import { describe, expect, it } from 'vitest'
import { useCommandKey } from '../useCommandKey'

describe('useCommandKey', () => {
  it('для одного и того же тела отдаёт один ключ (повтор команды)', () => {
    const command = useCommandKey()

    const first = command.keyFor({ full_name: 'Иван', phone: '+79001112233' })
    const second = command.keyFor({ full_name: 'Иван', phone: '+79001112233' })

    expect(second).toBe(first)
  })

  it('порядок полей в теле не влияет на ключ', () => {
    const command = useCommandKey()

    const first = command.keyFor({ a: 1, b: 2 })
    const second = command.keyFor({ b: 2, a: 1 })

    expect(second).toBe(first)
  })

  it('при изменении тела выдаёт новый ключ', () => {
    const command = useCommandKey()

    const first = command.keyFor({ full_name: 'Иван', duplicate_acknowledged: false })
    const second = command.keyFor({ full_name: 'Иван', duplicate_acknowledged: true })

    expect(second).not.toBe(first)
  })

  it('после успеха reset даёт новому действию новый ключ', () => {
    const command = useCommandKey()

    const first = command.keyFor({ full_name: 'Иван' })
    command.reset()
    const second = command.keyFor({ full_name: 'Иван' })

    expect(second).not.toBe(first)
  })

  it('ключ похож на UUID', () => {
    const key = useCommandKey().keyFor({})

    expect(key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
  })
})
