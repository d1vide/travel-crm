<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NDescriptions,
  NDescriptionsItem,
  NResult,
  NSpin,
  useMessage,
} from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { useClientsApi, type Client } from '@/api/clients'
import { ApiError } from '@/api/errors'
import ClientForm from '@/components/clients/ClientForm.vue'
import PageHeader from '@/components/PageHeader.vue'
import { formatDate, formatDateTime } from '@/utils/format'

const api = useClientsApi()
const route = useRoute()
const router = useRouter()
const message = useMessage()

const client = ref<Client | null>(null)
const loading = ref(true)
const notFound = ref(false)
const error = ref<string | null>(null)
const editing = ref(false)
const formKey = ref(0)
const conflictNotice = ref(false)

const id = computed(() => String(route.params.id))
const canUpdate = computed(() => client.value?.allowed_actions.includes('update') ?? false)

async function load() {
  loading.value = true
  error.value = null
  try {
    client.value = await api.get(id.value)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound.value = true
    else error.value = e instanceof ApiError ? e.message : 'Не удалось загрузить карточку'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function startEditing() {
  conflictNotice.value = false
  editing.value = true
}

function onSaved(saved: Client) {
  client.value = saved
  editing.value = false
  message.success('Изменения сохранены')
}

// Карточку изменил другой сотрудник: показываем актуальную версию и форму с её данными.
async function onConflict() {
  await load()
  formKey.value += 1
  conflictNotice.value = true
}

const dash = (value: string | null | undefined) => value || '—'
</script>

<template>
  <n-spin v-if="loading && !client" class="spin" />

  <n-result
    v-else-if="notFound"
    status="404"
    title="Клиент не найден"
    description="Карточка не существует или недоступна вам"
  >
    <template #footer>
      <n-button @click="router.push('/clients')">К списку клиентов</n-button>
    </template>
  </n-result>

  <n-alert v-else-if="error" type="error" :show-icon="false">
    {{ error }}
    <n-button size="tiny" @click="load">Повторить</n-button>
  </n-alert>

  <template v-else-if="client">
    <PageHeader
      :title="client.full_name"
      :description="`№${client.client_number} · создан ${formatDate(client.created_at)}`"
    >
      <template #actions>
        <n-button
          v-if="client.allowed_actions.includes('create_request')"
          @click="router.push({ name: 'request-new', query: { client: client.id } })"
        >
          Создать заявку
        </n-button>
        <n-button quaternary @click="router.push('/clients')">К списку</n-button>
        <n-button v-if="canUpdate && !editing" type="primary" @click="startEditing">
          Изменить
        </n-button>
      </template>
    </PageHeader>

    <n-alert v-if="conflictNotice" type="warning" :show-icon="false" class="notice">
      Карточку изменил другой сотрудник. Данные обновлены: проверьте их и внесите изменения заново.
    </n-alert>

    <n-card v-if="editing" class="card" title="Редактирование">
      <ClientForm
        :key="formKey"
        :client="client"
        @saved="onSaved"
        @cancel="editing = false"
        @conflict="onConflict"
      />
    </n-card>

    <n-card v-else class="card" title="Контакты и предпочтения">
      <n-descriptions :column="2" label-placement="top" label-style="color: #64748b">
        <n-descriptions-item label="Телефон">
          <span class="tabular">{{ dash(client.phone) }}</span>
        </n-descriptions-item>
        <n-descriptions-item label="Email">{{ dash(client.email) }}</n-descriptions-item>
        <n-descriptions-item label="Предпочтения" :span="2">
          {{ dash(client.preferences) }}
        </n-descriptions-item>
        <n-descriptions-item label="Примечание" :span="2">
          {{ dash(client.note) }}
        </n-descriptions-item>
        <n-descriptions-item label="Обновлён">
          <span class="tabular">{{ formatDateTime(client.updated_at) }}</span>
        </n-descriptions-item>
      </n-descriptions>
    </n-card>
  </template>
</template>

<style scoped>
.spin {
  display: block;
  margin: 64px auto;
}

.card {
  max-width: 720px;
}

.notice {
  max-width: 720px;
  margin-bottom: var(--space-3);
}
</style>
