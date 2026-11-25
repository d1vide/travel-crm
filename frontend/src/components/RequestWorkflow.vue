<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NCheckbox, NInput, NPagination, NSpin, NTag } from 'naive-ui'
import { ApiError, apiErrorFromResponse, fieldMessages } from '@/api/errors'
import { useSessionStore } from '@/stores/session'
import { formatDateTime } from '@/utils/format'
import { useHttp } from '@/api/instance'
import { useToursApi, type TourOffer } from '@/api/tours'
import { decimalAmount, type Dto } from '@/api/workflow'
import { useCommandKey } from '@/composables/useCommandKey'
import WorkflowOffer from './WorkflowOffer.vue'
import TouristFields from './TouristFields.vue'

const { request } = defineProps<{ request: Dto['Request'] }>()
const emit = defineEmits<{ changed: [] }>()
const http = useHttp()
const session = useSessionStore()
const toursApi = useToursApi()
const key = useCommandKey()
const base = computed(() => '/requests/' + request.id)
const requestAction = (action: Dto['RequestAction']) => request.allowed_actions.includes(action)
const bookings = ref<Dto['Booking'][]>([])
const selections = ref<Dto['Selection'][]>([])
const selectedTourIds = ref<string[]>([])
const catalog = ref<TourOffer[]>([])
const destination = ref('')
const catalogPage = ref(1)
const catalogTotal = ref(0)
const catalogLoading = ref(false)
const selecting = ref(false)
const selectionPage = ref(1)
const selectionTotal = ref(0)
const bookingPage = ref(1)
const bookingTotal = ref(0)
const messages = ref('')
const busy = ref(false)
const loading = ref(true)
const selectionLink = ref('')
const touristLink = ref('')
const editingTourists = ref(false)
const touristErrors = ref<Record<string, string>>({})
const tourists = ref<Dto['TouristSubmissionItem'][]>([])
const touristVersion = ref(0)
const bookingInputs = ref<Record<string, string>>({})
const cancellationInputs = ref<Record<string, string>>({})
const paymentInputs = ref<Record<string, string>>({})
const payments = ref<Record<string, Dto['PaymentPage']>>({})
const paymentPages = ref<Record<string, number>>({})
const paymentDetails = ref<Dto['Payment']>()
const paymentLabels: Record<Dto['PaymentStatus'], string> = {
  pending: 'Ожидает',
  succeeded: 'Оплачен',
  failed: 'Отклонён',
}
const bookingLabels: Record<string, string> = {
  pending_confirmation: 'Ждёт ответа поставщика',
  confirmed: 'Подтверждена',
  rejected: 'Отклонена',
  cancellation_requested: 'Запрошена отмена',
  cancelled: 'Отменена',
}
let catalogSequence = 0

function report(cause: unknown) {
  messages.value = cause instanceof Error ? cause.message : 'Не удалось выполнить действие.'
}
async function loadSelections() {
  const data = await http.get<Dto['SelectionPage']>(
    base.value + '/selections?page=' + selectionPage.value,
  )
  selections.value = data.items
  selectionTotal.value = data.total
}
async function loadBookings() {
  const data = await http.get<Dto['BookingPage']>(
    base.value + '/bookings?page=' + bookingPage.value,
  )
  bookings.value = data.items
  bookingTotal.value = data.total
  await Promise.all(
    data.items
      .filter(
        (booking) => booking.status !== 'pending_confirmation' && booking.status !== 'rejected',
      )
      .map((booking) => loadPayments(booking.id)),
  )
}
async function loadPayments(id: string) {
  const page = paymentPages.value[id] ?? 1
  payments.value[id] = await http.get<Dto['PaymentPage']>(
    '/bookings/' + id + '/payments?page=' + page,
  )
}
async function load() {
  loading.value = true
  try {
    await Promise.all([loadSelections(), loadBookings()])
  } catch (cause) {
    report(cause)
  } finally {
    loading.value = false
  }
}
watch(selectionPage, () => {
  void loadSelections().catch(report)
})
watch(bookingPage, () => {
  void loadBookings().catch(report)
})
watch(
  () => [request.version, request.active_booking?.status, request.active_booking?.paid_amount],
  load,
  { immediate: true },
)

async function loadCatalog() {
  const seq = ++catalogSequence
  catalogLoading.value = true
  try {
    const result = await toursApi.list({
      destination: destination.value,
      page: catalogPage.value,
      page_size: 8,
    })
    if (seq !== catalogSequence) return
    catalog.value = result.items
    catalogTotal.value = result.total
  } catch (cause) {
    if (seq === catalogSequence) report(cause)
  } finally {
    if (seq === catalogSequence) catalogLoading.value = false
  }
}
watch(catalogPage, loadCatalog)
function openCatalog() {
  selecting.value = !selecting.value
  if (selecting.value) void loadCatalog()
}
function searchCatalog() {
  if (catalogPage.value === 1) void loadCatalog()
  else catalogPage.value = 1
}

async function run(operation: () => Promise<void>, reload = true) {
  if (busy.value) return
  messages.value = ''
  busy.value = true
  try {
    await operation()
    key.reset()
    if (reload) {
      emit('changed')
      await load()
    }
  } catch (cause) {
    report(cause)
    if (cause instanceof ApiError && cause.status === 409) {
      emit('changed')
      await load()
    }
  } finally {
    busy.value = false
  }
}
const options = (path: string, body: unknown) => ({ idempotencyKey: key.keyFor([path, body]) })
function post<T>(path: string, body: unknown) {
  return http.post<T>(path, body, options(path, body))
}
function put<T>(path: string, body: unknown) {
  return http.put<T>(path, body, options(path, body))
}
function publish() {
  void run(async () => {
    await post(base.value + '/selections', {
      version: request.version,
      tour_offer_ids: [...selectedTourIds.value],
    })
    selectionPage.value = 1
    selectionLink.value = ''
    selectedTourIds.value = []
    selecting.value = false
  })
}
function toggleTour(id: string, checked: boolean) {
  selectedTourIds.value = checked
    ? [...selectedTourIds.value, id]
    : selectedTourIds.value.filter((item) => item !== id)
}
function choose(id: string) {
  void run(async () => {
    await put(base.value + '/selected-tour', { version: request.version, selection_item_id: id })
  })
}
async function issueLink(path: string) {
  // Выпуск нового токена нельзя повторять автоматически после неопределённого ответа.
  const response = await fetch('/api' + path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      Authorization: 'Bearer ' + session.accessToken,
    },
  })
  if (!response.ok) throw await apiErrorFromResponse(response)
  return response.json() as Promise<Dto['PublicLink']>
}
function shareSelection(id: string) {
  void run(async () => {
    selectionLink.value = (await issueLink('/selections/' + id + '/public-link')).url
  })
}
function revoke(id: string, kind: 'selection' | 'tourist') {
  void run(async () => {
    await http.delete('/public-links/' + id)
    if (kind === 'selection') selectionLink.value = ''
    else touristLink.value = ''
  })
}
function shareTourists() {
  void run(async () => {
    touristLink.value = (await issueLink(base.value + '/tourist-link')).url
  })
}
const paymentPoll = setInterval(() => {
  const current = paymentDetails.value
  if (!document.hidden && current?.status === 'pending' && !busy.value) refreshPayment(current)
}, 5000)
onUnmounted(() => clearInterval(paymentPoll))

async function copy(url: string) {
  try {
    await navigator.clipboard.writeText(url)
  } catch {
    messages.value = 'Не удалось скопировать. Выделите и скопируйте адрес вручную.'
  }
}
function openTourists() {
  void run(async () => {
    touristErrors.value = {}
    touristVersion.value = request.version
    const data = await http.get<Dto['Tourist'][]>(base.value + '/tourists')
    tourists.value = data.map(
      ({ id, full_name, birth_date, document_type, document_number, document_expires_on }) => ({
        id,
        full_name,
        birth_date,
        document_type,
        document_number,
        document_expires_on,
      }),
    )
    if (!tourists.value.length && requestAction('edit_tourists')) addTourist()
    editingTourists.value = true
  }, false)
}
function addTourist() {
  if (tourists.value.length >= request.tourist_count) return
  tourists.value.push({
    id: null,
    full_name: '',
    birth_date: '',
    document_type: 'passport',
    document_number: '',
    document_expires_on: null,
  })
}
function closeTourists() {
  tourists.value = []
  editingTourists.value = false
}

function reloadWorkflow() {
  emit('changed')
  void load()
}
function saveTourists() {
  touristErrors.value = {}
  if (tourists.value.length !== request.tourist_count) {
    messages.value = 'Заполните данные для всех туристов заявки.'
    return
  }
  void run(async () => {
    await put(base.value + '/tourists', {
      request_version: touristVersion.value,
      tourists: tourists.value.map((row) => ({
        ...row,
        document_expires_on:
          row.document_type === 'passport' ? null : row.document_expires_on || null,
      })),
    }).catch((cause: unknown) => {
      touristErrors.value = fieldMessages(cause)
      throw cause
    })
    closeTourists()
  })
}
function createBooking() {
  void run(async () => {
    await post(base.value + '/bookings', { version: request.version })
    bookingPage.value = 1
  })
}

type CancellationAction = 'request-cancellation' | 'confirm-cancellation' | 'reject-cancellation'

function changeCancellation(booking: Dto['Booking'], action: CancellationAction) {
  const text = cancellationInputs.value[booking.id]?.trim()
  if (!text) {
    messages.value = 'Введите причину отмены или ответ поставщика.'
    return
  }
  const body =
    action === 'confirm-cancellation'
      ? { version: booking.version, supplier_response: text }
      : { version: booking.version, reason: text }
  void run(async () => {
    await post('/bookings/' + booking.id + '/actions/' + action, body)
    delete cancellationInputs.value[booking.id]
    if (action === 'confirm-cancellation') {
      selectionLink.value = ''
      touristLink.value = ''
    }
  })
}
function respond(booking: Dto['Booking'], action: 'confirm' | 'reject') {
  const value = bookingInputs.value[booking.id]?.trim()
  if (!value) {
    messages.value = 'Введите номер брони или причину отказа.'
    return
  }
  void run(async () => {
    await post(
      '/bookings/' + booking.id + '/actions/' + action,
      action === 'confirm'
        ? { version: booking.version, supplier_booking_number: value }
        : { version: booking.version, reason: value },
    )
    delete bookingInputs.value[booking.id]
  })
}
function createPayment(booking: Dto['Booking']) {
  const amount = decimalAmount(paymentInputs.value[booking.id] ?? '')
  if (!amount || amount === '0.00') {
    messages.value = 'Укажите сумму платежа больше нуля.'
    return
  }
  void run(async () => {
    paymentDetails.value = await post<Dto['Payment']>('/bookings/' + booking.id + '/payments', {
      version: booking.version,
      amount,
      currency: 'RUB',
    })
    delete paymentInputs.value[booking.id]
  })
}
function refreshPayment(payment: Dto['Payment'], reconcile = false) {
  void run(async () => {
    const path = '/payments/' + payment.id
    paymentDetails.value = reconcile
      ? await http.post<Dto['Payment']>(path + '/reconcile')
      : await http.get<Dto['Payment']>(path)
  })
}
function changePaymentPage(id: string, page: number) {
  paymentPages.value[id] = page
  void loadPayments(id).catch(report)
}
</script>

<template>
  <div class="workflow">
    <n-alert v-if="messages" type="warning" role="alert"
      >{{ messages }} <n-button size="small" @click="load">Обновить разделы</n-button></n-alert
    >
    <n-card title="Подборки туров">
      <div class="actions">
        <n-button
          v-if="requestAction('prepare_selection')"
          type="primary"
          :disabled="busy"
          @click="openCatalog"
          >{{ selecting ? 'Скрыть каталог' : 'Собрать подборку' }}</n-button
        >
      </div>
      <div v-if="selecting" class="stack">
        <form class="actions" @submit.prevent="searchCatalog">
          <n-input
            v-model:value="destination"
            placeholder="Направление"
            aria-label="Направление"
          /><n-button attr-type="submit">Найти</n-button>
        </form>
        <n-spin :show="catalogLoading">
          <div class="offer-grid">
            <WorkflowOffer v-for="tour in catalog" :key="tour.id" :offer="tour">
              <n-checkbox
                :checked="selectedTourIds.includes(tour.id)"
                @update:checked="(checked) => toggleTour(tour.id, checked)"
                >Добавить в подборку</n-checkbox
              >
            </WorkflowOffer>
          </div>
          <p v-if="!catalogLoading && !catalog.length">Туры не найдены.</p>
        </n-spin>
        <n-pagination
          v-if="catalogTotal > 8"
          v-model:page="catalogPage"
          :page-size="8"
          :item-count="catalogTotal"
        />
        <n-button
          type="primary"
          :disabled="!selectedTourIds.length"
          :loading="busy"
          @click="publish"
          >Опубликовать · {{ selectedTourIds.length }}</n-button
        >
      </div>
      <div v-if="selectionLink" class="actions">
        <n-input
          :value="selectionLink"
          readonly
          aria-label="Публичная ссылка на подборку"
        /><n-button @click="copy(selectionLink)">Скопировать ссылку</n-button>
      </div>
      <p v-if="!loading && !selections.length">Подборок пока нет.</p>
      <section v-for="(selection, index) in selections" :key="selection.id" class="stack">
        <h3>
          {{ selectionPage === 1 && index === 0 ? 'Последняя подборка' : 'Предыдущая подборка' }} ·
          {{ formatDateTime(selection.created_at) }}
        </h3>
        <div class="actions">
          <n-button
            v-if="
              selectionPage === 1 &&
              index === 0 &&
              request.status === 'offer_prepared' &&
              !request.active_booking
            "
            :loading="busy"
            @click="shareSelection(selection.id)"
            >{{
              selection.public_link?.is_active ? 'Перевыпустить ссылку' : 'Выдать ссылку'
            }}</n-button
          >
          <n-button
            v-if="selection.public_link?.is_active"
            :loading="busy"
            @click="revoke(selection.public_link.id, 'selection')"
            >Отозвать ссылку</n-button
          >
        </div>
        <div class="offer-grid">
          <WorkflowOffer
            v-for="entry in selection.items"
            :key="entry.id"
            :offer="entry.offer_snapshot"
          >
            <n-tag v-if="request.selected_selection_item_id === entry.id" type="success"
              >Выбран</n-tag
            >
            <n-button
              v-else-if="selectionPage === 1 && index === 0 && requestAction('select_tour')"
              :loading="busy"
              @click="choose(entry.id)"
              >Зафиксировать выбор клиента</n-button
            >
          </WorkflowOffer>
        </div>
      </section>
      <n-pagination
        v-if="selectionTotal > 20"
        v-model:page="selectionPage"
        :page-size="20"
        :item-count="selectionTotal"
      />
    </n-card>
    <n-card title="Данные туристов">
      <p>Получено {{ request.tourists_received }} из {{ request.tourist_count }}</p>
      <div class="actions">
        <n-button
          v-if="requestAction('issue_tourist_link')"
          :loading="busy"
          @click="shareTourists"
          >{{
            request.tourist_link?.is_active ? 'Перевыпустить ссылку' : 'Выдать ссылку на форму'
          }}</n-button
        >
        <n-button
          v-if="request.tourist_link?.is_active"
          :loading="busy"
          @click="revoke(request.tourist_link.id, 'tourist')"
          >Отозвать ссылку</n-button
        >
        <n-button
          v-if="requestAction('edit_tourists') || request.tourists_received"
          :loading="busy"
          @click="openTourists"
          >{{ requestAction('edit_tourists') ? 'Заполнить данные' : 'Посмотреть данные' }}</n-button
        >
      </div>
      <div v-if="touristLink" class="actions">
        <n-input :value="touristLink" readonly aria-label="Публичная ссылка на форму" /><n-button
          @click="copy(touristLink)"
          >Скопировать ссылку</n-button
        >
      </div>
      <div v-if="editingTourists" class="stack">
        <div class="actions">
          <n-button
            v-if="requestAction('edit_tourists') && tourists.length < request.tourist_count"
            @click="addTourist"
            >Добавить туриста</n-button
          ><n-button @click="closeTourists">Закрыть форму</n-button>
        </div>
        <TouristFields
          v-model="tourists"
          :busy="busy"
          :errors="touristErrors"
          :readonly="!requestAction('edit_tourists')"
          @save="saveTourists"
        />
      </div>
    </n-card>
    <n-card title="Бронирование и оплата">
      <n-button
        v-if="requestAction('create_booking')"
        type="primary"
        :loading="busy"
        @click="createBooking"
        >Создать бронь</n-button
      >
      <p v-if="!loading && !bookings.length">Попыток бронирования пока нет.</p>
      <section v-for="booking in bookings" :key="booking.id" class="stack booking">
        <div class="booking-title">
          <h3>{{ booking.offer_snapshot.title }}</h3>
          <n-tag>{{ bookingLabels[booking.status] ?? booking.status }}</n-tag>
        </div>
        <WorkflowOffer :offer="booking.offer_snapshot" />
        <p v-if="booking.supplier_booking_number">
          Номер у поставщика: {{ booking.supplier_booking_number }}
        </p>
        <p v-if="booking.rejection_reason">Причина отказа: {{ booking.rejection_reason }}</p>
        <p v-if="booking.cancellation_reason">Причина отмены: {{ booking.cancellation_reason }}</p>
        <p v-if="booking.cancellation_response">
          Ответ поставщика: {{ booking.cancellation_response }}
        </p>
        <n-alert
          v-if="booking.status === 'cancelled' && booking.paid_amount !== '0.00'"
          type="warning"
        >
          Бронь отменена. Деньги автоматически не возвращены. Возврат оформляется отдельно.
        </n-alert>
        <div v-if="booking.allowed_actions.includes('request_cancellation')" class="actions">
          <n-input
            v-model:value="cancellationInputs[booking.id]"
            aria-label="Причина отмены брони"
            placeholder="Причина отмены брони"
          />
          <n-button :loading="busy" @click="changeCancellation(booking, 'request-cancellation')"
            >Запросить отмену брони</n-button
          >
        </div>
        <template v-else-if="booking.status === 'cancellation_requested'">
          <div class="actions">
            <n-input
              v-model:value="cancellationInputs[booking.id]"
              aria-label="Ответ поставщика на отмену"
              placeholder="Ответ поставщика на отмену"
            />
            <n-button
              v-if="booking.allowed_actions.includes('confirm_cancellation')"
              type="warning"
              :loading="busy"
              @click="changeCancellation(booking, 'confirm-cancellation')"
              >Подтвердить отмену</n-button
            >
            <n-button
              v-if="booking.allowed_actions.includes('reject_cancellation')"
              :loading="busy"
              @click="changeCancellation(booking, 'reject-cancellation')"
              >Внести отказ в отмене</n-button
            >
          </div>
          <p v-if="booking.reserved_payment_amount !== '0.00'">
            Подтверждение отмены станет доступно после обработки ожидающих платежей.
          </p>
        </template>
        <div
          v-if="
            booking.allowed_actions.includes('confirm') ||
            booking.allowed_actions.includes('reject')
          "
          class="actions"
        >
          <n-input
            v-model:value="bookingInputs[booking.id]"
            aria-label="Номер брони или причина отказа"
            placeholder="Номер брони или причина отказа"
          />
          <n-button
            v-if="booking.allowed_actions.includes('confirm')"
            :loading="busy"
            @click="respond(booking, 'confirm')"
            >Подтвердить бронь</n-button
          >
          <n-button
            v-if="booking.allowed_actions.includes('reject')"
            :loading="busy"
            @click="respond(booking, 'reject')"
            >Внести отказ</n-button
          >
        </div>
        <template v-if="payments[booking.id]">
          <p>
            Оплачено {{ booking.paid_amount }} ₽ · В резерве {{ booking.reserved_payment_amount }} ₽
            · Остаток {{ booking.remaining_amount }} ₽
          </p>
          <form
            v-if="booking.allowed_actions.includes('create_payment')"
            class="actions"
            @submit.prevent="createPayment(booking)"
          >
            <n-input
              v-model:value="paymentInputs[booking.id]"
              aria-label="Сумма платежа"
              :placeholder="'Доступно ' + booking.available_payment_amount + ' ₽'"
            />
            <n-button attr-type="submit" type="primary" :loading="busy">Создать платёж</n-button>
          </form>
          <div v-for="payment in payments[booking.id]?.items" :key="payment.id" class="actions">
            <strong>{{ payment.amount }} ₽</strong
            ><n-tag>{{ paymentLabels[payment.status] }}</n-tag>
            <a
              v-if="payment.payment_url && payment.status === 'pending'"
              :href="payment.payment_url"
              target="_blank"
              rel="noopener noreferrer"
              >Открыть тестовую оплату</a
            >
            <n-button
              v-if="payment.payment_url && payment.status === 'pending'"
              @click="copy(payment.payment_url)"
              >Копировать ссылку</n-button
            >
            <n-button :loading="busy" @click="refreshPayment(payment)">Проверить статус</n-button>
            <n-button
              v-if="payment.allowed_actions.includes('reconcile')"
              :loading="busy"
              @click="refreshPayment(payment, true)"
              >Сверить платёж</n-button
            >
            <span>{{ payment.failure_reason || payment.pending_reason }}</span>
          </div>
          <n-pagination
            v-if="(payments[booking.id]?.total ?? 0) > 20"
            :page="paymentPages[booking.id] ?? 1"
            :page-size="20"
            :item-count="payments[booking.id]?.total"
            @update:page="(page) => changePaymentPage(booking.id, page)"
          />
        </template>
      </section>
      <n-pagination
        v-if="bookingTotal > 20"
        v-model:page="bookingPage"
        :page-size="20"
        :item-count="bookingTotal"
      />
      <n-alert v-if="paymentDetails" type="info" class="stack">
        {{ paymentLabels[paymentDetails.status] }} · {{ paymentDetails.amount }} ₽
        {{ paymentDetails.failure_reason || paymentDetails.pending_reason }}
      </n-alert>
      <n-button size="small" @click="reloadWorkflow">Обновить данные</n-button>
    </n-card>
  </div>
</template>

<style scoped>
.workflow,
.stack {
  display: grid;
  gap: 12px;
}
.stack {
  margin-block: 12px;
}
.actions,
.booking-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-block: 8px;
}
.actions > .n-input {
  flex: 1;
  min-width: min(100%, 220px);
}
.offer-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr));
  gap: 8px;
}
h3,
p {
  margin: 0;
}
.booking + .booking {
  border-top: 1px solid var(--c-border);
  padding-top: 12px;
}
</style>
