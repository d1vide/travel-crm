import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { initHttp } from './api/instance'
import { createAppRouter } from './router'
import { createAuthGuard } from './router/guard'
import { useSessionStore } from './stores/session'

const app = createApp(App)
app.use(createPinia())

const router = createAppRouter()
const session = useSessionStore()
router.beforeEach(createAuthGuard(session))
initHttp(session, router)

app.use(router)
app.mount('#app')
