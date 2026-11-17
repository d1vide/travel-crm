import { describe, expectTypeOf, it } from 'vitest'
import type { Role } from '@/auth/roles'
import type { FieldError } from '../errors'
import type { components } from '../schema'

type Schemas = components['schemas']

// Проверки на этапе компиляции: если контракт и код разойдутся, не пройдёт `npm run type-check`.
describe('соответствие контракту API (docs/api/openapi.json)', () => {
  it('роли совпадают с Role контракта', () => {
    expectTypeOf<Role>().toEqualTypeOf<Schemas['Role']>()
  })

  it('ошибка поля совпадает с FieldError контракта', () => {
    expectTypeOf<FieldError>().toEqualTypeOf<Schemas['FieldError']>()
  })

  it('ответ входа содержит access_token и пользователя с ролью', () => {
    expectTypeOf<Schemas['AuthResult']['access_token']>().toEqualTypeOf<string>()
    expectTypeOf<Schemas['AuthResult']['user']['role']>().toEqualTypeOf<Role>()
  })
})
