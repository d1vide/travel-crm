<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { NIcon, NInput } from 'naive-ui'
import { SearchOutline } from '@/theme/icons'

const props = withDefaults(
  defineProps<{ modelValue: string; placeholder?: string; delay?: number }>(),
  { placeholder: 'Поиск', delay: 300 },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const text = ref(props.modelValue)
let timer: ReturnType<typeof setTimeout> | undefined

watch(
  () => props.modelValue,
  (value) => {
    if (value !== text.value.trim()) text.value = value
  },
)

function onInput(value: string) {
  text.value = value
  clearTimeout(timer)
  timer = setTimeout(() => emit('update:modelValue', value.trim()), props.delay)
}

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <n-input :value="text" :placeholder="placeholder" clearable @update:value="onInput">
    <template #prefix><n-icon :component="SearchOutline" /></template>
  </n-input>
</template>
