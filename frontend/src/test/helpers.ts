import { h, type Component } from 'vue'
import { NMessageProvider } from 'naive-ui'

/** Оборачивает компонент в провайдеры Naive UI, которые в приложении лежат в App.vue. */
export function withProviders(component: Component, props: Record<string, unknown> = {}) {
  return {
    render: () => h(NMessageProvider, null, { default: () => h(component, props) }),
  }
}

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
