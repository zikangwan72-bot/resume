import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    permission?: string
    public?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { title: '登录', public: true } },
    { path: '/assets/mobile-inventory', component: () => import('@/views/MobileInventoryView.vue'), meta: { title: '员工自助盘点', public: true } },
    { path: '/recruitment/student', component: () => import('@/views/recruitment/RecruitmentStudentView.vue'), meta: { title: '候选人投递端', public: true } },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: '/dashboard' },
        { path: 'dashboard', component: () => import('@/views/WorkbenchView.vue'), meta: { title: '工作台', permission: 'dashboard:view' } },
        { path: 'modules/resume-screening', component: () => import('@/views/ResumeScreeningView.vue'), meta: { title: 'AI简历筛选', permission: 'resume:view' } },
        { path: 'recruitment/admin', component: () => import('@/views/recruitment/RecruitmentAdminView.vue'), meta: { title: '招聘管理端', permission: 'recruitment:manage' } },
        { path: 'screening/jobs', component: () => import('@/views/screening/ScreeningJobsView.vue'), meta: { title: '岗位标准', permission: 'resume:manage' } },
        { path: 'screening/results/:id', component: () => import('@/views/screening/ScreeningResultView.vue'), meta: { title: '筛选结果', permission: 'resume:view' } },
        { path: 'modules/approval-center', component: () => import('@/views/approval/ApprovalHome.vue'), meta: { title: '审批中心', permission: 'approval:view' } },
        { path: 'modules/approval-center/requests', component: () => import('@/views/approval/ApprovalMyRequests.vue'), meta: { title: '我的申请', permission: 'approval:view' } },
        { path: 'modules/approval-center/new', component: () => import('@/views/approval/ApprovalNew.vue'), meta: { title: '发起申请', permission: 'approval:view' } },
        { path: 'modules/approval-center/pending', component: () => import('@/views/approval/ApprovalPending.vue'), meta: { title: '待我审批', permission: 'approval:view' } },
        { path: 'modules/approval-center/handled', component: () => import('@/views/approval/ApprovalHandled.vue'), meta: { title: '我已审批', permission: 'approval:view' } },
        { path: 'modules/approval-center/:id', component: () => import('@/views/approval/ApprovalDetail.vue'), meta: { title: '审批详情', permission: 'approval:view' } },
        { path: 'modules/asset-management', component: () => import('@/views/AssetManagementView.vue'), meta: { title: '全资产管理', permission: 'asset:view' } },
        { path: 'modules/service-desk', component: () => import('@/views/ServiceDeskView.vue'), meta: { title: '企业IT服务台', permission: 'service_desk:view' } },
        { path: 'modules/:moduleKey', component: () => import('@/views/ModuleView.vue'), meta: { title: '业务模块' } },
        { path: 'admin/process-apps', component: () => import('@/views/approval/AdminProcessApps.vue'), meta: { title: '流程应用', permission: 'approval:manage' } },
        { path: 'admin/process-apps/new', component: () => import('@/views/approval/AdminProcessEditor.vue'), meta: { title: '新建流程应用', permission: 'approval:manage' } },
        { path: 'admin/process-apps/:id/edit', component: () => import('@/views/approval/AdminProcessEditor.vue'), meta: { title: '编辑流程应用', permission: 'approval:manage' } },
        { path: 'admin/users', component: () => import('@/views/approval/AdminUsers.vue'), meta: { title: '员工与审批角色', permission: 'approval:manage' } },
        { path: 'admin/process-monitor', component: () => import('@/views/approval/AdminProcessMonitor.vue'), meta: { title: '流程监控', permission: 'approval:manage' } },
        { path: 'ai-runs', component: () => import('@/views/AIRunsView.vue'), meta: { title: 'AI运行记录', permission: 'ai_run:view' } },
        { path: 'notifications', component: () => import('@/views/NotificationsView.vue'), meta: { title: '通知中心', permission: 'notification:view' } },
        { path: 'audit-logs', component: () => import('@/views/AuditLogsView.vue'), meta: { title: '审计日志', permission: 'audit:view' } },
        { path: 'profile', component: () => import('@/views/ProfileView.vue'), meta: { title: '个人资料' } },
      ],
    },
    { path: '/:pathMatch(.*)*', component: () => import('@/views/NotFoundView.vue'), meta: { title: '页面不存在' } },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path === '/login' && auth.isAuthenticated) return '/dashboard'
  if (!to.meta.public && !auth.isAuthenticated) {
    localStorage.setItem('enterprise_ai_post_login_redirect', to.fullPath)
    return '/login'
  }
  if (to.meta.permission && !auth.can(to.meta.permission)) return '/dashboard'
  document.title = `${to.meta.title || '企业AI平台'} · Enterprise AI Suite`
})

export default router
