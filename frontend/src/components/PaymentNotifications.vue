<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { NAlert, NButton, NCard, NPagination, NSpin } from 'naive-ui'
import { useHttp } from '@/api/instance'
import type { Dto } from '@/api/workflow'
import { formatDateTime } from '@/utils/format'
const http = useHttp()
const data = ref<Dto['NotificationPage']>()
const page = ref(1)
const error = ref('')
const loading = ref(false)
const pendingIds = ref(new Set<string>())
let alive = true
let sequence = 0
async function load(next = page.value) {
  const current = ++sequence
  loading.value = true
  error.value = ''
  page.value = next
  try {
    const result = await http.get<Dto['NotificationPage']>('/notifications?page=' + next)
    if (alive && current === sequence) data.value = result
  } catch (cause) {
    if (alive && current === sequence)
      error.value = cause instanceof Error ? cause.message : 'Не удалось загрузить уведомления.'
  } finally {
    if (alive && current === sequence) loading.value = false
  }
}
async function read(id: string) {
  if (pendingIds.value.has(id)) return
  pendingIds.value.add(id)
  try {
    await http.post('/notifications/' + id + '/read')
    await load()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Не удалось отметить уведомление.'
  } finally {
    pendingIds.value.delete(id)
  }
}
const poll = () => {
  if (!document.hidden && !loading.value) void load()
}
let timer: ReturnType<typeof setInterval>
onMounted(() => {
  void load()
  timer = setInterval(poll, 15000)
  document.addEventListener('visibilitychange', poll)
})
onUnmounted(() => {
  alive = false
  clearInterval(timer)
  document.removeEventListener('visibilitychange', poll)
})
</script>
<template>
  <n-card title="Уведомления">
    <p>Непрочитано: {{ data?.unread_count ?? 0 }}</p>
    <n-alert v-if="error" type="error"
      >{{ error }} <n-button size="small" @click="load()">Повторить</n-button></n-alert
    >
    <n-spin :show="loading">
      <p v-if="!loading && !data?.items.length && !error">Уведомлений пока нет.</p>
      <article v-for="notice in data?.items" :key="notice.id">
        <div>
          <strong>Получена оплата {{ notice.amount }} ₽</strong>
          <p>{{ formatDateTime(notice.created_at) }}</p>
        </div>
        <RouterLink
          v-if="notice.can_open_request && notice.request_id"
          :to="{ name: 'request-detail', params: { id: notice.request_id } }"
          >Открыть заявку</RouterLink
        >
        <n-button
          v-if="!notice.read_at"
          size="small"
          :loading="pendingIds.has(notice.id)"
          @click="read(notice.id)"
          >Отметить прочитанным</n-button
        >
      </article>
      <n-pagination
        v-if="data && data.total > data.page_size"
        :page="page"
        :page-size="data.page_size"
        :item-count="data.total"
        @update:page="load"
      />
    </n-spin>
  </n-card>
</template>
<style scoped>
article {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  border-top: 1px solid var(--c-border);
  padding-block: 10px;
}
article p {
  margin: 4px 0 0;
  color: var(--c-text-muted);
}
</style>
