<script setup lang="ts">
import { computed, ref } from 'vue'
import { NAlert, NButton, NCard, NSpin } from 'naive-ui'
import PageHeader from '@/components/PageHeader.vue'
import { ApiError, fieldMessages } from '@/api/errors'
import { useHttp } from '@/api/instance'
import type { Dto } from '@/api/workflow'
import { formatDate } from '@/utils/format'

const http = useHttp()
const today = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Europe/Moscow',
  dateStyle: 'short',
}).format(new Date())
const from = ref(today.slice(0, 8) + '01')
const to = ref(today)
const result = ref<Dto['Report']>()
const errors = ref<Record<string, string>>({})
const error = ref('')
const loading = ref(false)
const metrics = computed(() =>
  result.value
    ? [
        { label: 'Создано заявок', value: result.value.requests_created },
        { label: 'Подтверждено броней', value: result.value.bookings_confirmed },
        { label: 'Успешные оплаты', value: money(result.value.payments_succeeded_amount) },
        { label: 'Успешные возвраты', value: money(result.value.refunds_succeeded_amount) },
      ]
    : [],
)
function money(value: string) {
  const [rubles = '', kopecks = '00'] = value.split('.')
  return rubles.replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f') + ',' + kopecks + ' ₽'
}
async function load() {
  if (loading.value) return
  errors.value = {}
  error.value = ''
  if (!from.value) errors.value.date_from = 'Укажите начало периода.'
  if (!to.value) errors.value.date_to = 'Укажите конец периода.'
  else if (from.value && to.value < from.value)
    errors.value.date_to = 'Конец периода должен быть не раньше начала.'
  if (Object.keys(errors.value).length) return
  loading.value = true
  try {
    result.value = await http.get<Dto['Report']>(
      '/reports/summary?' + new URLSearchParams({ date_from: from.value, date_to: to.value }),
    )
  } catch (cause) {
    errors.value = fieldMessages(cause)
    error.value = cause instanceof ApiError ? cause.message : 'Не удалось построить отчёт.'
  } finally {
    loading.value = false
  }
}
void load()
</script>
<template>
  <PageHeader
    title="Сводный отчёт"
    description="Заявки, подтверждённые брони и денежные операции за период"
  />
  <n-card>
    <form class="report-dates" novalidate @submit.prevent="load">
      <label
        >С даты<input v-model="from" type="date" :aria-invalid="!!errors.date_from" /><small
          v-if="errors.date_from"
          role="alert"
          >{{ errors.date_from }}</small
        ></label
      >
      <label
        >По дату<input v-model="to" type="date" :aria-invalid="!!errors.date_to" /><small
          v-if="errors.date_to"
          role="alert"
          >{{ errors.date_to }}</small
        ></label
      >
      <n-button type="primary" attr-type="submit" :loading="loading">Построить отчёт</n-button>
    </form>
  </n-card>
  <n-alert v-if="error" type="error" class="report-block">{{ error }}</n-alert>
  <n-spin :show="loading" class="report-block">
    <template v-if="result && !error">
      <p>
        {{ formatDate(result.date_from) }} — {{ formatDate(result.date_to) }} · московское время
      </p>
      <div class="metrics" aria-live="polite">
        <n-card v-for="metric in metrics" :key="metric.label" size="small">
          <div class="muted">{{ metric.label }}</div>
          <strong>{{ metric.value }}</strong>
        </n-card>
      </div>
    </template>
  </n-spin>
</template>
<style scoped>
.report-dates {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px;
}
.report-dates label {
  display: grid;
  gap: 4px;
}
.report-dates button {
  margin-top: 24px;
}
.report-dates input {
  min-height: 34px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  padding: 0 8px;
  font: inherit;
}
.report-block {
  margin-top: 16px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
  gap: 12px;
}
.metrics strong {
  font-size: 23px;
  font-variant-numeric: tabular-nums;
}
.muted {
  color: var(--c-text-muted);
}
small {
  color: #b42318;
}
</style>
