import { describe, expect, it } from 'vitest'
import { homePathFor, navigationFor, NAVIGATION } from '../navigation'

const labels = (role: Parameters<typeof navigationFor>[0]) =>
  navigationFor(role).map((i) => i.label)

describe('navigationFor', () => {
  it('менеджер видит клиентов, заявки и каталог, но не отчётность', () => {
    expect(labels('manager')).toEqual(['Заявки', 'Клиенты', 'Каталог туров'])
  })

  it('руководитель видит все разделы', () => {
    expect(labels('head')).toEqual([
      'Заявки',
      'Клиенты',
      'Каталог туров',
      'Оплаты и возвраты',
      'Рабочее место руководителя',
      'Отчёт',
    ])
  })

  it('бухгалтер видит только оплаты и возвраты', () => {
    expect(labels('accountant')).toEqual(['Оплаты и возвраты'])
  })

  it('не содержит одинаковых путей и имён маршрутов', () => {
    const paths = NAVIGATION.map((i) => i.path)
    const names = NAVIGATION.map((i) => i.name)
    expect(new Set(paths).size).toBe(paths.length)
    expect(new Set(names).size).toBe(names.length)
  })
})

describe('homePathFor', () => {
  it('ведёт каждую роль в первый доступный ей раздел', () => {
    expect(homePathFor('manager')).toBe('/requests')
    expect(homePathFor('head')).toBe('/requests')
    expect(homePathFor('accountant')).toBe('/payments')
  })
})
