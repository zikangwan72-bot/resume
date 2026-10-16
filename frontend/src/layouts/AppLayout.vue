<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApartmentOutlined, AuditOutlined, BellOutlined, BlockOutlined, DatabaseOutlined, FileSearchOutlined, LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined, ProfileOutlined, RobotOutlined, SafetyCertificateOutlined, SettingOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const collapsed = ref(window.innerWidth < 900)
const isMobile = ref(window.innerWidth < 992)
const mobileMenuOpen = ref(false)
const openMenuKeys = ref<string[]>(['management'])
let preloadTimer: number | undefined
const roleLabel: Record<string, string> = { platform_admin: '平台管理员', recruitment_admin: '招聘管理员', asset_admin: '资产管理员', department_manager: '部门经理', approval_finance: '财务审批', employee: '员工' }

const contextTitle = computed(() => {
  if (route.path === '/dashboard') return '企业AI工作台'
  if (route.path.startsWith('/recruitment/admin')) return '招聘管理端'
  if (route.path.includes('approval-center') || route.path.startsWith('/admin/')) return '审批与流程管理'
  if (route.path.includes('asset-management')) return '全资产管理'
  if (route.path.includes('service-desk')) return '企业IT服务台'
  if (route.path.startsWith('/notifications') || route.path.startsWith('/ai-runs') || route.path.startsWith('/audit-logs')) return '平台治理'
  if (route.path.startsWith('/profile')) return '个人资料'
  return 'AI 简历筛选管理端'
})
const selectedMenuKeys = computed(() => {
  const path = route.path
  if (path.startsWith('/recruitment/admin')) return ['/recruitment/admin']
  if (path.startsWith('/modules/approval-center')) return ['/modules/approval-center']
  if (path.startsWith('/screening/')) return ['/screening/jobs']
  if (path.startsWith('/admin/process-apps')) return ['/admin/process-apps']
  return [path]
})
const menuItems = computed(() => {
  const business = [
    auth.can('resume:view') && { key: '/modules/resume-screening', icon: h(FileSearchOutlined), label: 'AI简历筛选' },
    auth.can('approval:view') && { key: '/modules/approval-center', icon: h(AuditOutlined), label: '流程审批中心' },
    auth.can('asset:view') && { key: '/modules/asset-management', icon: h(DatabaseOutlined), label: '全资产管理' },
    auth.can('service_desk:view') && { key: '/modules/service-desk', icon: h(RobotOutlined), label: '企业IT服务台' },
  ].filter(Boolean)
  const businessConfig = [
    auth.can('approval:manage') && { key: '/admin/process-apps', icon: h(ApartmentOutlined), label: '流程应用' },
    auth.can('approval:manage') && { key: '/admin/process-monitor', icon: h(AuditOutlined), label: '流程监控' },
  ].filter(Boolean)
  const organization = [
    auth.can('approval:manage') && { key: '/admin/users', icon: h(TeamOutlined), label: '员工管理' },
  ].filter(Boolean)
  const recruitment = [
    auth.can('recruitment:manage') && { key: '/recruitment/admin', icon: h(TeamOutlined), label: '招聘管理端' },
  ].filter(Boolean)
  const governance = [
    auth.can('notification:view') && { key: '/notifications', icon: h(BellOutlined), label: '通知中心' },
    auth.can('ai_run:view') && { key: '/ai-runs', icon: h(SafetyCertificateOutlined), label: 'AI运行记录' },
    auth.can('audit:view') && { key: '/audit-logs', icon: h(AuditOutlined), label: '审计日志' },
  ].filter(Boolean)
  const management = [
    ...(recruitment.length ? [{ type: 'group', label: '招聘管理', children: recruitment }] : []),
    ...(businessConfig.length ? [{ type: 'group', label: '业务配置', children: businessConfig }] : []),
    ...(organization.length ? [{ type: 'group', label: '组织管理', children: organization }] : []),
    ...(governance.length ? [{ type: 'group', label: '平台治理', children: governance }] : []),
  ]
  return [
    { key: '/dashboard', icon: h(BlockOutlined), label: '工作台' },
    ...(business.length ? [{ type: 'group', label: '业务模块', children: business }] : []),
    ...(management.length ? [{ key: 'management', icon: h(SettingOutlined), label: '管理与审核', children: management }] : []),
  ]
})

function selectMenu({ key }: { key: string }) { router.push(key); if (isMobile.value) mobileMenuOpen.value = false }
function handleResize() { const mobile = window.innerWidth < 992; isMobile.value = mobile; if (mobile) collapsed.value = true; else mobileMenuOpen.value = false }
function handleAccount({ key }: { key: string }) { if (key === 'profile') router.push('/profile'); if (key === 'logout') { auth.logout(); router.push('/login') } }

function scheduleRoutePreload() {
  const preloaders: Array<false | (() => Promise<unknown>)> = [
    auth.can('resume:view') && (() => import('@/views/ResumeScreeningView.vue')),
    auth.can('resume:manage') && (() => import('@/views/screening/ScreeningJobsView.vue')),
    auth.can('approval:view') && (() => import('@/views/approval/ApprovalHome.vue')),
    auth.can('approval:view') && (() => import('@/views/approval/ApprovalMyRequests.vue')),
    auth.can('asset:view') && (() => import('@/views/AssetManagementView.vue')),
    auth.can('approval:manage') && (() => import('@/views/approval/AdminProcessApps.vue')),
    auth.can('approval:manage') && (() => import('@/views/approval/AdminProcessMonitor.vue')),
    auth.can('approval:manage') && (() => import('@/views/approval/AdminUsers.vue')),
  ]
  const activePreloaders = preloaders.filter(Boolean) as Array<() => Promise<unknown>>

  preloadTimer = window.setTimeout(() => {
    void Promise.allSettled(activePreloaders.map((load) => load()))
  }, 600)
}

onMounted(() => {
  auth.refreshMe().catch(() => undefined)
  scheduleRoutePreload()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  if (preloadTimer !== undefined) window.clearTimeout(preloadTimer)
  window.removeEventListener('resize', handleResize)
})
</script>

<template>
  <a-layout class="app-shell">
    <a-layout-sider v-if="!isMobile" v-model:collapsed="collapsed" :collapsed-width="72" :width="248" :trigger="null" class="app-sider">
      <div class="brand" :class="{ compact: collapsed }"><div class="brand-mark">EA</div><div v-if="!collapsed" class="brand-copy"><strong>Enterprise AI</strong><span>Operations Console</span></div></div>
      <a-menu v-model:open-keys="openMenuKeys" mode="inline" theme="dark" :selected-keys="selectedMenuKeys" :items="menuItems" class="app-menu" @click="selectMenu" />
    </a-layout-sider>
    <a-drawer v-model:open="mobileMenuOpen" placement="left" :width="248" class="mobile-nav-drawer" @close="mobileMenuOpen = false">
      <div class="brand"><div class="brand-mark">EA</div><div class="brand-copy"><strong>Enterprise AI</strong><span>Operations Console</span></div></div>
      <a-menu v-model:open-keys="openMenuKeys" mode="inline" theme="dark" :selected-keys="selectedMenuKeys" :items="menuItems" class="app-menu" @click="selectMenu" />
    </a-drawer>
    <a-layout>
      <a-layout-header class="app-header">
        <a-button type="text" class="collapse-button" aria-label="切换导航" @click="isMobile ? (mobileMenuOpen = true) : (collapsed = !collapsed)"><MenuUnfoldOutlined v-if="collapsed" /><MenuFoldOutlined v-else /></a-button>
        <div class="header-context"><span class="context-label">当前空间</span><strong>{{ contextTitle }}</strong></div>
        <a-dropdown>
          <button class="account-button" aria-label="账户菜单"><a-avatar class="account-avatar" :size="34"><UserOutlined /></a-avatar><span class="account-copy"><strong>{{ auth.user?.display_name }}</strong><small>{{ roleLabel[auth.user?.role || ''] }}</small></span></button>
          <template #overlay><a-menu @click="handleAccount"><a-menu-item key="profile"><ProfileOutlined /> 个人资料</a-menu-item><a-menu-divider /><a-menu-item key="logout"><LogoutOutlined /> 退出登录</a-menu-item></a-menu></template>
        </a-dropdown>
      </a-layout-header>
      <a-layout-content class="app-content"><router-view /></a-layout-content>
    </a-layout>
  </a-layout>
</template>
