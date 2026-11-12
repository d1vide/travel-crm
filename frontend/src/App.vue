<script setup lang="ts">
import { NConfigProvider, dateRuRU, ruRU } from 'naive-ui'
import { RouterView } from 'vue-router'
</script>

<template>
  <n-config-provider :locale="ruRU" :date-locale="dateRuRU">
    <router-view />
  </n-config-provider>
</template>
