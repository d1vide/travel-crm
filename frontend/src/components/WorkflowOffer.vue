<script setup lang="ts">
import { NCard } from 'naive-ui'
import type { Dto } from '@/api/workflow'
import { formatDate } from '@/utils/format'
defineProps<{ offer: Dto['OfferSnapshot'] }>()
</script>
<template>
  <n-card size="small">
    <div class="offer-header">
      <strong>{{ offer.title }}</strong>
      <strong>{{ offer.price.replace('.', ',') }} ₽</strong>
    </div>
    <p>
      {{ offer.destination }} · {{ formatDate(offer.starts_on) }} —
      {{ formatDate(offer.ends_on) }} · Туристов: {{ offer.tourist_count }}
    </p>
    <p>{{ offer.supplier }}</p>
    <ul v-if="offer.services.length">
      <li v-for="(service, index) in offer.services" :key="index">{{ service }}</li>
    </ul>
    <slot />
  </n-card>
</template>
<style scoped>
.offer-header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
}
p {
  margin: 8px 0;
}
</style>
