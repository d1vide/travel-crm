<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NAlert, NButton, NSpin } from 'naive-ui'
import { fieldMessages } from '@/api/errors'
import { publicRequest, type Dto } from '@/api/workflow'
import { useCommandKey } from '@/composables/useCommandKey'
import { formatDateTime } from '@/utils/format'
import TouristFields from '@/components/TouristFields.vue'
import WorkflowOffer from '@/components/WorkflowOffer.vue'

const route = useRoute()
const key = useCommandKey()
const selection = ref<Dto['PublicSelection']>()
const form = ref<Dto['PublicTouristForm']>()
const tourists = ref<Dto['TouristSubmissionItem'][]>([])
const saved = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const fieldErrors = ref<Record<string, string>>({})
let generation = 0
const path = (kind: string) => '/' + kind + '/' + encodeURIComponent(String(route.params.token))
const explain = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'Не удалось открыть страницу.'
async function load() {
  const current = ++generation
  loading.value = true
  error.value = ''
  fieldErrors.value = {}
  saved.value = false
  selection.value = undefined
  form.value = undefined
  tourists.value = []
  key.reset()
  try {
    if (route.name === 'public-selection') {
      const data = await publicRequest<Dto['PublicSelection']>(path('selections'))
      if (current === generation) selection.value = data
    } else {
      const data = await publicRequest<Dto['PublicTouristForm']>(path('tourist-forms'))
      if (current !== generation) return
      form.value = data
      if (data.is_editable)
        tourists.value = Array.from({ length: Math.min(data.tourist_count, 10) }, blankTourist)
    }
  } catch (cause) {
    if (current === generation) {
      error.value = explain(cause)
      fieldErrors.value = fieldMessages(cause)
    }
  } finally {
    if (current === generation) loading.value = false
  }
}
function blankTourist(): Dto['TouristSubmissionItem'] {
  return {
    id: null,
    full_name: '',
    birth_date: '',
    document_type: 'passport',
    document_number: '',
    document_expires_on: null,
  }
}
function addTourist() {
  if (form.value && tourists.value.length < form.value.tourist_count)
    tourists.value.push(blankTourist())
}

async function save() {
  const current = generation
  if (!form.value?.is_editable || busy.value) return
  if (tourists.value.length !== form.value.tourist_count) {
    error.value = 'Заполните данные для всех туристов.'
    return
  }
  busy.value = true
  error.value = ''
  fieldErrors.value = {}
  const body = {
    request_version: form.value.request_version,
    tourists: tourists.value.map((row) => ({
      ...row,
      document_expires_on:
        row.document_type === 'passport' ? null : row.document_expires_on || null,
    })),
  }
  try {
    await publicRequest<Dto['TouristSubmissionResult']>(
      path('tourist-forms'),
      body,
      key.keyFor(body),
    )
    if (current !== generation) return
    saved.value = true
    tourists.value = []
  } catch (cause) {
    if (current === generation) {
      error.value = explain(cause)
      fieldErrors.value = fieldMessages(cause)
    }
  } finally {
    busy.value = false
  }
}
watch(() => route.fullPath, load, { immediate: true })
</script>
<template>
  <main class="public-flow">
    <h1>{{ route.name === 'public-selection' ? 'Подборка туров' : 'Данные туристов' }}</h1>
    <n-alert v-if="error" type="error"
      >{{ error }} <n-button size="small" @click="load">Загрузить заново</n-button></n-alert
    >
    <n-spin v-if="loading" />
    <template v-if="selection">
      <p>Подборка доступна до {{ formatDateTime(selection.expires_at) }} (МСК)</p>
      <WorkflowOffer v-for="item in selection.items" :key="item.id" :offer="item.offer_snapshot" />
    </template>
    <n-alert v-if="saved" type="success">Данные туристов приняты.</n-alert>
    <template v-else-if="form">
      <template v-if="form.is_editable">
        <p>Данные нужны для {{ form.tourist_count }} туристов.</p>
        <n-button v-if="tourists.length < form.tourist_count" @click="addTourist"
          >Добавить туриста</n-button
        >
        <TouristFields v-model="tourists" :busy="busy" :errors="fieldErrors" @save="save" />
      </template>
      <n-alert v-else type="info">{{ form.closed_reason || 'Форма закрыта.' }}</n-alert>
    </template>
  </main>
</template>
<style scoped>
.public-flow {
  width: min(760px, calc(100% - 32px));
  margin: 32px auto;
  display: grid;
  gap: 16px;
}
h1,
p {
  margin: 0;
}
</style>
