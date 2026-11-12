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

  it('страница входа открыта без авторизации', () => {
    const resolved = router.resolve('/login')

    expect(resolved.name).toBe('login')
    expect(resolved.meta.public).toBe(true)
  })

  it('есть страница «нет доступа»', () => {
    expect(router.resolve({ name: 'forbidden' }).path).toBe('/forbidden')
  })

  it('неизвестный адрес открывает страницу «не найдено»', () => {
    expect(router.resolve('/нет-такой-страницы').name).toBe('not-found')
  })
})
