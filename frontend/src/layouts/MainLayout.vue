<script setup lang="ts">
import { computed, h, type Component } from 'vue'
import {
  NAvatar,
  NButton,
  NIcon,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  NTag,
  type MenuOption,
} from 'naive-ui'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { groupedNavigationFor } from '@/auth/navigation'
import { ROLE_LABELS } from '@/auth/roles'
import { useSessionStore } from '@/stores/session'
import {
  AirplaneOutline,
  BarChartOutline,
  CompassOutline,
  DocumentTextOutline,
  LogOutOutline,
  PeopleOutline,
  SpeedometerOutline,
  WalletOutline,
} from '@/theme/icons'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const icons: Record<string, Component> = {
  requests: DocumentTextOutline,
  clients: PeopleOutline,
  tours: AirplaneOutline,
  payments: WalletOutline,
  workspace: SpeedometerOutline,
  reports: BarChartOutline,
}

function renderIcon(icon: Component) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions = computed<MenuOption[]>(() =>
  session.role
    ? groupedNavigationFor(session.role).map((section) => ({
        type: 'group',
        key: section.group,
        label: section.label,
        children: section.items.map((item) => ({
          key: item.name,
          icon: icons[item.name] ? renderIcon(icons[item.name]!) : undefined,
          label: () => h(RouterLink, { to: item.path }, { default: () => item.label }),
        })),
      }))
    : [],
)

// Вложенные страницы раздела (карточка, форма) подсвечивают свой пункт меню.
const activeKey = computed(() => {
  if (route.meta.section) return route.meta.section
  return typeof route.name === 'string' ? route.name : null
})

const initials = computed(() =>
  (session.user?.fullName ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join(''),
)

async function logout() {
  await session.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <n-layout class="layout" has-sider position="absolute">
    <n-layout-sider bordered :width="240" content-style="padding: 0 8px 16px;">
      <div class="brand">
        <span class="brand__logo"><n-icon :component="CompassOutline" :size="20" /></span>
        <span>
          <span class="brand__name">Travel CRM</span>
          <span class="brand__caption">Рабочая область</span>
        </span>
      </div>
      <n-menu :options="menuOptions" :value="activeKey" :indent="12" />
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered class="header">
        <div class="user">
          <n-avatar round :size="28" class="user__avatar">{{ initials }}</n-avatar>
          <span v-if="session.user" class="user__name">{{ session.user.fullName }}</span>
          <n-tag v-if="session.role" size="small" :bordered="false">
            {{ ROLE_LABELS[session.role] }}
          </n-tag>
          <n-button quaternary size="small" @click="logout">
            <template #icon><n-icon :component="LogOutOutline" /></template>
            Выйти
          </n-button>
        </div>
      </n-layout-header>
      <n-layout-content content-style="padding: 24px;" class="content">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 12px;
}

.brand__logo {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  color: #fff;
  background: var(--c-primary);
}

.brand__name {
  display: block;
  font-size: 15px;
  font-weight: 600;
  line-height: 18px;
}

.brand__caption {
  display: block;
  font-size: 12px;
  line-height: 16px;
  color: var(--c-text-muted);
}

.header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  height: 56px;
  padding: 0 24px;
}

.user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user__avatar {
  color: #fff;
  background: var(--c-primary);
  font-size: 12px;
}

.user__name {
  font-weight: 500;
}

.content {
  background: var(--c-surface-app);
}
</style>
