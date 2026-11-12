import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// Адрес бэкенда для dev-сервера. В браузере запросы всегда идут на /api того же адреса:
// в разработке их проксирует Vite, в Docker — nginx.
const env = loadEnv('development', process.cwd(), 'VITE_')
const apiTarget = process.env.VITE_API_TARGET ?? env.VITE_API_TARGET ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), vueDevTools()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': { target: apiTarget, changeOrigin: false },
    },
  },
})
