<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInput } from 'naive-ui'
import {
  useClientsApi,
  type Client,
  type ClientBrief,
  type ClientCreate,
  type ClientsApi,
} from '@/api/clients'
import { ApiError, fieldMessages } from '@/api/errors'
import { useCommandKey } from '@/composables/useCommandKey'
import ClientDuplicateAlert from './ClientDuplicateAlert.vue'

const props = defineProps<{ client?: Client; api?: ClientsApi }>()
const emit = defineEmits<{ saved: [client: Client]; cancel: []; conflict: [] }>()

const api = props.api ?? useClientsApi()
const command = useCommandKey()
const isEdit = computed(() => props.client !== undefined)

const form = reactive({
  fullName: props.client?.full_name ?? '',
  phone: props.client?.phone ?? '',
  email: props.client?.email ?? '',
  preferences: props.client?.preferences ?? '',
  note: props.client?.note ?? '',
})

const errors = reactive<Record<string, string | undefined>>({})
const formError = ref<string | null>(null)
const matches = ref<ClientBrief[]>([])
const headReview = ref(false)
const acknowledged = ref(false)
const submitting = ref(false)

const contact = (value: string) => value.trim() || null
const phone = computed(() => contact(form.phone))
const email = computed(() => contact(form.email))

// Совпадения относятся к конкретным контактам: при их смене проверка и подтверждение устаревают.
watch([phone, email], () => {
  matches.value = []
  headReview.value = false
  acknowledged.value = false
})

function clearErrors() {
  for (const key of Object.keys(errors)) delete errors[key]
  formError.value = null
}

function validate(): boolean {
  if (!form.fullName.trim()) errors.full_name = 'Укажите имя'
  if (!phone.value && !email.value) errors.phone = 'Укажите телефон или email'
  if (email.value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
    errors.email = 'Проверьте email'
  }
  return Object.keys(errors).length === 0
}

/** Контакты проверяются на дубли при создании и в редактировании только если они изменились. */
function needsDuplicateCheck(): boolean {
  if (!props.client) return true
  return (
    phone.value !== (props.client.phone ?? null) || email.value !== (props.client.email ?? null)
  )
}

async function runDuplicateCheck(): Promise<boolean> {
  const result = await api.checkDuplicates({
    phone: phone.value,
    email: email.value,
    excludeClientId: props.client?.id,
  })
  matches.value = result.matches
  headReview.value = result.requires_head_review
  return result.matches.length > 0 || result.requires_head_review
}

function body(): ClientCreate {
  const data = {
    full_name: form.fullName.trim(),
    phone: phone.value,
    email: email.value,
    preferences: form.preferences,
    note: form.note,
    duplicate_acknowledged: acknowledged.value,
  }
  if (data.phone !== null) return { ...data, phone: data.phone }
  if (data.email !== null) return { ...data, email: data.email }
  throw new ApiError(422, 'validation_error', 'Укажите телефон или email', [
    { field: 'phone', message: 'Укажите телефон или email' },
  ])
}

async function save(): Promise<Client> {
  const data = body()
  if (props.client) {
    const update = { ...data, version: props.client.version }
    return api.update(props.client.id, update, command.keyFor(update))
  }
  return api.create(data, command.keyFor(data))
}

async function handleError(error: unknown) {
  if (!(error instanceof ApiError)) {
    formError.value = 'Не удалось сохранить, попробуйте ещё раз'
    return
  }
  Object.assign(errors, fieldMessages(error))
  formError.value = error.message
  if (error.code === 'version_conflict') {
    emit('conflict')
  } else if (
    error.code === 'duplicate_contacts' ||
    error.code === 'duplicate_requires_head_review'
  ) {
    acknowledged.value = false
    await runDuplicateCheck().catch(() => undefined)
  }
}

async function submit() {
  clearErrors()
  if (!validate()) return
  submitting.value = true
  try {
    if (needsDuplicateCheck() && !acknowledged.value && (await runDuplicateCheck())) return
    const client = await save()
    command.reset()
    emit('saved', client)
  } catch (error) {
    await handleError(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <n-form label-placement="top" :show-require-mark="false" @submit.prevent="submit">
    <n-alert v-if="formError" type="error" :show-icon="false" class="form-alert">
      {{ formError }}
    </n-alert>
    <client-duplicate-alert
      :matches="matches"
      :head-review="headReview"
      v-model:acknowledged="acknowledged"
    />
    <div class="grid">
      <n-form-item
        label="ФИО"
        class="grid__wide"
        :validation-status="errors.full_name ? 'error' : undefined"
        :feedback="errors.full_name"
      >
        <n-input
          v-model:value="form.fullName"
          data-test="full_name"
          placeholder="Фамилия Имя Отчество"
        />
      </n-form-item>
      <n-form-item
        label="Телефон"
        :validation-status="errors.phone ? 'error' : undefined"
        :feedback="errors.phone"
      >
        <n-input v-model:value="form.phone" data-test="phone" placeholder="+7 900 000-00-00" />
      </n-form-item>
      <n-form-item
        label="Email"
        :validation-status="errors.email ? 'error' : undefined"
        :feedback="errors.email"
      >
        <n-input v-model:value="form.email" data-test="email" placeholder="name@example.com" />
      </n-form-item>
      <n-form-item
        label="Предпочтения"
        class="grid__wide"
        :validation-status="errors.preferences ? 'error' : undefined"
        :feedback="errors.preferences"
      >
        <n-input
          v-model:value="form.preferences"
          data-test="preferences"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="Направления, формат отдыха, пожелания"
        />
      </n-form-item>
      <n-form-item
        label="Примечание"
        class="grid__wide"
        :validation-status="errors.note ? 'error' : undefined"
        :feedback="errors.note"
      >
        <n-input
          v-model:value="form.note"
          data-test="note"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="Внутренняя заметка, клиенту не показывается"
        />
      </n-form-item>
    </div>
    <div class="actions">
      <n-button type="primary" attr-type="submit" :loading="submitting">
        {{ isEdit ? 'Сохранить' : 'Создать клиента' }}
      </n-button>
      <n-button :disabled="submitting" @click="emit('cancel')">Отмена</n-button>
    </div>
  </n-form>
</template>

<style scoped>
.form-alert {
  margin-bottom: var(--space-4);
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: var(--space-4);
}

.grid__wide {
  grid-column: 1 / -1;
}

.actions {
  display: flex;
  gap: var(--space-2);
}
</style>
