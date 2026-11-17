import { describe, expect, it } from 'vitest'
import { groupedNavigationFor, homePathFor, navigationFor, NAVIGATION } from '../navigation'

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

describe('groupedNavigationFor', () => {
  const summary = (role: Parameters<typeof navigationFor>[0]) =>
    groupedNavigationFor(role).map((g) => [g.label, g.items.map((i) => i.label)])

  it('разбивает разделы руководителя на группы в порядке макета', () => {
    expect(summary('head')).toEqual([
      ['Операции', ['Заявки', 'Клиенты', 'Каталог туров']],
      ['Финансы', ['Оплаты и возвраты']],
      ['Управление', ['Рабочее место руководителя', 'Отчёт']],
    ])
  })

  it('не показывает пустые группы', () => {
    expect(summary('manager')).toEqual([['Операции', ['Заявки', 'Клиенты', 'Каталог туров']]])
    expect(summary('accountant')).toEqual([['Финансы', ['Оплаты и возвраты']]])
  })
})
