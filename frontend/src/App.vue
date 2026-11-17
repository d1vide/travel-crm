<script setup lang="ts">
import { NConfigProvider, NMessageProvider, dateRuRU, ruRU } from 'naive-ui'
import { RouterView } from 'vue-router'
import { themeOverrides } from '@/theme/naive'
</script>

<template>
  <n-config-provider :locale="ruRU" :date-locale="dateRuRU" :theme-overrides="themeOverrides">
    <n-message-provider>
      <router-view />
    </n-message-provider>
  </n-config-provider>
</template>
