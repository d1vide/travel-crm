<script setup lang="ts">
import { NCard, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import type { Client } from '@/api/clients'
import ClientForm from '@/components/clients/ClientForm.vue'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()
const message = useMessage()

function onSaved(client: Client) {
  message.success('Клиент создан')
  void router.push(`/clients/${client.id}`)
}
</script>

<template>
  <PageHeader title="Новый клиент" description="Перед сохранением контакты проверяются на дубли" />
  <n-card class="card">
    <ClientForm @saved="onSaved" @cancel="router.push('/clients')" />
  </n-card>
</template>

<style scoped>
.card {
  max-width: 720px;
}
</style>
