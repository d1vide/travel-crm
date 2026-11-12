import type { Role } from './roles'

export interface NavigationItem {
  name: string
  label: string
  path: string
  /** Роли, которым раздел виден. Окончательную проверку прав выполняет сервер. */
  roles: readonly Role[]
}

/** Единый источник списка разделов: по нему строятся и меню, и маршруты. */
export const NAVIGATION: readonly NavigationItem[] = [
  { name: 'requests', label: 'Заявки', path: '/requests', roles: ['manager', 'head'] },
  { name: 'clients', label: 'Клиенты', path: '/clients', roles: ['manager', 'head'] },
  { name: 'tours', label: 'Каталог туров', path: '/tours', roles: ['manager', 'head'] },
  {
    name: 'payments',
    label: 'Оплаты и возвраты',
    path: '/payments',
    roles: ['head', 'accountant'],
  },
  {
    name: 'workspace',
    label: 'Рабочее место руководителя',
    path: '/workspace',
    roles: ['head'],
  },
  { name: 'reports', label: 'Отчёт', path: '/reports', roles: ['head'] },
]

export function navigationFor(role: Role): NavigationItem[] {
  return NAVIGATION.filter((item) => item.roles.includes(role))
}

export function homePathFor(role: Role): string {
  return navigationFor(role)[0]?.path ?? '/forbidden'
}
