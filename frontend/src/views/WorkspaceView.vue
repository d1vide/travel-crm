<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NCard, NModal, NSpace } from 'naive-ui'
import type { TravelRequest } from '@/api/requests'
import CommunicationLog from '@/components/CommunicationLog.vue'
import PageHeader from '@/components/PageHeader.vue'
import RequestsView from './RequestsView.vue'
import PaymentsView from './PaymentsView.vue'

const tab = ref<'requests' | 'payments'>('requests')
const contact = ref<TravelRequest>()
const showContact = ref(false)

function openContact(request: TravelRequest) {
  contact.value = request
  showContact.value = true
}
</script>
<template>
  <PageHeader
    title="Рабочее место руководителя"
    description="Заявки команды, взаимодействие с клиентами и расчёты"
  />
  <n-space class="workspace-tabs">
    <n-button
      :type="tab === 'requests' ? 'primary' : 'default'"
      :aria-pressed="tab === 'requests'"
      @click="tab = 'requests'"
      >Заявки команды</n-button
    >
    <n-button
      :type="tab === 'payments' ? 'primary' : 'default'"
      :aria-pressed="tab === 'payments'"
      @click="tab = 'payments'"
      >Финансы</n-button
    >
    <RouterLink :to="{ name: 'reports' }">Отчёт за период</RouterLink>
  </n-space>
  <RequestsView v-if="tab === 'requests'" embedded @communication="openContact" />
  <PaymentsView v-else embedded />
  <n-modal v-model:show="showContact">
    <n-card
      v-if="contact"
      class="contact-modal"
      :title="contact.client.full_name"
      closable
      @close="showContact = false"
    >
      <CommunicationLog :key="contact.id" :client-id="contact.client_id" :request-id="contact.id" />
    </n-card>
  </n-modal>
</template>
<style scoped>
.workspace-tabs {
  margin-bottom: 16px;
  align-items: center;
}
.contact-modal {
  width: min(740px, calc(100vw - 32px));
  max-height: 85vh;
  overflow: auto;
}
</style>
