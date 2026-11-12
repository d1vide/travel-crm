/**
 * Роли сотрудников. Точные значения, которые вернёт сервер, закрепляются в контракте API (#7);
 * при расхождении правится только этот файл.
 */
export type Role = 'manager' | 'head' | 'accountant'

export const ROLE_LABELS: Record<Role, string> = {
  manager: 'Менеджер',
  head: 'Руководитель',
  accountant: 'Бухгалтер',
}

export interface SessionUser {
  id: string
  fullName: string
  role: Role
}

export function isRole(value: unknown): value is Role {
  return value === 'manager' || value === 'head' || value === 'accountant'
}
