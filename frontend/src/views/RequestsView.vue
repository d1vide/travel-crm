<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NDataTable, NEmpty, NSelect, NTag, type DataTableColumns } from 'naive-ui'
import { useRequestsApi, type RequestStatus, type TravelRequest } from '@/api/requests'
import PageHeader from '@/components/PageHeader.vue'
import { useSessionStore } from '@/stores/session'

const api = useRequestsApi()
const session = useSessionStore()
const statusLabels: Record<RequestStatus, string> = {
  new: 'Новая',
  in_progress: 'В работе',
  offer_prepared: 'Предложение готово',
  booked: 'Забронирована',
  completed: 'Завершена',
  cancelled: 'Отменена',
}
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

watch([status, managerId], () => {
  page.value = 1
  void load()
}, { immediate: true })
if (session.role === 'head') void loadManagers()

const pagination = computed(() => total.value > pageSize && {
  page: page.value,
  pageSize,
  itemCount: total.value,
  onUpdatePage(next: number) {
    page.value = next
    void load()
  },
})

const columns: DataTableColumns<TravelRequest> = [
  { title: 'Клиент', key: 'client', render: (row) => row.client.full_name },
  { title: 'Направление', key: 'destination' },
  { title: 'Ответственный', key: 'manager', render: (row) => row.manager.full_name },
  {
    title: 'Статус',
    key: 'status',
    render: (row) => h(NTag, { size: 'small', bordered: false }, {
      default: () => statusLabels[row.status],
    }),
  },
]
</script>

<template>
  <PageHeader title="Заявки" />
  <n-card content-style="padding: 0">
    <div class="filters">
      <n-select v-model:value="status" :options="statuses" clearable placeholder="Все статусы" aria-label="Статус заявки" />
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
        <n-empty :description="status || managerId ? 'По этим фильтрам заявок нет' : 'Заявок пока нет'" />
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
</style>
