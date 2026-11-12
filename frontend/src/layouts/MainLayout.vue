<script setup lang="ts">
import { computed, h } from 'vue'
import {
  NButton,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  NSpace,
  NTag,
  type MenuOption,
} from 'naive-ui'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { navigationFor } from '@/auth/navigation'
import { ROLE_LABELS } from '@/auth/roles'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const menuOptions = computed<MenuOption[]>(() =>
  session.role
    ? navigationFor(session.role).map((item) => ({
        key: item.name,
        label: () => h(RouterLink, { to: item.path }, { default: () => item.label }),
      }))
    : [],
)

const activeKey = computed(() => (typeof route.name === 'string' ? route.name : null))

function logout() {
  // Запрос выхода на сервер (отзыв refresh-токена) подключается в задаче #11.
  session.clearSession()
  void router.push({ name: 'login' })
}
</script>

<template>
  <n-layout class="layout" has-sider position="absolute">
    <n-layout-sider bordered :width="240" content-style="padding: 8px 0;">
      <div class="layout__brand">Travel CRM</div>
      <n-menu :options="menuOptions" :value="activeKey" />
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered class="layout__header">
        <n-space align="center" justify="end">
          <span v-if="session.user">{{ session.user.fullName }}</span>
          <n-tag v-if="session.role" size="small" round>{{ ROLE_LABELS[session.role] }}</n-tag>
          <n-button size="small" @click="logout">Выйти</n-button>
        </n-space>
      </n-layout-header>
      <n-layout-content content-style="padding: 24px;">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
.layout__brand {
  padding: 16px 24px;
  font-size: 18px;
  font-weight: 600;
}

.layout__header {
  padding: 12px 24px;
}
</style>
