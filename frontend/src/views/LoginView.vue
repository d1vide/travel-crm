<script setup lang="ts">
import { NAlert, NButton, NCard, NSpace } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { homePathFor } from '@/auth/navigation'
import { ROLE_LABELS, type Role } from '@/auth/roles'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const route = useRoute()

// Временный демонстрационный вход только для разработки интерфейса без сервера.
// Настоящая форма входа добавляется в задаче «Вход, выход и доступ по ролям» (#11).
const showDemoLogin = import.meta.env.DEV
const roles = Object.keys(ROLE_LABELS) as Role[]

function signInAs(role: Role) {
  session.setSession({
    accessToken: 'demo-token',
    user: { id: 'demo', fullName: `Демо: ${ROLE_LABELS[role]}`, role },
  })
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : null
  void router.push(redirect ?? homePathFor(role))
}
</script>

<template>
  <main class="login">
    <n-card title="Вход в Travel CRM" class="login__card">
      <n-space v-if="showDemoLogin" vertical>
        <n-alert type="warning" :show-icon="false">
          Режим разработки: вход без сервера. Выберите роль, чтобы посмотреть интерфейс.
        </n-alert>
        <n-button v-for="role in roles" :key="role" block @click="signInAs(role)">
          {{ ROLE_LABELS[role] }}
        </n-button>
      </n-space>
      <n-alert v-else type="info" :show-icon="false">
        Форма входа появится после подключения сервера авторизации.
      </n-alert>
    </n-card>
  </main>
</template>

<style scoped>
.login {
  box-sizing: border-box;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 16px;
}

.login__card {
  width: 100%;
  max-width: 400px;
}
</style>
