import type { Role } from '@/auth/roles'
import type { HttpClient } from './http'
import { useHttp } from './instance'

export interface Profile {
  fullName: string
  role: Role
  email: string | null
  department: string | null
  position: string | null
  workPhone: string | null
}

/**
 * Контракт 0.2 отдаёт в `User` только id, full_name и role. Email, отдел, должность и рабочий
 * телефон читаются, если сервер их вернёт, и остаются пустыми, пока бэкенд их не поддерживает.
 */
interface ProfileResponse {
  full_name: string
  role: Role
  email?: string | null
  department?: string | null
  position?: string | null
  work_phone?: string | null
}

export function createProfileApi(http: HttpClient) {
  return {
    async get(): Promise<Profile> {
      const body = await http.get<ProfileResponse>('/auth/me')
      return {
        fullName: body.full_name,
        role: body.role,
        email: body.email ?? null,
        department: body.department ?? null,
        position: body.position ?? null,
        workPhone: body.work_phone ?? null,
      }
    },
  }
}

export function useProfileApi() {
  return createProfileApi(useHttp())
}
