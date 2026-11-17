import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { NAVIGATION } from '@/auth/navigation'
import { createAppRouter } from '../index'

const router = createAppRouter(createMemoryHistory())

describe('маршруты приложения', () => {
  it.each(NAVIGATION.map((item) => [item.path, item] as const))(
    'для раздела %s есть маршрут с теми же ролями, что в меню',
    (_path, item) => {
      const resolved = router.resolve(item.path)

      expect(resolved.name).toBe(item.name)
      expect(resolved.meta.roles).toEqual(item.roles)
    },
  )

  it.each(['/clients/new', '/clients/00000000-0000-4000-8000-000000000001'])(
    'вложенная страница %s доступна менеджеру и руководителю и подсвечивает «Клиенты»',
    (path) => {
      const resolved = router.resolve(path)

      expect(resolved.meta.roles).toEqual(['manager', 'head'])
      expect(resolved.meta.section).toBe('clients')
    },
  )

  it('«new» не принимается за идентификатор клиента', () => {
    expect(router.resolve('/clients/new').name).toBe('client-new')
  })

  it('страница входа доступна только гостям', () => {
    const resolved = router.resolve('/login')

    expect(resolved.name).toBe('login')
    expect(resolved.meta.guestOnly).toBe(true)
  })

  it('есть страница «нет доступа»', () => {
    expect(router.resolve({ name: 'forbidden' }).path).toBe('/forbidden')
  })

  it('неизвестный адрес открывает страницу «не найдено»', () => {
    expect(router.resolve('/нет-такой-страницы').name).toBe('not-found')
  })
})
