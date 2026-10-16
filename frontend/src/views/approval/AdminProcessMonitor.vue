<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import dayjs, { type Dayjs } from 'dayjs'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/client'
import type { ApprovalRequestDetail, ApprovalRequestStatus, ApprovalUser, FormField, MonitorRequestItem, MonitorRequestPage, MonitorSummary, ProcessApp } from '@/types/approval'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const failed = ref(false)
const summaryFailed = ref(false)
const optionsFailed = ref(false)
const summary = ref<MonitorSummary | null>(null)
const requestPage = ref<MonitorRequestPage>({ items: [], total: 0, page: 1, page_size: 20 })
const processApps = ref<ProcessApp[]>([])
const users = ref<ApprovalUser[]>([])
const drawerOpen = ref(false)
const drawerLoading = ref(false)
const drawerFailed = ref(false)
const selectedItem = ref<MonitorRequestItem | null>(null)
const detail = ref<ApprovalRequestDetail | null>(null)

const filters = reactive({ processAppId: undefined as number | undefined, status: undefined as ApprovalRequestStatus | undefined, submittedRange: [] as Dayjs[], department: '', applicant: '', currentApproverId: undefined as string | undefined, overdue: undefined as boolean | undefined, page: 1 })
const overdueFilterValue = computed<string | undefined>({
  get: () => filters.overdue === undefined ? undefined : String(filters.overdue),
  set: (value) => { filters.overdue = value === undefined ? undefined : value === 'true' },
})

const metrics = computed(() => [
  { key: 'total', title: '流程总数', value: summary.value?.total ?? 0 },
  { key: 'pending', title: '审批中', value: summary.value?.pending ?? 0 },
  { key: 'approved', title: '已通过', value: summary.value?.approved ?? 0 },
  { key: 'rejected', title: '已驳回', value: summary.value?.rejected ?? 0 },
  { key: 'revoked', title: '已撤回', value: summary.value?.revoked ?? 0 },
  { key: 'overdue', title: '已超时', value: summary.value?.overdue ?? 0, danger: true },
])
const statusMeta: Record<ApprovalRequestStatus, { label: string; color: string }> = {
  pending: { label: '审批中', color: 'processing' }, revision: { label: '待修改', color: 'warning' }, approved: { label: '已通过', color: 'success' }, rejected: { label: '已驳回', color: 'error' }, revoked: { label: '已撤回', color: 'default' },
}
const detailFields = computed(() => ((detail.value?.form_schema_snapshot as { fields?: FormField[] } | null)?.fields || []))
const detailApprovers = computed(() => {
  const pending = detail.value?.nodes.find((node) => node.status === 'pending')
  if (!pending) return []
  return detail.value?.nodes.filter((node) => node.status === 'pending' && (pending.node_key ? node.node_key === pending.node_key : node.node_index === pending.node_index)) || []
})
const selectedPath = computed(() => detail.value?.flow_snapshot.filter((node) => node.type !== 'start' && node.type !== 'end') || [])

function formatDate(value: string | null | undefined) { return value ? value.slice(0, 16).replace('T', ' ') : '-' }
function approverNames(record: MonitorRequestItem) { return record.current_approvers.map((person) => person.name).join('、') || '-' }
function monitorStatus(record: MonitorRequestItem) { return statusMeta[record.status] }
function formatElapsed(record: MonitorRequestItem) {
  const start = dayjs(record.submitted_at || record.created_at)
  if (!start.isValid()) return '-'
  const minutes = Math.max(0, dayjs().diff(start, 'minute'))
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const remainingMinutes = minutes % 60
  if (days) return `${days}天 ${hours}小时`
  if (hours) return `${hours}小时 ${remainingMinutes}分钟`
  return `${remainingMinutes}分钟`
}
function formatFormValue(field: FormField) {
  const value = detail.value?.form_data[field.id || field.key]
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.map((item) => typeof item === 'object' ? Object.values(item).join(' / ') : String(item)).join('；')
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}
function readQuery() {
  const query = route.query
  filters.processAppId = query.process_app_id ? Number(query.process_app_id) : undefined
  filters.status = typeof query.status === 'string' ? query.status as ApprovalRequestStatus : undefined
  filters.submittedRange = typeof query.submitted_from === 'string' && typeof query.submitted_to === 'string' ? [dayjs(query.submitted_from), dayjs(query.submitted_to)] : []
  filters.department = typeof query.department === 'string' ? query.department : ''
  filters.applicant = typeof query.applicant === 'string' ? query.applicant : ''
  filters.currentApproverId = typeof query.current_approver_id === 'string' ? query.current_approver_id : undefined
  filters.overdue = query.overdue === 'true' ? true : query.overdue === 'false' ? false : undefined
  filters.page = Number(query.page || 1)
}
function queryParams() {
  const params: Record<string, string | number | boolean> = { page: filters.page, page_size: requestPage.value.page_size }
  if (filters.processAppId) params.process_app_id = filters.processAppId
  if (filters.status) params.status = filters.status
  if (filters.submittedRange.length === 2) { params.submitted_from = filters.submittedRange[0].startOf('day').toISOString(); params.submitted_to = filters.submittedRange[1].endOf('day').toISOString() }
  if (filters.department.trim()) params.department = filters.department.trim()
  if (filters.applicant.trim()) params.applicant = filters.applicant.trim()
  if (filters.currentApproverId) params.current_approver_id = filters.currentApproverId
  if (filters.overdue !== undefined) params.overdue = filters.overdue
  return params
}
async function syncQuery() { const query: Record<string, string> = {}; for (const [key, value] of Object.entries(queryParams())) query[key] = String(value); await router.replace({ query }) }
async function loadOptions() {
  optionsFailed.value = false
  const [appsResult, usersResult] = await Promise.allSettled([api.get('/api/v1/admin/process-apps'), api.get('/api/v1/admin/users')])
  if (appsResult.status === 'fulfilled') processApps.value = appsResult.value.data.data
  else optionsFailed.value = true
  if (usersResult.status === 'fulfilled') users.value = usersResult.value.data.data.filter((user: ApprovalUser) => user.is_active)
  else optionsFailed.value = true
}
async function load() {
  loading.value = true; failed.value = false; summaryFailed.value = false
  const [summaryResult, requestsResult] = await Promise.allSettled([api.get('/api/v1/admin/process-monitor/summary'), api.get('/api/v1/admin/process-monitor/requests', { params: queryParams() })])
  if (summaryResult.status === 'fulfilled') summary.value = summaryResult.value.data.data
  else summaryFailed.value = true
  if (requestsResult.status === 'fulfilled') requestPage.value = requestsResult.value.data.data
  else failed.value = true
  loading.value = false
}
async function search() { filters.page = 1; await syncQuery(); await load() }
async function reset() {
  filters.processAppId = undefined; filters.status = undefined; filters.submittedRange = []; filters.department = ''; filters.applicant = ''; filters.currentApproverId = undefined; filters.overdue = undefined; filters.page = 1
  await syncQuery(); await load()
}
async function changePage(nextPage: number, nextSize: number) { filters.page = nextPage; requestPage.value.page_size = nextSize; await syncQuery(); await load() }
async function openDetail(record: MonitorRequestItem) {
  selectedItem.value = record; drawerOpen.value = true; drawerLoading.value = true; drawerFailed.value = false; detail.value = null
  try { detail.value = (await api.get(`/api/v1/approvals/requests/${record.id}`)).data.data } catch { drawerFailed.value = true } finally { drawerLoading.value = false }
}
onMounted(async () => { readQuery(); await Promise.all([loadOptions(), load()]) })
</script>

<template>
  <div class="page-frame monitor-page">
    <header class="page-heading"><div><p class="eyebrow">PROCESS OPERATIONS</p><h1>流程监控</h1><p>集中查看流程实例与处理进度，仅提供只读追溯。</p></div></header>
    <a-skeleton v-if="loading && !summary" active :paragraph="{ rows: 12 }" />
    <a-alert v-else-if="failed" class="page-alert" type="error" show-icon message="流程实例加载失败"><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert>
    <template v-else>
      <a-alert v-if="summaryFailed" class="page-alert" type="warning" show-icon message="统计汇总暂时不可用，流程实例仍可正常查看"><template #action><a-button size="small" @click="load">重试统计</a-button></template></a-alert>
      <a-alert v-if="optionsFailed" class="page-alert" type="warning" show-icon message="部分筛选选项加载失败，可继续查看全部流程实例"><template #action><a-button size="small" @click="loadOptions">重试选项</a-button></template></a-alert>
      <section v-if="summary" class="monitor-stats" aria-label="流程统计"><div v-for="metric in metrics" :key="metric.key" class="monitor-stat" :class="{ overdue: metric.danger }"><a-statistic :title="metric.title" :value="metric.value" /></div></section>
      <section class="monitor-filter-region" aria-label="流程筛选"><a-form layout="vertical" class="monitor-filters" @submit.prevent="search">
        <a-form-item label="流程应用"><a-select v-model:value="filters.processAppId" aria-label="流程应用筛选" allow-clear placeholder="全部流程应用" :options="processApps.map((app) => ({ value: app.id, label: app.name }))" /></a-form-item>
        <a-form-item label="运行状态"><a-select v-model:value="filters.status" aria-label="运行状态筛选" allow-clear placeholder="全部状态" :options="Object.entries(statusMeta).map(([value, meta]) => ({ value, label: meta.label }))" /></a-form-item>
        <a-form-item label="提交时间"><a-range-picker v-model:value="filters.submittedRange" aria-label="提交时间筛选" class="filter-control" /></a-form-item>
        <a-form-item label="申请部门"><a-input v-model:value="filters.department" aria-label="申请部门筛选" allow-clear placeholder="输入部门" @press-enter="search" /></a-form-item>
        <a-form-item label="申请人"><a-input v-model:value="filters.applicant" aria-label="申请人筛选" allow-clear placeholder="输入姓名" @press-enter="search" /></a-form-item>
        <a-form-item label="当前审批人"><a-select v-model:value="filters.currentApproverId" aria-label="当前审批人筛选" allow-clear placeholder="全部审批人" :options="users.map((user) => ({ value: user.id, label: `${user.display_name} | ${user.department} | ${user.position}` }))" /></a-form-item>
        <a-form-item label="是否超时"><a-select v-model:value="overdueFilterValue" aria-label="是否超时筛选" allow-clear placeholder="全部" :options="[{ value: 'true', label: '是' }, { value: 'false', label: '否' }]" /></a-form-item>
        <a-form-item class="filter-actions"><a-space wrap><a-button type="primary" html-type="submit">查询</a-button><a-button @click="reset">重置</a-button></a-space></a-form-item>
      </a-form></section>
      <section class="monitor-table-region" aria-label="流程实例列表">
        <a-empty v-if="requestPage.items.length === 0" description="暂无流程实例" />
        <a-table v-else class="monitor-table" :data-source="requestPage.items" row-key="id" :pagination="false" :scroll="{ x: 1210 }">
          <a-table-column title="流程编号" data-index="id" :width="100"><template #default="{ record }">#{{ record.id }}</template></a-table-column>
          <a-table-column title="流程名称 / 版本" :width="190"><template #default="{ record }"><strong>{{ record.process_app.name || record.title }}</strong><small class="table-subline">{{ record.process_app.code || '-' }} · v{{ record.process_app.version_number || '-' }}</small></template></a-table-column>
          <a-table-column title="申请人" :width="170"><template #default="{ record }"><strong>{{ record.applicant.name }}</strong><small class="table-subline">{{ record.applicant.department || '-' }} · {{ record.applicant.position || '-' }}</small></template></a-table-column>
          <a-table-column title="提交时间" :width="156"><template #default="{ record }">{{ formatDate(record.submitted_at || record.created_at) }}</template></a-table-column>
          <a-table-column title="已运行" :width="120"><template #default="{ record }">{{ formatElapsed(record) }}</template></a-table-column>
          <a-table-column title="当前节点 / 审批人" :width="220"><template #default="{ record }"><strong>{{ record.current_node.name || '-' }}</strong><small class="table-subline">{{ approverNames(record) }}</small></template></a-table-column>
          <a-table-column title="状态" :width="100"><template #default="{ record }"><a-tag :color="monitorStatus(record).color">{{ monitorStatus(record).label }}</a-tag></template></a-table-column>
          <a-table-column title="超时" :width="90"><template #default="{ record }"><a-tag v-if="record.overdue" color="error">已超时</a-tag><span v-else>-</span></template></a-table-column>
          <a-table-column title="操作" fixed="right" :width="110"><template #default="{ record }"><a-button type="link" @click="openDetail(record)">查看详情</a-button></template></a-table-column>
        </a-table>
        <a-pagination class="monitor-pagination" :current="requestPage.page" :page-size="requestPage.page_size" :total="requestPage.total" show-size-changer @change="changePage" />
      </section>
    </template>
    <a-drawer v-model:open="drawerOpen" title="流程实例详情" width="min(720px, 100vw)" :footer="false">
      <a-skeleton v-if="drawerLoading" active :paragraph="{ rows: 12 }" />
      <a-alert v-else-if="drawerFailed" type="error" show-icon message="实例详情加载失败"><template #action><a-button size="small" @click="selectedItem && openDetail(selectedItem)">重试</a-button></template></a-alert>
      <template v-else-if="detail">
        <section class="drawer-section"><h2>申请人和流程版本</h2><a-descriptions bordered size="small" :column="1"><a-descriptions-item label="申请人">{{ detail.applicant_snapshot?.display_name || detail.applicant_name }}</a-descriptions-item><a-descriptions-item label="部门 / 职位">{{ detail.applicant_snapshot?.department || '-' }} / {{ detail.applicant_snapshot?.position || '-' }}</a-descriptions-item><a-descriptions-item label="流程版本">v{{ selectedItem?.process_app.version_number || '-' }}</a-descriptions-item><a-descriptions-item label="提交时间">{{ formatDate(detail.submitted_at || detail.created_at) }}</a-descriptions-item></a-descriptions></section>
        <section class="drawer-section"><h2>表单快照</h2><a-descriptions bordered size="small" :column="1"><a-descriptions-item v-for="field in detailFields.filter((field) => field.type !== 'section')" :key="field.id" :label="field.label">{{ formatFormValue(field) }}</a-descriptions-item></a-descriptions></section>
        <section class="drawer-section"><h2>当前审批人</h2><a-space v-if="detailApprovers.length" wrap><a-tag v-for="node in detailApprovers" :key="node.id" color="processing">{{ node.approver_name }}</a-tag></a-space><span v-else>当前无待处理节点</span></section>
        <section class="drawer-section"><h2>已选择审批路径</h2><a-steps direction="vertical" size="small" :current="0"><a-step v-for="node in selectedPath" :key="node.id" :title="node.name || node.label || node.type" :description="node.type === 'countersign' ? '会签节点' : '审批节点'" /></a-steps></section>
        <section class="drawer-section"><h2>处理时间线</h2><a-timeline v-if="detail.actions.length"><a-timeline-item v-for="action in detail.actions" :key="action.id"><strong>{{ action.actor_name }}</strong> {{ action.action }}<span v-if="action.comment"> · {{ action.comment }}</span><br /><small>{{ formatDate(action.created_at) }}</small></a-timeline-item></a-timeline><a-empty v-else description="暂无操作记录" /></section>
        <router-link class="drawer-detail-link" :to="`/modules/approval-center/${detail.id}`">打开申请详情</router-link>
      </template>
    </a-drawer>
  </div>
</template>

<style scoped>
.monitor-stats { display:grid; grid-template-columns:repeat(6, minmax(0, 1fr)); gap:12px; margin-bottom:16px; }.monitor-stat { min-height:108px; padding:16px; border:1px solid #f0f0f0; border-radius:6px; background:#fff; }.monitor-stat.overdue { border-color:#ffccc7; }.monitor-stat.overdue :deep(.ant-statistic-content) { color:#cf1322; }.monitor-filter-region, .monitor-table-region { margin-top:16px; padding:18px; border:1px solid #f0f0f0; border-radius:6px; background:#fff; }.monitor-filters { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:0 12px; }.monitor-filters :deep(.ant-form-item) { min-width:0; margin-bottom:12px; }.filter-control { width:100%; }.filter-actions { display:flex; align-items:flex-end; }.monitor-table :deep(.ant-table-cell) { vertical-align:top; }.table-subline { display:block; margin-top:3px; color:#8c8c8c; font-size:12px; line-height:1.45; }.monitor-pagination { display:flex; justify-content:flex-end; margin-top:16px; }.drawer-section { padding:0 0 20px; margin-bottom:20px; border-bottom:1px solid #f0f0f0; }.drawer-section h2 { margin:0 0 12px; font-size:15px; font-weight:600; }.drawer-detail-link { display:inline-block; margin-top:4px; } @media (max-width:1200px) { .monitor-stats { grid-template-columns:repeat(3, minmax(0, 1fr)); }.monitor-filters { grid-template-columns:repeat(3, minmax(0, 1fr)); } } @media (max-width:768px) { .monitor-stats, .monitor-filters { grid-template-columns:1fr; }.monitor-filter-region, .monitor-table-region { padding:14px; }.filter-actions { align-items:flex-start; }.monitor-pagination { justify-content:center; }.monitor-table :deep(.ant-table) { font-size:12px; } }
</style>
