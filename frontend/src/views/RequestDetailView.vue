<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NInput, NPagination, NSelect, NSpin, NTag } from 'naive-ui'
import { ApiError } from '@/api/errors'
import { useClientsApi } from '@/api/clients'
import { useRequestsApi, type RequestUpdate, type TravelRequest } from '@/api/requests'
import { useCommandKey } from '@/composables/useCommandKey'
import { useSessionStore } from '@/stores/session'
import PageHeader from '@/components/PageHeader.vue'
import SearchInput from '@/components/SearchInput.vue'
import { formatDate, formatDateTime } from '@/utils/format'
import { requestStatuses } from '@/utils/requestStatus'

const route = useRoute()
const router = useRouter()
const api = useRequestsApi()
const clientsApi = useClientsApi()
const session = useSessionStore()
const commandKey = useCommandKey()
const item = ref<TravelRequest>()
const editing = ref(false)
const loading = ref(false)
const busy = ref(false)
const loadError = ref('')
const error = ref('')
const directoryError = ref('')
const historyError = ref('')
const query = ref('')
const clientId = ref<string | null>(null)
const assignee = ref<string | null>(null)
const clients = ref<{ label: string; value: string }[]>([])
const managers = ref<{ label: string; value: string }[]>([])
const reason = ref('')
const cancelling = ref(false)
const fields = ref({ destination: '', start: '', end: '', count: '2', budget: '', wishes: '' })
const history = ref<Awaited<ReturnType<typeof api.history>>>()
const historyPage = ref(1)
const historyLabels: Record<string, string> = {
  created: 'Создание заявки',
  assignee_changed: 'Смена ответственного',
  'start-work': 'Взята в работу',
  cancel: 'Отмена заявки',
  resume: 'Возобновление заявки',
}
let generation = 0
let searchSequence = 0
let historySequence = 0
const message = (cause: unknown) =>
  cause instanceof ApiError ? cause.message : 'Не удалось выполнить запрос.'

async function loadClients() {
  const seq = ++searchSequence
  directoryError.value = ''
  try {
    const result = await clientsApi.list({ q: query.value, pageSize: 20, sort: 'full_name' })
    if (seq !== searchSequence) return
    const selected = clients.value.find((person) => person.value === clientId.value)
    const options = result.items.map((person) => ({ label: person.full_name, value: person.id }))
    if (selected && !options.some((person) => person.value === selected.value))
      options.unshift(selected)
    clients.value = options
  } catch (cause) {
    if (seq === searchSequence) directoryError.value = message(cause)
  }
}

async function loadManagers() {
  const first = await api.managers(1)
  const users = [...first.items]
  for (let page = 2; page <= Math.ceil(first.total / first.page_size); page++) {
    users.push(...(await api.managers(page)).items)
  }
  managers.value = users.map((user) => ({ label: user.full_name, value: user.id }))
}

async function loadHistory() {
  if (!item.value) return
  const seq = ++historySequence
  historyError.value = ''
  try {
    const result = await api.history(item.value.id, historyPage.value)
    if (seq === historySequence) history.value = result
  } catch (cause) {
    if (seq === historySequence) historyError.value = message(cause)
  }
}

async function load() {
  const current = ++generation
  searchSequence++
  historySequence++
  item.value = undefined
  history.value = undefined
  historyPage.value = 1
  loadError.value = ''
  directoryError.value = ''
  error.value = ''
  editing.value = false
  cancelling.value = false
  clientId.value = null
  assignee.value = null
  reason.value = ''
  fields.value = { destination: '', start: '', end: '', count: '2', budget: '', wishes: '' }
  commandKey.reset()
  loading.value = true
  try {
    if (route.name === 'request-new') {
      const client = route.query.client
      if (typeof client === 'string') {
        const selected = await clientsApi.get(client)
        if (current !== generation) return
        clients.value = [{ label: selected.full_name, value: selected.id }]
        clientId.value = selected.id
      }
      await loadClients()
    } else {
      const result = await api.get(String(route.params.id))
      if (current !== generation) return
      item.value = result
      assignee.value = result.manager_id
      void loadHistory()
    }
    if (session.role === 'head') {
      try {
        await loadManagers()
      } catch (cause) {
        if (current === generation) directoryError.value = message(cause)
      }
    }
  } catch (cause) {
    if (current === generation) loadError.value = message(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}

watch(() => route.fullPath, load, { immediate: true })
watch(query, () => {
  void loadClients()
})
watch(historyPage, () => {
  void loadHistory()
})

function edit(request: TravelRequest) {
  fields.value = {
    destination: request.destination,
    start: request.starts_on,
    end: request.ends_on,
    count: String(request.tourist_count),
    budget: request.budget,
    wishes: request.wishes,
  }
  error.value = ''
  editing.value = true
}

function formData(): Omit<RequestUpdate, 'version'> | undefined {
  const { destination, start, end, count, budget, wishes } = fields.value
  const amount = budget.trim().replace(',', '.')
  if (!destination.trim() || !start || !end || start > end) {
    error.value = 'Укажите направление и даты поездки. Окончание должно быть не раньше начала.'
  } else if (!/^\d+$/.test(count) || Number(count) < 1 || Number(count) > 2147483647) {
    error.value = 'Укажите допустимое целое число туристов.'
  } else if (!/^\d{1,12}(\.\d{1,2})?$/.test(amount)) {
    error.value = 'Укажите бюджет в рублях с точностью до копеек.'
  }
  if (error.value) return
  const [rubles, kopecks = ''] = amount.split('.')
  return {
    destination: destination.trim(),
    starts_on: start,
    ends_on: end,
    tourist_count: Number(count),
    budget: rubles + '.' + kopecks.padEnd(2, '0'),
    wishes,
  }
}

async function run(action: () => Promise<TravelRequest>) {
  if (busy.value) return
  const current = generation
  busy.value = true
  error.value = ''
  try {
    const result = await action()
    if (current !== generation) return
    commandKey.reset()
    if (route.name === 'request-new') {
      await router.replace({ name: 'request-detail', params: { id: result.id } })
      return
    }
    item.value = result
    assignee.value = result.manager_id
    editing.value = false
    cancelling.value = false
    reason.value = ''
    if (historyPage.value === 1) void loadHistory()
    else historyPage.value = 1
  } catch (cause) {
    if (current !== generation) return
    if (cause instanceof ApiError && cause.code === 'version_conflict' && item.value) {
      try {
        const fresh = await api.get(item.value.id)
        if (current !== generation) return
        item.value = fresh
        void loadHistory()
        error.value =
          'Заявку успели изменить. Актуальная карточка загружена. Проверьте данные перед повторной отправкой.'
      } catch (refreshError) {
        if (current === generation) error.value = message(refreshError)
      }
    } else {
      error.value = message(cause)
    }
  } finally {
    busy.value = false
  }
}

function save() {
  error.value = ''
  const data = formData()
  if (!data) return
  const current = item.value
  if (current) {
    const body = { ...data, version: current.version }
    void run(() => api.update(current.id, body, commandKey.keyFor(['update', current.id, body])))
  } else if (clientId.value) {
    const body = { ...data, client_id: clientId.value, manager_id: assignee.value }
    void run(() => api.create(body, commandKey.keyFor(['create', body])))
  } else error.value = 'Выберите клиента.'
}

function assign() {
  const current = item.value
  if (!current || !assignee.value) return
  const body = { version: current.version, manager_id: assignee.value }
  void run(() => api.assign(current.id, body, commandKey.keyFor(['assign', current.id, body])))
}

function changeStatus(action: 'start-work' | 'cancel' | 'resume') {
  const current = item.value
  if (!current) return
  if (action === 'cancel' && !reason.value.trim()) {
    error.value = 'Укажите причину отмены.'
    return
  }
  const body =
    action === 'cancel'
      ? { version: current.version, reason: reason.value.trim() }
      : { version: current.version }
  void run(() =>
    api.command(current.id, action, body, commandKey.keyFor([action, current.id, body])),
  )
}
</script>

<template>
  <RouterLink :to="{ name: 'requests' }" class="back">← К заявкам</RouterLink>
  <PageHeader
    :title="route.name === 'request-new' ? 'Новая заявка' : (item?.destination ?? 'Заявка')"
  />
  <n-alert v-if="loadError" type="error"
    >{{ loadError }} <n-button @click="load">Повторить</n-button></n-alert
  >
  <n-spin v-else-if="loading" description="Загружаем заявку…" />
  <template v-else>
    <n-alert v-if="error" type="error" class="block" role="alert">{{ error }}</n-alert>
    <n-alert v-if="directoryError" type="warning" class="block">{{ directoryError }}</n-alert>
    <n-card v-if="item" class="block">
      <n-tag :bordered="false">{{ requestStatuses[item.status] }}</n-tag>
      <dl class="grid summary">
        <div>
          <dt>Клиент</dt>
          <dd>
            <RouterLink :to="{ name: 'client-detail', params: { id: item.client_id } }">{{
              item.client.full_name
            }}</RouterLink>
          </dd>
        </div>
        <div>
          <dt>Ответственный</dt>
          <dd>{{ item.manager.full_name }}</dd>
        </div>
        <div>
          <dt>Даты поездки</dt>
          <dd>{{ formatDate(item.starts_on) }} — {{ formatDate(item.ends_on) }}</dd>
        </div>
        <div>
          <dt>Туристы</dt>
          <dd>{{ item.tourist_count }}</dd>
        </div>
        <div>
          <dt>Бюджет</dt>
          <dd>{{ item.budget.replace('.', ',') }} ₽</dd>
        </div>
        <div>
          <dt>Пожелания</dt>
          <dd>{{ item.wishes || '—' }}</dd>
        </div>
        <div v-if="item.cancellation_reason">
          <dt>Причина отмены</dt>
          <dd>{{ item.cancellation_reason }}</dd>
        </div>
      </dl>
      <div class="actions">
        <n-button
          v-if="item.allowed_actions.includes('start_work')"
          type="primary"
          :disabled="busy"
          @click="changeStatus('start-work')"
          >Взять в работу</n-button
        >
        <n-button
          v-if="item.allowed_actions.includes('resume')"
          type="primary"
          :disabled="busy"
          @click="changeStatus('resume')"
          >Возобновить заявку</n-button
        >
        <n-button
          v-if="item.allowed_actions.includes('update') && !editing"
          :disabled="busy"
          @click="edit(item)"
          >Редактировать</n-button
        >
        <n-button
          v-if="item.allowed_actions.includes('cancel') && !cancelling"
          :disabled="busy"
          @click="cancelling = true"
          >Отменить заявку</n-button
        >
      </div>
      <form
        v-if="cancelling && item.allowed_actions.includes('cancel')"
        class="block"
        @submit.prevent="changeStatus('cancel')"
      >
        <label for="request-reason">Причина отмены</label>
        <n-input v-model:value="reason" :input-props="{ id: 'request-reason' }" />
        <div class="actions">
          <n-button type="error" attr-type="submit" :loading="busy">Подтвердить отмену</n-button
          ><n-button @click="cancelling = false">Назад</n-button>
        </div>
      </form>
      <form v-if="item.allowed_actions.includes('reassign')" class="block" @submit.prevent="assign">
        <label id="request-assignee-label">Новый ответственный</label>
        <div class="actions">
          <n-select
            v-model:value="assignee"
            :options="managers"
            filterable
            class="select"
            aria-labelledby="request-assignee-label"
          /><n-button
            attr-type="submit"
            :disabled="!assignee || assignee === item.manager_id"
            :loading="busy"
            >Назначить</n-button
          >
        </div>
      </form>
    </n-card>
    <n-card v-if="!item || editing" class="block">
      <form @submit.prevent="save">
        <div v-if="!item" class="grid">
          <div>
            <label id="request-client-label">Клиент</label>
            <SearchInput v-model="query" placeholder="Найти клиента по имени или контакту" />
            <n-select
              v-model:value="clientId"
              :options="clients"
              placeholder="Выберите клиента"
              aria-labelledby="request-client-label"
            />
          </div>
          <div v-if="session.role === 'head'">
            <label id="request-manager-label">Ответственный</label>
            <n-select
              v-model:value="assignee"
              clearable
              filterable
              :options="managers"
              placeholder="Назначить себе"
              aria-labelledby="request-manager-label"
            />
          </div>
        </div>
        <div class="grid block">
          <div>
            <label for="request-destination">Направление</label
            ><n-input
              v-model:value="fields.destination"
              :input-props="{ id: 'request-destination' }"
              placeholder="Например, Сочи"
            />
          </div>
          <div>
            <label for="request-start">Начало поездки</label
            ><input id="request-start" v-model="fields.start" type="date" required />
          </div>
          <div>
            <label for="request-end">Окончание поездки</label
            ><input id="request-end" v-model="fields.end" type="date" required />
          </div>
          <div>
            <label for="request-count">Число туристов</label
            ><n-input
              v-model:value="fields.count"
              :input-props="{ id: 'request-count', inputmode: 'numeric' }"
            />
          </div>
          <div>
            <label for="request-budget">Бюджет, ₽</label
            ><n-input
              v-model:value="fields.budget"
              :input-props="{ id: 'request-budget', inputmode: 'decimal' }"
            />
          </div>
          <div class="wide">
            <label for="request-wishes">Пожелания</label
            ><n-input
              v-model:value="fields.wishes"
              type="textarea"
              :input-props="{ id: 'request-wishes' }"
            />
          </div>
        </div>
        <div class="actions">
          <n-button type="primary" attr-type="submit" :loading="busy">{{
            item ? 'Сохранить изменения' : 'Создать заявку'
          }}</n-button
          ><n-button v-if="item" @click="editing = false">Отмена</n-button>
        </div>
      </form>
    </n-card>
    <n-card v-if="item" title="История изменений" class="block">
      <n-alert v-if="historyError" type="error"
        >{{ historyError }} <n-button @click="loadHistory">Повторить</n-button></n-alert
      >
      <template v-else-if="history">
        <ul v-if="history.items.length" class="history">
          <li v-for="event in history.items" :key="event.id">
            <strong>{{ historyLabels[event.action] ?? event.action }}</strong
            ><span
              >{{ formatDateTime(event.created_at) }} ·
              {{ event.actor?.full_name ?? 'Система' }}</span
            >
          </li>
        </ul>
        <p v-else>Изменений пока нет.</p>
        <n-pagination
          v-if="history.total > history.page_size"
          v-model:page="historyPage"
          :item-count="history.total"
          :page-size="history.page_size"
        />
      </template>
      <n-spin v-else description="Загружаем историю…" />
    </n-card>
  </template>
</template>

<style scoped>
.back {
  display: inline-block;
  margin-bottom: var(--space-3);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 210px), 1fr));
  gap: var(--space-4);
}
.block {
  margin-top: var(--space-4);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.wide {
  grid-column: 1 / -1;
}
label,
dt {
  display: block;
  margin-bottom: 4px;
  color: var(--c-text-muted);
}
dd {
  margin: 0;
  font-weight: 500;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
input[type='date'] {
  width: 100%;
  min-height: 34px;
  padding-inline: 8px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  font: inherit;
}
.select {
  width: min(320px, 100%);
}
.history {
  list-style: none;
  padding: 0;
  margin: 0 0 var(--space-3);
}
.history li {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-2);
  padding-block: var(--space-2);
  border-bottom: 1px solid var(--c-border);
}
.history span {
  color: var(--c-text-muted);
}
</style>
