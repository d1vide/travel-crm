<script setup lang="ts">
import { NButton, NResult } from 'naive-ui'
import { RouterLink } from 'vue-router'
</script>

<template>
  <n-result status="403" title="Нет доступа" description="Для вашей роли этот раздел недоступен">
    <template #footer>
      <router-link to="/" custom v-slot="{ navigate }">
        <n-button @click="navigate">На главную</n-button>
      </router-link>
    </template>
  </n-result>
</template>
