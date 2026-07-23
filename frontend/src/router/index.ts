import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    permission?: string
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: '/dashboard' },
        {
          path: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '工作台', permission: 'dashboard:view' },
        },
        // ── 审批模块路由 ──
        {
          path: 'modules/approval-center',
          component: () => import('@/views/approval/ApprovalHome.vue'),
          meta: { title: '审批中心', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/requests',
          component: () => import('@/views/approval/ApprovalMyRequests.vue'),
          meta: { title: '我的申请', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/new',
          component: () => import('@/views/approval/ApprovalNew.vue'),
          meta: { title: '发起申请', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/pending',
          component: () => import('@/views/approval/ApprovalPending.vue'),
          meta: { title: '待我审批', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/handled',
          component: () => import('@/views/approval/ApprovalHandled.vue'),
          meta: { title: '我已审批', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/:id',
          component: () => import('@/views/approval/ApprovalDetail.vue'),
          meta: { title: '审批详情', permission: 'approval:view' },
        },
        // ── 后台管理路由 ──
        {
          path: 'admin/process-apps',
          component: () => import('@/views/approval/AdminProcessApps.vue'),
          meta: { title: '流程应用', permission: 'approval:manage' },
        },
        {
          path: 'admin/process-apps/new',
          component: () => import('@/views/NotFoundView.vue'),
          meta: { title: '新建流程应用', permission: 'approval:manage' },
        },
        {
          path: 'admin/process-apps/:id/edit',
          component: () => import('@/views/NotFoundView.vue'),
          meta: { title: '编辑流程应用', permission: 'approval:manage' },
        },
        {
          path: 'admin/users',
          component: () => import('@/views/approval/AdminUsers.vue'),
          meta: { title: '员工与审批角色', permission: 'approval:manage' },
        },
        {
          path: 'modules/:moduleKey',
          component: () => import('@/views/ModuleView.vue'),
          meta: { title: '业务模块' },
        },
        {
          path: 'notifications',
          component: () => import('@/views/NotificationsView.vue'),
          meta: { title: '通知中心', permission: 'notification:view' },
        },
        {
          path: 'ai-runs',
          component: () => import('@/views/AIRunsView.vue'),
          meta: { title: 'AI运行记录', permission: 'ai_run:view' },
        },
        {
          path: 'audit-logs',
          component: () => import('@/views/AuditLogsView.vue'),
          meta: { title: '审计日志', permission: 'audit:view' },
        },
        {
          path: 'profile',
          component: () => import('@/views/ProfileView.vue'),
          meta: { title: '个人资料' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', component: () => import('@/views/NotFoundView.vue') },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path === '/login' && auth.isAuthenticated) return '/dashboard'
  if (to.path !== '/login' && !auth.isAuthenticated) return '/login'
  if (to.meta.permission && !auth.can(to.meta.permission)) return '/dashboard'
  document.title = `${to.meta.title || '企业AI平台'} · Enterprise AI Suite`
})

export default router
