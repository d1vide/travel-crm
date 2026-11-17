<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NCard, NForm, NFormItem, NInput } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/errors'
import { homePathFor } from '@/auth/navigation'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const emailError = ref<string | null>(null)
const passwordError = ref<string | null>(null)
const formError = ref<string | null>(null)
const submitting = ref(false)

/** Возврат разрешён только на внутренние адреса приложения. */
function safeRedirect(value: unknown): string | null {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//')
    ? value
    : null
}

function validate(): boolean {
  emailError.value = email.value.trim() ? null : 'Укажите email'
  passwordError.value = password.value ? null : 'Укажите пароль'
  return !emailError.value && !passwordError.value
}

async function submit() {
  formError.value = null
  if (!validate()) return
  submitting.value = true
  try {
    await session.login(email.value.trim(), password.value)
    const role = session.role
    const target = safeRedirect(route.query.redirect) ?? (role ? homePathFor(role) : '/')
    await router.push(target)
  } catch (error) {
    formError.value =
      error instanceof ApiError ? error.message : 'Не удалось выполнить вход, попробуйте позже'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login">
    <n-card title="Вход в Travel CRM" class="login__card">
      <n-form @submit.prevent="submit">
        <n-alert v-if="formError" type="error" :show-icon="false" class="login__alert">
          {{ formError }}
        </n-alert>
        <n-form-item
          label="Email"
          :validation-status="emailError ? 'error' : undefined"
          :feedback="emailError ?? undefined"
        >
          <n-input
            v-model:value="email"
            placeholder="name@example.com"
            :input-props="{ autocomplete: 'username' }"
          />
        </n-form-item>
        <n-form-item
          label="Пароль"
          :validation-status="passwordError ? 'error' : undefined"
          :feedback="passwordError ?? undefined"
        >
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            :input-props="{ autocomplete: 'current-password' }"
          />
        </n-form-item>
        <n-button type="primary" block :loading="submitting" attr-type="submit">Войти</n-button>
      </n-form>
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

.login__alert {
  margin-bottom: 16px;
}
</style>
