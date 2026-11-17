<script setup lang="ts">
import { NAlert, NCheckbox } from 'naive-ui'
import { RouterLink } from 'vue-router'
import type { ClientBrief } from '@/api/clients'

defineProps<{
  matches: ClientBrief[]
  headReview: boolean
  acknowledged: boolean
}>()
const emit = defineEmits<{ 'update:acknowledged': [value: boolean] }>()
</script>

<template>
  <div class="duplicates">
    <n-alert v-if="matches.length" type="warning" title="Похожие клиенты уже есть">
      <ul class="duplicates__list">
        <li v-for="match in matches" :key="match.id">
          <router-link :to="`/clients/${match.id}`">
            №{{ match.client_number }} · {{ match.full_name }}
          </router-link>
        </li>
      </ul>
      <n-checkbox
        v-if="!headReview"
        data-test="acknowledge"
        :checked="acknowledged"
        @update:checked="emit('update:acknowledged', $event)"
      >
        Это другой клиент, создать отдельную карточку
      </n-checkbox>
    </n-alert>
    <n-alert v-if="headReview" type="error" title="Контакт есть в недоступной вам карточке">
      Обратитесь к руководителю: он проверит совпадение и подтвердит создание отдельной карточки.
    </n-alert>
  </div>
</template>

<style scoped>
.duplicates {
  display: grid;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.duplicates__list {
  margin: 0 0 var(--space-2);
  padding-left: 18px;
}
</style>
