import type { Router } from 'vue-router'
import { createAppHttpClient } from './client'
import type { HttpClient } from './http'

type Session = Parameters<typeof createAppHttpClient>[0]

let instance: HttpClient | null = null

/** Настраивает общий HTTP-клиент. Вызывается один раз при старте приложения. */
export function initHttp(session: Session, router: Router): void {
  instance = createAppHttpClient(session, router)
}

/** Общий HTTP-клиент для модулей API (`src/api/*`). */
export function useHttp(): HttpClient {
  if (!instance) throw new Error('HTTP-клиент не инициализирован: вызовите initHttp при старте')
  return instance
}

/** Сбрасывает клиент. Нужен только тестам. */
export function resetHttp(): void {
  instance = null
}
