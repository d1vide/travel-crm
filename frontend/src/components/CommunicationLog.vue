<script setup lang="ts">
import { ref, watch } from 'vue'
import { NAlert, NButton, NCard, NInput, NPagination, NSelect, NSpin } from 'naive-ui'
import { fieldMessages } from '@/api/errors'
import { useHttp } from '@/api/instance'
import type { Dto } from '@/api/workflow'
import { useCommandKey } from '@/composables/useCommandKey'
import { formatDateTime } from '@/utils/format'
const props = defineProps<{ clientId: string; requestId?: string }>()
const http = useHttp()
const key = useCommandKey()
const labels: Record<Dto['CommunicationChannel'], string> = {
  phone: 'Телефон',
  email: 'Почта',
  messenger: 'Мессенджер',
  office: 'В офисе',
  other: 'Другое',
}
const channels = Object.entries(labels).map(([value, label]) => ({ value, label }))
const channel = ref<Dto['CommunicationChannel']>('phone')
const text = ref('')
const editing = ref(false)
const occurred = ref('')
const data = ref<Dto['CommunicationPage']>()
const page = ref(1)
const error = ref('')
const fields = ref<Record<string, string>>({})
const loading = ref(false)
const busy = ref(false)
let sequence = 0
const explain = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'Не удалось выполнить запрос.'
async function load() {
  const seq = ++sequence
  loading.value = true
  error.value = ''
  try {
    const path = props.requestId ? '/requests/' + props.requestId : '/clients/' + props.clientId
    const result = await http.get<Dto['CommunicationPage']>(
      path + '/communications?page=' + page.value,
    )
    if (seq === sequence) data.value = result
  } catch (cause) {
    if (seq === sequence) error.value = explain(cause)
  } finally {
    if (seq === sequence) loading.value = false
  }
}
async function add() {
  if (busy.value) return
  const date = new Date(occurred.value)
  fields.value = {}
  if (!text.value.trim()) fields.value.text = 'Опишите, что обсудили.'
  if (Number.isNaN(date.valueOf())) fields.value.occurred_at = 'Укажите дату и время контакта.'
  if (Object.keys(fields.value).length) return

  busy.value = true
  error.value = ''
  const body: Dto['CommunicationCreate'] = {
    request_id: props.requestId ?? null,
    channel: channel.value,
    text: text.value.trim(),
    occurred_at: date.toISOString(),
  }
  try {
    await http.post('/clients/' + props.clientId + '/communications', body, {
      idempotencyKey: key.keyFor([props.clientId, body]),
    })
    key.reset()
    editing.value = false
    text.value = ''
    occurred.value = ''
    if (page.value === 1) await load()
    else page.value = 1
  } catch (cause) {
    fields.value = fieldMessages(cause)
    error.value = explain(cause)
  } finally {
    busy.value = false
  }
}
watch(page, load, { immediate: true })
</script>
<template>
  <n-card title="История общения">
    <n-alert v-if="error" type="error"
      >{{ error }} <n-button size="small" @click="load">Обновить</n-button></n-alert
    >
    <n-button v-if="!editing" @click="editing = true">Записать контакт</n-button>
    <form v-else class="log-form" novalidate @submit.prevent="add">
      <label
        >Канал<n-select v-model:value="channel" :options="channels" /><small
          v-if="fields.channel"
          role="alert"
          >{{ fields.channel }}</small
        ></label
      >
      <label
        >Дата и время контакта<input
          v-model="occurred"
          type="datetime-local"
          :aria-invalid="!!fields.occurred_at"
        /><small v-if="fields.occurred_at" role="alert">{{ fields.occurred_at }}</small></label
      >
      <label class="wide"
        >Что обсудили<n-input
          v-model:value="text"
          type="textarea"
          :input-props="{ required: true }"
          :status="fields.text ? 'error' : undefined"
        /><small v-if="fields.text" role="alert">{{ fields.text }}</small></label
      >
      <n-button class="wide" type="primary" attr-type="submit" :loading="busy"
        >Добавить запись</n-button
      >
    </form>
    <n-spin :show="loading">
      <p v-if="!loading && !data?.items?.length">Записей пока нет.</p>
      <article v-for="entry in data?.items" :key="entry.id">
        <strong>{{ labels[entry.channel] }} · {{ formatDateTime(entry.occurred_at) }}</strong>
        <div>{{ entry.author.full_name }}</div>
        <p>{{ entry.text }}</p>
      </article>
      <n-pagination
        v-if="data && data.total > data.page_size"
        v-model:page="page"
        :page-size="data.page_size"
        :item-count="data.total"
      />
    </n-spin>
  </n-card>
</template>
<style scoped>
.log-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 210px), 1fr));
  gap: 12px;
  margin-block: 12px;
}
label {
  display: grid;
  gap: 4px;
}
.wide {
  grid-column: 1/-1;
}
button.wide {
  justify-self: start;
}
input {
  min-height: 34px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  padding-inline: 8px;
  font: inherit;
}
article {
  padding-block: 10px;
  border-top: 1px solid var(--c-border);
}
article p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin-bottom: 0;
}
small {
  color: #b42318;
}
</style>
