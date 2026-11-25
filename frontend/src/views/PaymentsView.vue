<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NPagination, NSpace, NSpin, NTag } from 'naive-ui'
import PageHeader from '@/components/PageHeader.vue'
import { useHttp } from '@/api/instance'
import type { Dto } from '@/api/workflow'
import { formatDateTime } from '@/utils/format'
const http = useHttp()
const mode = ref<'bookings' | 'payments'>('bookings')
const page = ref(1)
const bookings = ref<Dto['FinancialBookingPage']>()
const payments = ref<Dto['PaymentPage']>()
const detail = ref<Dto['Payment']>()
const error = ref('')
const detailError = ref('')
const busy = ref(false)
const loading = ref(false)
let sequence = 0
const currentPage = computed(() => (mode.value === 'bookings' ? bookings.value : payments.value))
const bookingStatus: Record<Dto['BookingStatus'], string> = {
  pending_confirmation: 'Ждёт подтверждения',
  confirmed: 'Подтверждена',
  rejected: 'Отклонена',
  cancellation_requested: 'Запрошена отмена',
  cancelled: 'Отменена',
}
const paymentStatus: Record<Dto['PaymentStatus'], string> = {
  pending: 'Ожидает оплаты',
  succeeded: 'Оплачен',
  failed: 'Отклонён',
}
function change(next: typeof mode.value) {
  mode.value = next
  page.value = 1
  detail.value = undefined
  detailError.value = ''
}
async function load() {
  const seq = ++sequence
  loading.value = true
  error.value = ''
  try {
    const query = '?page=' + page.value
    if (mode.value === 'bookings') {
      const result = await http.get<Dto['FinancialBookingPage']>('/financial-bookings' + query)
      if (seq === sequence) bookings.value = result
    } else {
      const result = await http.get<Dto['PaymentPage']>('/payments' + query)
      if (seq === sequence) payments.value = result
    }
  } catch (cause) {
    if (seq === sequence)
      error.value = cause instanceof Error ? cause.message : 'Не удалось загрузить данные.'
  } finally {
    if (seq === sequence) loading.value = false
  }
}
async function view(payment: Dto['Payment'], reconcile = false) {
  if (busy.value) return
  busy.value = true
  detailError.value = ''
  try {
    const path = '/payments/' + payment.id
    detail.value = reconcile
      ? await http.post<Dto['Payment']>(path + '/reconcile')
      : await http.get<Dto['Payment']>(path)
    await load()
  } catch (cause) {
    detailError.value = cause instanceof Error ? cause.message : 'Не удалось проверить платёж.'
  } finally {
    busy.value = false
  }
}
watch([mode, page], load, { immediate: true })
</script>
<template>
  <PageHeader title="Оплаты и возвраты" />
  <n-space class="actions">
    <n-button :type="mode === 'bookings' ? 'primary' : 'default'" @click="change('bookings')"
      >Финансовая сводка</n-button
    >
    <n-button :type="mode === 'payments' ? 'primary' : 'default'" @click="change('payments')"
      >Платежи</n-button
    >
    <n-button @click="load">Обновить</n-button>
  </n-space>
  <n-alert v-if="error" type="error">{{ error }}</n-alert>
  <n-alert v-if="detailError" type="error">{{ detailError }}</n-alert>
  <n-alert v-if="detail && mode === 'payments'" type="info" class="actions">
    {{ paymentStatus[detail.status] }} · {{ detail.amount }} ₽ ·
    {{ formatDateTime(detail.created_at) }}
    {{ detail.pending_reason || detail.failure_reason }}
    <n-button
      v-if="detail.allowed_actions.includes('reconcile')"
      :loading="busy"
      @click="view(detail, true)"
      >Сверить платёж</n-button
    >
  </n-alert>
  <n-spin :show="loading">
    <n-card v-if="!loading && !error && !currentPage?.items.length">Записей пока нет.</n-card>
    <div v-else-if="mode === 'bookings'" class="items">
      <n-card v-for="booking in bookings?.items" :key="booking.id" size="small">
        <div class="row">
          <strong>{{ booking.total_amount }} ₽</strong
          ><n-tag>{{ bookingStatus[booking.status] }}</n-tag
          ><span>{{ formatDateTime(booking.created_at) }}</span>
        </div>
        <p>
          Оплачено {{ booking.paid_amount }} ₽ · В резерве {{ booking.reserved_payment_amount }} ₽ ·
          Остаток {{ booking.remaining_amount }} ₽ · Возвращено {{ booking.refunded_amount }} ₽
        </p>
        <RouterLink
          v-if="booking.can_open_request"
          :to="{ name: 'request-detail', params: { id: booking.request_id } }"
          >Открыть заявку</RouterLink
        >
      </n-card>
    </div>
    <div v-else class="items">
      <n-card v-for="payment in payments?.items" :key="payment.id" size="small">
        <div class="row">
          <strong>{{ payment.amount }} ₽</strong><n-tag>{{ paymentStatus[payment.status] }}</n-tag
          ><span>{{ formatDateTime(payment.created_at) }}</span>
        </div>
        <div class="row">
          <n-button size="small" :disabled="busy" @click="view(payment)">Проверить статус</n-button
          ><RouterLink
            v-if="payment.can_open_request"
            :to="{ name: 'request-detail', params: { id: payment.request_id } }"
            >Открыть заявку</RouterLink
          >
        </div>
      </n-card>
    </div>
    <n-pagination
      v-if="currentPage && currentPage.total > currentPage.page_size"
      v-model:page="page"
      class="actions"
      :page-size="currentPage.page_size"
      :item-count="currentPage.total"
    />
  </n-spin>
</template>
<style scoped>
.items {
  display: grid;
  gap: 8px;
}
.row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-block: 4px;
}
.actions {
  margin-block: 12px;
}
</style>
