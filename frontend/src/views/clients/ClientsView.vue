<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NDataTable, NEmpty, NIcon, type DataTableColumns } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useClientsApi, type Client } from '@/api/clients'
import { ApiError } from '@/api/errors'
import PageHeader from '@/components/PageHeader.vue'
import SearchInput from '@/components/SearchInput.vue'
import { formatDate } from '@/utils/format'
import { PersonAddOutline } from '@/theme/icons'

const PAGE_SIZE = 20

const api = useClientsApi()
const router = useRouter()

const query = ref('')
const page = ref(1)
const items = ref<Client[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

// Ответы приходят в произвольном порядке: применяем только результат последнего запроса.
let requestId = 0

async function load() {
  const current = ++requestId
  loading.value = true
  error.value = null
  try {
    const result = await api.list({ q: query.value, page: page.value, pageSize: PAGE_SIZE })
    if (current !== requestId) return
    items.value = result.items
    total.value = result.total
  } catch (e) {
    if (current !== requestId) return
    error.value = e instanceof ApiError ? e.message : 'Не удалось загрузить клиентов'
  } finally {
    if (current === requestId) loading.value = false
  }
}

onMounted(load)

watch(query, () => {
  page.value = 1
  void load()
})

function changePage(next: number) {
  page.value = next
  void load()
}

const dash = (value: string | null) => value || '—'

const columns: DataTableColumns<Client> = [
  {
    title: '№',
    key: 'client_number',
    width: 80,
    render: (row) => h('span', { class: 'tabular muted' }, `№${row.client_number}`),
  },
  {
    title: 'Клиент',
    key: 'full_name',
    render: (row) => h('span', { class: 'name' }, row.full_name),
  },
  {
    title: 'Телефон',
    key: 'phone',
    render: (row) => h('span', { class: 'tabular' }, dash(row.phone)),
  },
  { title: 'Email', key: 'email', render: (row) => dash(row.email) },
  {
    title: 'Создан',
    key: 'created_at',
    width: 120,
    render: (row) => h('span', { class: 'tabular muted' }, formatDate(row.created_at)),
  },
]

const pagination = computed(() =>
  total.value > PAGE_SIZE
    ? {
        page: page.value,
        pageSize: PAGE_SIZE,
        itemCount: total.value,
        onUpdatePage: changePage,
      }
    : false,
)

const rowProps = (row: Client) => ({
  style: 'cursor: pointer',
  onClick: () => void router.push(`/clients/${row.id}`),
})
</script>

<template>
  <PageHeader title="Клиенты" description="Карточки клиентов, контакты и предпочтения">
    <template #actions>
      <n-button type="primary" @click="router.push('/clients/new')">
        <template #icon><n-icon :component="PersonAddOutline" /></template>
        Новый клиент
      </n-button>
    </template>
  </PageHeader>

  <n-card content-style="padding: 0;" class="card">
    <div class="toolbar">
      <SearchInput
        v-model="query"
        placeholder="Поиск по имени, телефону или email"
        class="search"
      />
    </div>
    <n-alert v-if="error" type="error" :show-icon="false" class="error">
      {{ error }}
      <n-button size="tiny" class="retry" @click="load">Повторить</n-button>
    </n-alert>
    <n-data-table
      remote
      :columns="columns"
      :data="items"
      :loading="loading"
      :pagination="pagination"
      :row-key="(row: Client) => row.id"
      :row-props="rowProps"
      :bordered="false"
    >
      <template #empty>
        <n-empty :description="query ? 'Ничего не найдено' : 'Клиентов пока нет'" />
      </template>
    </n-data-table>
  </n-card>
</template>

<style scoped>
.toolbar {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--c-border);
}

.search {
  max-width: 360px;
}

.error {
  margin: var(--space-3) var(--space-4);
}

.retry {
  margin-left: var(--space-2);
}

.name {
  font-weight: 500;
}

.muted {
  color: var(--c-text-muted);
}
</style>
