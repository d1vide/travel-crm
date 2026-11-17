import type { Role } from './roles'

export type NavigationGroup = 'operations' | 'finance' | 'management'

export const GROUP_LABELS: Record<NavigationGroup, string> = {
  operations: 'Операции',
  finance: 'Финансы',
  management: 'Управление',
}

export interface NavigationItem {
  name: string
  group: NavigationGroup
  label: string
  path: string
  /** Роли, которым раздел виден. Окончательную проверку прав выполняет сервер. */
  roles: readonly Role[]
}

/** Единый источник списка разделов: по нему строятся и меню, и маршруты. */
export const NAVIGATION: readonly NavigationItem[] = [
  {
    name: 'requests',
    group: 'operations',
    label: 'Заявки',
    path: '/requests',
    roles: ['manager', 'head'],
  },
  {
    name: 'clients',
    group: 'operations',
    label: 'Клиенты',
    path: '/clients',
    roles: ['manager', 'head'],
  },
  {
    name: 'tours',
    group: 'operations',
    label: 'Каталог туров',
    path: '/tours',
    roles: ['manager', 'head'],
  },
  {
    name: 'payments',
    group: 'finance',
    label: 'Оплаты и возвраты',
    path: '/payments',
    roles: ['head', 'accountant'],
  },
  {
    name: 'workspace',
    group: 'management',
    label: 'Рабочее место руководителя',
    path: '/workspace',
    roles: ['head'],
  },
  { name: 'reports', group: 'management', label: 'Отчёт', path: '/reports', roles: ['head'] },
]

export function navigationFor(role: Role): NavigationItem[] {
  return NAVIGATION.filter((item) => item.roles.includes(role))
}

export function homePathFor(role: Role): string {
  return navigationFor(role)[0]?.path ?? '/forbidden'
}

export interface NavigationSection {
  group: NavigationGroup
  label: string
  items: NavigationItem[]
}

/** Разделы роли, сгруппированные для бокового меню; пустые группы не возвращаются. */
export function groupedNavigationFor(role: Role): NavigationSection[] {
  const items = navigationFor(role)
  return (Object.keys(GROUP_LABELS) as NavigationGroup[])
    .map((group) => ({
      group,
      label: GROUP_LABELS[group],
      items: items.filter((item) => item.group === group),
    }))
    .filter((section) => section.items.length > 0)
}
