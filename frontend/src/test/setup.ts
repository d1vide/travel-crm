import { vi } from 'vitest'

// jsdom не реализует ResizeObserver, который нужен компонентам Naive UI.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??= ResizeObserverStub

vi.mock('@/theme/icons', () => import('./icons.stub'))
