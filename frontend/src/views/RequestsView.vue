<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { formatDate } from '@/utils/format'
import { requestStatuses } from '@/utils/requestStatus'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NSpin,
  NSelect,
  NTag,
  type DataTableColumns,
} from 'naive-ui'
import { useRequestsApi, type RequestStatus, type TravelRequest } from '@/api/requests'
import PageHeader from '@/components/PageHeader.vue'
import { useSessionStore } from '@/stores/session'

const props = defineProps<{ embedded?: boolean }>()
const emit = defineEmits<{ communication: [request: TravelRequest] }>()
const api = useRequestsApi()
const session = useSessionStore()
const statusLabels = requestStatuses
const statuses = Object.entries(statusLabels).map(([value, label]) => ({ value, label }))
const managers = ref<{ label: string; value: string }[]>([])
const managerError = ref(false)
const status = ref<RequestStatus | null>(null)
const managerId = ref<string | null>(null)
const page = ref(1)
const total = ref(0)
const rows = ref<TravelRequest[]>([])
const loading = ref(true)
const error = ref(false)
const pageSize = 20
const board = ref(false)
const lanes = computed(() =>
  statuses
    .filter((option) => !status.value || option.value === status.value)
    .map((option) => ({
      ...option,
      items: rows.value.filter((row) => row.status === option.value),
    })),
)
let latest = 0

async function load() {
  const sequence = ++latest
  loading.value = true
  error.value = false
  try {
    const result = await api.list({
      status: status.value ?? undefined,
      managerId: managerId.value ?? undefined,
      page: page.value,
    })
    if (sequence !== latest) return
    rows.value = result.items
    total.value = result.total
  } catch {
    if (sequence !== latest) return
    rows.value = []
    total.value = 0
    error.value = true
  } finally {
    if (sequence === latest) loading.value = false
  }
}

async function loadManagers() {
  managerError.value = false
  try {
    const first = await api.managers(1)
    const users = [...first.items]
    for (let next = 2; next <= Math.ceil(first.total / first.page_size); next++) {
      users.push(...(await api.managers(next)).items)
    }
    managers.value = users.map((user) => ({ label: user.full_name, value: user.id }))
  } catch {
    managerError.value = true
  }
}

watch(
  [status, managerId],
  () => {
    page.value = 1
    void load()
  },
  { immediate: true },
)
if (session.role === 'head') void loadManagers()

const pagination = computed(
  () =>
    total.value > pageSize && {
      page: page.value,
      pageSize,
      itemCount: total.value,
      onUpdatePage(next: number) {
        page.value = next
        void load()
      },
    },
)

const columns: DataTableColumns<TravelRequest> = [
  { title: 'Клиент', key: 'client', render: (row) => row.client.full_name },
  {
    title: 'Направление',
    key: 'destination',
    render: (row) =>
      h(
        RouterLink,
        { to: { name: 'request-detail', params: { id: row.id } } },
        () => row.destination,
      ),
  },
  {
    title: 'Поездка',
    key: 'starts_on',
    render: (row) => `${formatDate(row.starts_on)} — ${formatDate(row.ends_on)}`,
  },
  { title: 'Ответственный', key: 'manager', render: (row) => row.manager.full_name },
  {
    title: 'Статус',
    key: 'status',
    render: (row) =>
      h(
        NTag,
        { size: 'small', bordered: false },
        {
          default: () => statusLabels[row.status],
        },
      ),
  },
]
if (props.embedded) {
  columns.push({
    title: 'Общение',
    key: 'communication',
    render: (row) =>
      h(
        NButton,
        { size: 'small', onClick: () => emit('communication', row) },
        () => 'Открыть ленту',
      ),
  })
}
</script>

<template>
  <PageHeader v-if="!embedded" title="Заявки">
    <template #actions
      ><n-button :aria-pressed="board" @click="board = !board">
        {{ board ? 'Показать таблицу' : 'Показать доску' }} </n-button
      ><n-button
        type="primary"
        tag="a"
        href="/requests/new"
        @click.prevent="$router.push({ name: 'request-new' })"
        >Создать заявку</n-button
      ></template
    >
  </PageHeader>
  <n-card content-style="padding: 0">
    <div class="filters">
      <n-select
        v-model:value="status"
        :options="statuses"
        clearable
        placeholder="Все статусы"
        aria-label="Статус заявки"
      />
      <n-select
        v-if="session.role === 'head'"
        v-model:value="managerId"
        :options="managers"
        clearable
        filterable
        placeholder="Все ответственные"
        aria-label="Ответственный"
      />
    </div>
    <n-alert v-if="managerError" type="warning" class="notice">
      Не удалось загрузить ответственных.
      <n-button size="small" @click="loadManagers">Повторить</n-button>
    </n-alert>
    <n-alert v-if="error" type="error" class="notice">
      Не удалось загрузить заявки.
      <n-button size="small" @click="load">Повторить</n-button>
    </n-alert>
    <n-spin v-else-if="board" :show="loading">
      <p class="notice">На текущей странице {{ rows.length }} из {{ total }} заявок</p>
      <div class="lanes">
        <section v-for="lane in lanes" :key="lane.value" class="lane">
          <h2>{{ lane.label }}</h2>
          <ul v-if="lane.items.length">
            <li v-for="request in lane.items" :key="request.id">
              <RouterLink :to="{ name: 'request-detail', params: { id: request.id } }">
                <strong>{{ request.destination }}</strong>
                <span>{{ request.client.full_name }}</span>
              </RouterLink>
            </li>
          </ul>
          <p v-else>Нет заявок</p>
        </section>
      </div>
      <div v-if="pagination" class="notice board-pages">
        <n-button :disabled="loading || page === 1" @click="pagination.onUpdatePage(page - 1)"
          >Назад</n-button
        >
        <n-button
          :disabled="loading || page * pageSize >= total"
          @click="pagination.onUpdatePage(page + 1)"
          >Далее</n-button
        >
      </div>
    </n-spin>
    <n-data-table
      v-else
      remote
      :bordered="false"
      :columns="columns"
      :data="rows"
      :loading="loading"
      :pagination="pagination"
      :row-key="(row: TravelRequest) => row.id"
      :scroll-x="640"
    >
      <template #empty>
        <n-empty
          :description="status || managerId ? 'По этим фильтрам заявок нет' : 'Заявок пока нет'"
        />
      </template>
    </n-data-table>
  </n-card>
</template>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 240px));
  gap: var(--space-3);
  padding: var(--space-4);
  border-bottom: 1px solid var(--c-border);
}

.notice {
  margin: var(--space-4);
}
.lanes {
  display: grid;
  grid-auto-columns: minmax(175px, 1fr);
  grid-auto-flow: column;
  gap: var(--space-3);
  padding: 0 var(--space-4) var(--space-4);
  overflow-x: auto;
}
.lane {
  min-width: 0;
  padding: var(--space-3);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
}
.lane h2 {
  margin: 0;
  font-size: 14px;
}
.lane ul {
  list-style: none;
  padding: 0;
}
.lane li + li {
  margin-top: var(--space-2);
}
.lane a {
  display: grid;
  gap: 4px;
  padding: var(--space-2);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  overflow-wrap: anywhere;
}
.lane span,
.lane p {
  color: var(--c-text-muted);
}
.board-pages {
  display: flex;
  gap: var(--space-2);
}
</style>
