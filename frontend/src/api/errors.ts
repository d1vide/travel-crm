/** Ошибка поля формы в ответе сервера. Формат контракта: `{code, message, fields[]}`. */
export interface FieldError {
  field: string
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: FieldError[]
  /** Исходная ошибка, если запрос не дошёл до сервера. */
  originalError?: unknown

  constructor(status: number, code: string, message: string, fields: FieldError[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

interface Fallback {
  code: string
  message: string
}

function fallbackFor(status: number): Fallback {
  if (status === 401) return { code: 'unauthorized', message: 'Требуется вход в систему' }
  if (status === 403) return { code: 'forbidden', message: 'Недостаточно прав для этого действия' }
  if (status === 404) return { code: 'not_found', message: 'Запрошенные данные не найдены' }
  if (status >= 500) return { code: 'server_error', message: 'Ошибка сервера, попробуйте позже' }
  return { code: 'request_error', message: 'Не удалось выполнить запрос' }
}

function parseFields(value: unknown): FieldError[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item): FieldError[] => {
    if (item && typeof item === 'object') {
      const { field, message } = item as Record<string, unknown>
      if (typeof field === 'string' && typeof message === 'string') return [{ field, message }]
    }
    return []
  })
}

async function readBody(response: Response): Promise<Record<string, unknown> | null> {
  try {
    const body: unknown = await response.json()
    return body && typeof body === 'object' ? (body as Record<string, unknown>) : null
  } catch {
    return null
  }
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const fallback = fallbackFor(response.status)
  const body = await readBody(response)
  const code = typeof body?.code === 'string' ? body.code : fallback.code
  const message = typeof body?.message === 'string' ? body.message : fallback.message
  return new ApiError(response.status, code, message, parseFields(body?.fields))
}

export function apiErrorFromNetwork(cause: unknown): ApiError {
  const error = new ApiError(0, 'network_error', 'Нет связи с сервером, проверьте подключение')
  error.originalError = cause
  return error
}
