<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ApartmentOutlined,
  AuditOutlined,
  BellOutlined,
  BlockOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ProfileOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const collapsed = ref(window.innerWidth < 900)
const isMobile = ref(window.innerWidth < 992)
const mobileMenuOpen = ref(false)

const roleLabel: Record<string, string> = {
  platform_admin: '平台管理员',
  product_demo_user: '产品演示用户',
  auditor: '审计查看者',
}

const menuItems = computed(() => {
  const modules = [
    { key: '/modules/resume-screening', icon: h(FileSearchOutlined), label: 'AI简历筛选', permission: 'resume:view' },
    { key: '/modules/approval-center', icon: h(ApartmentOutlined), label: '流程审批中心', permission: 'approval:view' },
    { key: '/modules/asset-management', icon: h(DatabaseOutlined), label: '全资产管理', permission: 'asset:view' },
    { key: '/modules/service-desk', icon: h(RobotOutlined), label: '企业IT服务台', permission: 'service_desk:view' },
  ]
    .filter((item) => auth.can(item.permission))
    .map(({ permission: _, ...item }) => item)

  const governance = [
    { key: '/notifications', icon: h(BellOutlined), label: '通知中心', permission: 'notification:view' },
    { key: '/ai-runs', icon: h(SafetyCertificateOutlined), label: 'AI运行记录', permission: 'ai_run:view' },
    { key: '/audit-logs', icon: h(AuditOutlined), label: '审计日志', permission: 'audit:view' },
  ]
    .filter((item) => auth.can(item.permission))
    .map(({ permission: _, ...item }) => item)

  const admin = [
    { key: '/admin/users', icon: h(UserOutlined), label: '员工与角色', permission: 'approval:manage' },
    { key: '/admin/process-apps', icon: h(SettingOutlined), label: '流程应用', permission: 'approval:manage' },
  ]
    .filter((item) => auth.can(item.permission))
    .map(({ permission: _, ...item }) => item)

  return [
    { key: '/dashboard', icon: h(BlockOutlined), label: '工作台' },
    ...(modules.length ? [{ type: 'group', label: '业务模块', children: modules }] : []),
    ...(admin.length ? [{ type: 'group', label: '后台管理', children: admin }] : []),
    ...(governance.length ? [{ type: 'group', label: '平台治理', children: governance }] : []),
  ]
})

function selectMenu({ key }: { key: string }) {
  router.push(key)
  if (isMobile.value) mobileMenuOpen.value = false
}

function handleBreakpoint(broken: boolean) {
  isMobile.value = broken
  collapsed.value = broken
  if (!broken) mobileMenuOpen.value = false
}

function handleResize() {
  const mobile = window.innerWidth < 992
  if (mobile) collapsed.value = true
  isMobile.value = mobile
  if (!mobile) mobileMenuOpen.value = false
}

function handleAccount({ key }: { key: string }) {
  if (key === 'profile') router.push('/profile')
  if (key === 'logout') {
    auth.logout()
    router.push('/login')
  }
}

onMounted(() => {
  auth.refreshMe().catch(() => undefined)
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => window.removeEventListener('resize', handleResize))
</script>

<template>
  <a-layout class="app-shell">
    <a-layout-sider
      v-if="!isMobile"
      v-model:collapsed="collapsed"
      :collapsed-width="isMobile ? 0 : 72"
      :width="248"
      :trigger="null"
      class="app-sider"
      :class="{ 'mobile-sider': isMobile }"
      breakpoint="lg"
      @breakpoint="handleBreakpoint"
    >
      <div class="brand" :class="{ compact: collapsed }">
        <div class="brand-mark">EA</div>
        <div v-if="!collapsed" class="brand-copy">
          <strong>Enterprise AI</strong>
          <span>Workflow Suite</span>
        </div>
      </div>
      <a-menu
        mode="inline"
        theme="dark"
        :selected-keys="[route.path]"
        :items="menuItems"
        class="app-menu"
        @click="selectMenu"
      />
      <div v-if="!collapsed" class="sider-foot">
        <span class="status-dot"></span>
        Foundation v0.1
      </div>
    </a-layout-sider>

    <a-drawer v-model:open="mobileMenuOpen" placement="left" :width="248" :mask-closable="true" @close="mobileMenuOpen = false" class="mobile-nav-drawer">
      <div class="brand">
        <div class="brand-mark">EA</div>
        <div class="brand-copy"><strong>Enterprise AI</strong><span>Workflow Suite</span></div>
      </div>
      <a-menu mode="inline" theme="dark" :selected-keys="[route.path]" :items="menuItems" class="app-menu" @click="selectMenu" />
    </a-drawer>

    <a-layout>
      <a-layout-header class="app-header">
        <a-button type="text" class="collapse-button" aria-label="切换导航" @click="isMobile ? (mobileMenuOpen = true) : (collapsed = !collapsed)">
          <MenuUnfoldOutlined v-if="collapsed" />
          <MenuFoldOutlined v-else />
        </a-button>
        <div class="header-context">
          <span class="context-label">当前空间</span>
          <strong>企业AI工作流平台</strong>
        </div>
        <a-dropdown>
          <button class="account-button" aria-label="账户菜单">
            <a-avatar class="account-avatar" :size="34"><UserOutlined /></a-avatar>
            <span class="account-copy">
              <strong>{{ auth.user?.display_name }}</strong>
              <small>{{ roleLabel[auth.user?.role || ''] }}</small>
            </span>
          </button>
          <template #overlay>
            <a-menu @click="handleAccount">
              <a-menu-item key="profile"><ProfileOutlined /> 个人资料</a-menu-item>
              <a-menu-divider />
              <a-menu-item key="logout">退出登录</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </a-layout-header>
      <a-layout-content class="app-content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>
