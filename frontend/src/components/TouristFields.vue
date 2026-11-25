<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NCard, NInput, NSelect } from 'naive-ui'
import type { Dto } from '@/api/workflow'
const rows = defineModel<Dto['TouristSubmissionItem'][]>({ required: true })
const props = defineProps<{ busy: boolean; readonly?: boolean; errors?: Record<string, string> }>()
const emit = defineEmits<{ save: [] }>()
const localErrors = ref<Record<string, string>>({})
const errorFor = (index: number, field: string) =>
  localErrors.value[`tourists.${index}.${field}`] ?? props.errors?.[`tourists.${index}.${field}`]

function submit() {
  if (props.readonly || props.busy) return
  const errors: Record<string, string> = {}
  const today = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Europe/Moscow',
    dateStyle: 'short',
  }).format(new Date())
  rows.value.forEach((row, index) => {
    const prefix = `tourists.${index}.`
    if (!row.full_name.trim()) errors[prefix + 'full_name'] = 'Укажите ФИО.'
    if (!row.birth_date || row.birth_date > today)
      errors[prefix + 'birth_date'] = 'Укажите дату рождения, которая уже наступила.'
    if (!row.document_number.trim()) errors[prefix + 'document_number'] = 'Укажите номер документа.'
    if (row.document_type === 'international_passport' && !row.document_expires_on) {
      errors[prefix + 'document_expires_on'] = 'Укажите срок действия загранпаспорта.'
    }
  })
  localErrors.value = errors
  if (!Object.keys(errors).length) emit('save')
}
const types = [
  { label: 'Паспорт', value: 'passport' },
  { label: 'Загранпаспорт', value: 'international_passport' },
]
</script>
<template>
  <form class="tourist-form" novalidate @submit.prevent="submit">
    <n-card v-for="(row, index) in rows" :key="index" :title="'Турист ' + (index + 1)" size="small">
      <div class="fields">
        <label
          >ФИО<n-input
            v-model:value="row.full_name"
            :readonly="readonly"
            :status="errorFor(index, 'full_name') ? 'error' : undefined"
          />
          <small v-if="errorFor(index, 'full_name')" role="alert">{{
            errorFor(index, 'full_name')
          }}</small>
        </label>
        <label
          >Дата рождения<input v-model="row.birth_date" :readonly="readonly" type="date" />
          <small v-if="errorFor(index, 'birth_date')" role="alert">{{
            errorFor(index, 'birth_date')
          }}</small>
        </label>
        <label
          >Документ<n-select
            v-model:value="row.document_type"
            :disabled="readonly"
            :options="types"
        /></label>
        <label
          >Номер документа<n-input
            v-model:value="row.document_number"
            :readonly="readonly"
            :status="errorFor(index, 'document_number') ? 'error' : undefined"
          />
          <small v-if="errorFor(index, 'document_number')" role="alert">{{
            errorFor(index, 'document_number')
          }}</small>
        </label>
        <label v-if="row.document_type === 'international_passport'"
          >Действителен до<input
            v-model="row.document_expires_on"
            :readonly="readonly"
            type="date"
          />
          <small v-if="errorFor(index, 'document_expires_on')" role="alert">{{
            errorFor(index, 'document_expires_on')
          }}</small>
        </label>
      </div>
    </n-card>
    <n-button
      v-if="!readonly"
      type="primary"
      attr-type="submit"
      :loading="busy"
      :disabled="!rows.length"
      >Сохранить данные</n-button
    >
  </form>
</template>
<style scoped>
.tourist-form {
  display: grid;
  gap: 12px;
  justify-items: start;
}
.tourist-form > :first-child,
.tourist-form > .n-card {
  width: 100%;
}
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr));
  gap: 12px;
}
label {
  display: grid;
  gap: 4px;
}
small {
  color: #b42318;
}
input[type='date'] {
  min-height: 34px;
  width: 100%;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  padding-inline: 8px;
  font: inherit;
}
</style>
