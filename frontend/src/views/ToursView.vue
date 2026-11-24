<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPagination,
  NSpin,
} from 'naive-ui'
import { ApiError } from '@/api/errors'
import { useToursApi, type TourFilters, type TourOffer } from '@/api/tours'
import PageHeader from '@/components/PageHeader.vue'
import { formatDate } from '@/utils/format'

const api = useToursApi()
const pageSize = 12
const defaultFields = () => ({ destination: '', from: '', until: '', tourists: '', price: '' })
const fields = ref(defaultFields())
const filters = ref<TourFilters>({})
const page = ref(1)
const total = ref(0)
const tours = ref<TourOffer[]>([])
const loading = ref(true)
const error = ref('')
const formError = ref('')
let listSequence = 0

function applyFilters() {
  const { destination, from, until, tourists, price } = fields.value
  const count = tourists.trim()
  const amount = price.trim().replace(',', '.')
  formError.value = ''
  if (from && until && from > until) {
    formError.value = 'Дата окончания должна быть не раньше даты начала.'
  } else if (count && (!/^\d+$/.test(count) || Number(count) < 1 || Number(count) > 2147483647)) {
    formError.value = 'Укажите целое число туристов от 1 до 2147483647.'
  } else if (amount && !/^\d{1,12}(\.\d{1,2})?$/.test(amount)) {
    formError.value = 'Укажите цену в рублях с точностью до копеек.'
  }
  if (formError.value) return
  const [rubles = '', kopecks = ''] = amount.split('.')
  page.value = 1
  filters.value = {
    destination,
    starts_from: from,
    ends_until: until,
    tourist_count: count ? Number(count) : undefined,
    max_price: amount ? `${rubles}.${kopecks.padEnd(2, '0')}` : undefined,
  }
}

function reset() {
  fields.value = defaultFields()
  applyFilters()
}

async function load() {
  const sequence = ++listSequence
  loading.value = true
  error.value = ''
  try {
    const result = await api.list({ ...filters.value, page: page.value, page_size: pageSize })
    if (sequence !== listSequence) return
    tours.value = result.items
    total.value = result.total
  } catch (cause) {
    if (sequence !== listSequence) return
    error.value = cause instanceof ApiError ? cause.message : 'Не удалось загрузить каталог.'
  } finally {
    if (sequence === listSequence) loading.value = false
  }
}

watch([filters, page], load, { immediate: true })
const filtered = computed(() => Object.values(filters.value).some(Boolean))

const detailId = ref('')
const detail = ref<TourOffer>()
const detailLoading = ref(false)
const detailError = ref('')
const detailOpen = ref(false)
let detailSequence = 0

async function openTour(id: string) {
  const sequence = ++detailSequence
  detailId.value = id
  detailOpen.value = true
  detail.value = undefined
  detailError.value = ''
  detailLoading.value = true
  try {
    const result = await api.get(id)
    if (sequence === detailSequence) detail.value = result
  } catch (cause) {
    if (sequence !== detailSequence) return
    detailError.value = cause instanceof ApiError ? cause.message : 'Не удалось открыть тур.'
  } finally {
    if (sequence === detailSequence) detailLoading.value = false
  }
}

function priceLabel(price: string) {
  const [rubles, kopecks] = price.split('.')
  return `${rubles?.replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f')}${kopecks && kopecks !== '00' ? ',' + kopecks : ''} ₽`
}
</script>

<template>
  <PageHeader title="Каталог туров" />
  <n-card class="search-card">
    <n-form @submit.prevent="applyFilters">
      <div class="filter-grid">
        <n-form-item label="Направление" label-for="tour-destination" :show-feedback="false">
          <n-input
            v-model:value="fields.destination"
            :input-props="{ id: 'tour-destination' }"
            placeholder="Например, Сочи"
            clearable
          />
        </n-form-item>
        <n-form-item label="Начало не раньше" label-for="tour-from" :show-feedback="false">
          <input id="tour-from" v-model="fields.from" class="date-input" type="date" />
        </n-form-item>
        <n-form-item label="Окончание не позже" label-for="tour-until" :show-feedback="false">
          <input id="tour-until" v-model="fields.until" class="date-input" type="date" />
        </n-form-item>
        <n-form-item label="Туристы" label-for="tour-count" :show-feedback="false">
          <n-input
            v-model:value="fields.tourists"
            :input-props="{ id: 'tour-count', inputmode: 'numeric' }"
            placeholder="Любое число"
          />
        </n-form-item>
        <n-form-item label="Бюджет до, ₽" label-for="tour-price" :show-feedback="false">
          <n-input
            v-model:value="fields.price"
            :input-props="{ id: 'tour-price', inputmode: 'decimal' }"
            placeholder="Без ограничения"
          />
        </n-form-item>
      </div>
      <n-alert v-if="formError" type="warning" class="message">{{ formError }}</n-alert>
      <div class="actions">
        <n-button type="primary" attr-type="submit">Найти туры</n-button>
        <n-button attr-type="button" @click="reset">Сбросить</n-button>
      </div>
    </n-form>
  </n-card>

  <n-alert v-if="error" type="error" class="message">
    {{ error }} <n-button size="small" @click="load">Повторить</n-button>
  </n-alert>
  <n-spin v-else :show="loading">
    <div class="result-count" aria-live="polite">
      {{ loading ? 'Загружаем каталог…' : `Предложений: ${total}` }}
    </div>
    <div v-if="tours.length" class="tour-grid">
      <n-card v-for="tour in tours" :key="tour.id" class="tour-card">
        <p class="muted destination">{{ tour.destination }}</p>
        <h2>{{ tour.title }}</h2>
        <p class="muted">{{ formatDate(tour.starts_on) }} — {{ formatDate(tour.ends_on) }}</p>
        <div class="tour-footer">
          <div>
            <strong>{{ priceLabel(tour.price) }}</strong>
            <div class="muted">Туристов: {{ tour.tourist_count }}</div>
          </div>
          <n-button :aria-label="`Подробнее: ${tour.title}`" @click="openTour(tour.id)"
            >Подробнее</n-button
          >
        </div>
      </n-card>
    </div>
    <n-empty
      v-else-if="!loading"
      :description="filtered ? 'По этим фильтрам туров нет' : 'Предложений пока нет'"
    />
    <n-pagination
      v-if="total > pageSize"
      v-model:page="page"
      :item-count="total"
      :page-size="pageSize"
      class="pagination"
    />
  </n-spin>

  <n-modal
    v-model:show="detailOpen"
    preset="card"
    :title="detail?.title ?? 'Карточка тура'"
    class="tour-modal"
  >
    <n-alert v-if="detailError" type="error">
      {{ detailError }} <n-button size="small" @click="openTour(detailId)">Повторить</n-button>
    </n-alert>
    <n-spin v-else-if="detailLoading" description="Загружаем тур…" />
    <template v-else-if="detail">
      <dl class="tour-data">
        <div>
          <dt>Направление</dt>
          <dd>{{ detail.destination }}</dd>
        </div>
        <div>
          <dt>Даты</dt>
          <dd>{{ formatDate(detail.starts_on) }} — {{ formatDate(detail.ends_on) }}</dd>
        </div>
        <div>
          <dt>Поставщик</dt>
          <dd>{{ detail.supplier }}</dd>
        </div>
        <div>
          <dt>Цена за всех туристов ({{ detail.tourist_count }})</dt>
          <dd>{{ priceLabel(detail.price) }}</dd>
        </div>
      </dl>
      <h2>Что входит в тур</h2>
      <ul v-if="detail.services.length">
        <li v-for="(service, index) in detail.services" :key="index">{{ service }}</li>
      </ul>
      <p v-else class="muted">Поставщик не указал услуги.</p>
    </template>
  </n-modal>
</template>

<style scoped>
.filter-grid,
.tour-grid {
  display: grid;
  gap: var(--space-4);
}
.filter-grid {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr));
}
.tour-grid {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 270px), 1fr));
}
.date-input {
  width: 100%;
  min-width: 0;
  height: 34px;
  padding-inline: 8px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  color: inherit;
  font: inherit;
}
.actions,
.tour-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
.tour-footer {
  justify-content: space-between;
}
.tour-footer strong {
  font-size: 19px;
  font-variant-numeric: tabular-nums;
}
.message,
.pagination {
  margin-block: var(--space-4);
}
.result-count {
  margin-block: var(--space-4);
  color: var(--c-text-muted);
}
.muted {
  color: var(--c-text-muted);
}
.destination {
  margin-top: 0;
}
h2 {
  margin: 0;
  font-size: 16px;
}
.tour-modal {
  width: min(540px, calc(100vw - 32px));
}
.tour-data {
  display: grid;
  gap: var(--space-3);
  margin: 0 0 var(--space-4);
}
.tour-data dt {
  color: var(--c-text-muted);
}
.tour-data dd {
  margin: 0;
  font-weight: 500;
}
</style>
