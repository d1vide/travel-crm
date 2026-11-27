<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NInput, NPagination, NSpin, NTag } from 'naive-ui'
import { ApiError, fieldMessages } from '@/api/errors'
import { useHttp } from '@/api/instance'
import { validatePositiveAmount, type Dto } from '@/api/workflow'
import { useCommandKey } from '@/composables/useCommandKey'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ payment?: Dto['Payment'] }>()
const emit = defineEmits<{ changed: [] }>()
const http = useHttp()
const key = useCommandKey()
const page = ref(1)
const data = ref<Dto['RefundPage']>()
const processing = ref<Dto['Refund']>()
const amount = ref('')
const amountError = ref('')
const error = ref('')
const loading = ref(false)
const busy = ref(false)
const amountId = computed(() => 'refund-amount-' + props.payment?.id)
const listPath = computed(() =>
  props.payment ? '/payments/' + props.payment.id + '/refunds' : '/refunds',
)
const labels: Record<Dto['RefundStatus'], string> = {
  processing: 'В обработке',
  succeeded: 'Возвращён',
  failed: 'Отклонён',
}
let sequence = 0
let alive = true

async function load() {
  const current = ++sequence
  loading.value = true
  try {
    const result = await http.get<Dto['RefundPage']>(listPath.value + '?page=' + page.value)
    if (alive && current === sequence) data.value = result
  } catch (cause) {
    if (alive && current === sequence)
      error.value = cause instanceof ApiError ? cause.message : 'Не удалось загрузить возвраты.'
  } finally {
    if (alive && current === sequence) loading.value = false
  }
}

watch(
  [listPath, page],
  () => {
    void load()
  },
  { immediate: true },
)

async function submit() {
  if (!props.payment?.allowed_actions.includes('create_refund') || busy.value) return
  amountError.value = ''
  error.value = ''
  const { amount: value, error: problem } = validatePositiveAmount(
    amount.value,
    props.payment.available_refund_amount,
  )
  if (!value) {
    amountError.value = problem
    return
  }
  const body: Dto['RefundCreate'] = { amount: value, currency: 'RUB' }
  busy.value = true
  try {
    const refund = await http.post<Dto['Refund']>(listPath.value, body, {
      idempotencyKey: key.keyFor([listPath.value, body]),
    })
    key.reset()
    amount.value = ''
    processing.value = refund.status === 'processing' ? refund : undefined
    if (page.value === 1) await load()
    else page.value = 1
    emit('changed')
  } catch (cause) {
    amountError.value = fieldMessages(cause).amount ?? ''
    error.value = cause instanceof ApiError ? cause.message : 'Не удалось оформить возврат.'
    if (cause instanceof ApiError && cause.status === 409) emit('changed')
  } finally {
    busy.value = false
  }
}

async function refresh(refund: Dto['Refund'], reconcile = false) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const path = '/refunds/' + refund.id
    const result = reconcile
      ? await http.post<Dto['Refund']>(path + '/reconcile')
      : await http.get<Dto['Refund']>(path)
    processing.value = result.status === 'processing' ? result : undefined
    if (result.status !== refund.status || reconcile) {
      await load()
      emit('changed')
    }
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : 'Не удалось проверить возврат.'
  } finally {
    busy.value = false
  }
}

const timer = setInterval(() => {
  if (processing.value && !document.hidden) void refresh(processing.value)
}, 5000)
onUnmounted(() => {
  alive = false
  clearInterval(timer)
})
</script>
<template>
  <n-card title="Возвраты" size="small">
    <n-alert v-if="error" type="error"
      >{{ error }} <n-button size="small" @click="load">Обновить</n-button></n-alert
    >
    <form
      v-if="payment?.allowed_actions.includes('create_refund')"
      class="refund-form"
      @submit.prevent="submit"
    >
      <label :for="amountId" class="amount-label"
        >Сумма возврата, ₽ · до {{ payment.available_refund_amount }} ₽</label
      >
      <div class="refund-actions">
        <n-input
          v-model:value="amount"
          :input-props="{ id: amountId, inputmode: 'decimal' }"
          :status="amountError ? 'error' : undefined"
        />
        <n-button attr-type="submit" type="primary" :loading="busy">Оформить возврат</n-button>
      </div>
      <small v-if="amountError" role="alert">{{ amountError }}</small>
    </form>
    <n-spin :show="loading">
      <p v-if="!loading && !data?.items.length && !error">Возвратов пока нет.</p>
      <div v-for="refund in data?.items" :key="refund.id" class="refund-row">
        <div class="refund-actions">
          <strong>{{ refund.amount }} ₽</strong>
          <n-tag
            :type="
              refund.status === 'succeeded'
                ? 'success'
                : refund.status === 'failed'
                  ? 'error'
                  : 'warning'
            "
            >{{ labels[refund.status] }}</n-tag
          >
          <span>{{ formatDateTime(refund.created_at) }}</span>
        </div>
        <p v-if="refund.pending_reason || refund.failure_reason">
          {{ refund.pending_reason || refund.failure_reason }}
        </p>
        <div class="refund-actions">
          <RouterLink
            v-if="refund.can_open_request"
            :to="{ name: 'request-detail', params: { id: refund.request_id } }"
            >Открыть заявку</RouterLink
          >
          <n-button
            v-if="refund.status === 'processing'"
            size="small"
            :loading="busy"
            @click="refresh(refund)"
            >Проверить статус</n-button
          >
          <n-button
            v-if="refund.allowed_actions.includes('reconcile')"
            size="small"
            :loading="busy"
            @click="refresh(refund, true)"
            >Сверить возврат</n-button
          >
        </div>
      </div>
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
.refund-form {
  margin-block: 12px;
  display: grid;
  gap: 6px;
}
.refund-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.refund-actions > .n-input {
  width: min(200px, 100%);
}
.refund-row {
  padding-block: 10px;
  border-top: 1px solid var(--c-border);
}
.amount-label {
  color: var(--c-text-muted);
}
small {
  color: #b42318;
}
</style>
