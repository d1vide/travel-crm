<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NAlert, NButton, NCard, NDescriptions, NDescriptionsItem, NSpin } from 'naive-ui'
import { ApiError } from '@/api/errors'
import { useProfileApi, type Profile } from '@/api/profile'
import { ROLE_LABELS } from '@/auth/roles'
import PageHeader from '@/components/PageHeader.vue'

const api = useProfileApi()
const profile = ref<Profile | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    profile.value = await api.get()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Не удалось загрузить профиль'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <PageHeader title="Мой профиль" description="Основная информация о вас в системе" />

  <n-spin v-if="loading && !profile" class="spin" />

  <n-alert v-else-if="error" type="error" :show-icon="false" class="card">
    {{ error }}
    <n-button size="tiny" @click="load">Повторить</n-button>
  </n-alert>

  <n-card v-else-if="profile" class="card">
    <n-descriptions :column="2" label-placement="top" label-style="color: #64748b">
      <n-descriptions-item label="ФИО" :span="2">
        <strong>{{ profile.fullName }}</strong>
      </n-descriptions-item>
      <n-descriptions-item label="Роль">{{ ROLE_LABELS[profile.role] }}</n-descriptions-item>
      <n-descriptions-item label="Отдел">
        <template v-if="profile.department">{{ profile.department }}</template>
        <span v-else data-test="profile-empty">—</span>
      </n-descriptions-item>
      <n-descriptions-item label="Должность">
        <template v-if="profile.position">{{ profile.position }}</template>
        <span v-else data-test="profile-empty">—</span>
      </n-descriptions-item>
      <n-descriptions-item label="Рабочий телефон">
        <span v-if="profile.workPhone" class="tabular">{{ profile.workPhone }}</span>
        <span v-else data-test="profile-empty">—</span>
      </n-descriptions-item>
      <n-descriptions-item label="Email">
        <template v-if="profile.email">{{ profile.email }}</template>
        <span v-else data-test="profile-empty">—</span>
      </n-descriptions-item>
    </n-descriptions>
  </n-card>
</template>

<style scoped>
.spin {
  display: block;
  margin: 64px auto;
}

.card {
  max-width: 720px;
}
</style>
