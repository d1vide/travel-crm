<script setup lang="ts">
import { NEmpty, NH1 } from 'naive-ui'

defineProps<{ title: string }>()
</script>

<template>
  <section>
    <n-h1>{{ title }}</n-h1>
    <n-empty description="Раздел в разработке" />
  </section>
</template>
