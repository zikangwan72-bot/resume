<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import api from '@/api/client'
import DynamicApprovalForm from '@/components/approval/DynamicApprovalForm.vue'
import PageBackButton from '@/components/PageBackButton.vue'
import { useAuthStore } from '@/stores/auth'
import type { ApprovalUser, FlowNodeSchema, ProcessApp } from '@/types/approval'

const router = useRouter(); const auth = useAuthStore()
const apps = ref<ProcessApp[]>([]); const users = ref<ApprovalUser[]>([]); const selectedApp = ref<ProcessApp | null>(null); const values = ref<Record<string, any>>({}); const form = ref<InstanceType<typeof DynamicApprovalForm>>(); const submitting = ref(false); const submitError = ref(''); const idempotencyKey = ref('')
const loading = ref(true); const loadFailed = ref(false); const usersLoadFailed = ref(false)
const activeApps = computed(() => apps.value.filter(app => app.status === 'published' && app.version_status === 'published'))
const categoryOrder = ['人事', '财务', '采购', '行政', '通用', '通用审批']
const groupedApps = computed(() => {
  const groups = activeApps.value.reduce<Record<string, ProcessApp[]>>((result, app) => {
    const category = app.category?.trim() || '通用'
    ;(result[category] ||= []).push(app)
    return result
  }, {})
  return Object.entries(groups)
    .sort(([left], [right]) => {
      const leftIndex = categoryOrder.indexOf(left); const rightIndex = categoryOrder.indexOf(right)
      if (leftIndex >= 0 || rightIndex >= 0) return (leftIndex < 0 ? categoryOrder.length : leftIndex) - (rightIndex < 0 ? categoryOrder.length : rightIndex)
      return left.localeCompare(right, 'zh-CN')
    })
    .map(([category, categoryApps]) => ({ category, apps: categoryApps.sort((left, right) => left.name.localeCompare(right.name, 'zh-CN')) }))
})
const userNames = computed(() => new Map(users.value.map(user => [user.id, user.display_name])))
const hasLegacyConditions = computed(() => selectedApp.value?.flow_schema.nodes.some(node => node.type === 'condition') === true)
const approvalPathRows = computed(() => {
  const schema = selectedApp.value?.flow_schema
  if (!schema) return []
  const nodes = new Map(schema.nodes.map(node => [node.id, node]))
  const outgoing = new Map<string, string[]>()
  for (const edge of schema.edges) {
    const targets = outgoing.get(edge.source) ?? []
    targets.push(edge.target)
    outgoing.set(edge.source, targets)
  }
  const ordered: FlowNodeSchema[] = []
  const visited = new Set<string>()
  const visit = (id: string) => {
    if (visited.has(id)) return
    visited.add(id)
    const node = nodes.get(id)
    if (!node) return
    if (node.type === 'approval' || node.type === 'countersign') ordered.push(node)
    for (const target of outgoing.get(id) ?? []) visit(target)
  }
  const start = schema.nodes.find(node => node.type === 'start')
  if (start) visit(start.id)
  for (const node of schema.nodes) {
    if ((node.type === 'approval' || node.type === 'countersign') && !visited.has(node.id)) visit(node.id)
  }
  return ordered.map((node, index) => {
    const countersign = node.type === 'countersign' || node.approval_type === 'counter_sign'
    const approverIds = countersign ? (node.approver_ids ?? []) : (node.approver_id ? [node.approver_id] : [])
    return {
      key: node.id,
      order: index + 1,
      name: node.name || node.label || `审批节点 ${index + 1}`,
      mode: countersign ? '会签（全部同意）' : '单人审批',
      approvers: approverIds.length ? approverIds.map(id => userNames.value.get(id) || `未知审批人（${id}）`).join('、') : '待配置',
    }
  })
})
function freshKey() { return globalThis.crypto?.randomUUID?.() || `request-${Date.now()}-${Math.random().toString(36).slice(2)}` }
function selectApp(app: ProcessApp) { selectedApp.value = app; values.value = {}; idempotencyKey.value = freshKey(); submitError.value = '' }
async function loadApps() {
  loading.value = true
  loadFailed.value = false
  usersLoadFailed.value = false
  try {
    const [appsResult, usersResult] = await Promise.allSettled([
      api.get('/api/v1/approvals/apps'),
      api.get('/api/v1/approvals/users'),
    ])
    if (appsResult.status === 'rejected') throw appsResult.reason
    apps.value = appsResult.value.data.data
    if (usersResult.status === 'fulfilled') users.value = usersResult.value.data.data
    else { users.value = []; usersLoadFailed.value = true }
  } catch (error) {
    loadFailed.value = true
    message.error(errorMessage(error, '流程应用加载失败'))
  } finally {
    loading.value = false
  }
}
onMounted(loadApps)
function errorMessage(error: any, fallback: string) { const detail = error?.response?.data?.detail; return typeof detail === 'string' ? detail : detail?.message || fallback }
async function submit() {
  if (!selectedApp.value || submitting.value) return
  submitError.value = ''
  if (!form.value?.validate()) return
  submitting.value = true
  try {
    await api.post('/api/v1/approvals/requests', { process_app_id: selectedApp.value.id, title: `${selectedApp.value.name} - ${new Date().toLocaleDateString('zh-CN')}`, form_data: values.value, idempotency_key: idempotencyKey.value || (idempotencyKey.value = freshKey()) })
    message.success('提交成功'); router.push('/modules/approval-center/requests')
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    if (error?.response?.status === 422 && detail?.field_id) form.value?.setErrors({ [detail.field_id]: detail.message || '字段校验失败' })
    submitError.value = errorMessage(error, '提交失败，请重试')
    message.error(submitError.value)
  } finally { submitting.value = false }
}
</script>

<template>
  <div class="page-frame approval-new">
    <header class="page-heading"><div><p class="eyebrow">NEW REQUEST</p><h1>发起申请</h1></div><div class="heading-actions"><PageBackButton fallback="/modules/approval-center" /></div></header>
    <section><div class="section-title"><div><p class="eyebrow">STEP 1</p><h2>选择流程应用</h2></div></div><a-skeleton v-if="loading" active :paragraph="{ rows: 4 }" /><a-result v-else-if="loadFailed" status="error" title="流程应用加载失败" sub-title="请检查网络或后端服务后重试。"><template #extra><a-button type="primary" @click="loadApps">重新加载</a-button></template></a-result><template v-else><div v-if="groupedApps.length" class="category-groups"><section v-for="group in groupedApps" :key="group.category" class="category-group"><h3>{{ group.category === '通用审批' ? '通用' : group.category }}</h3><div class="type-cards"><button v-for="app in group.apps" :key="app.id" type="button" class="type-card" :class="{ active: selectedApp?.id === app.id }" @click="selectApp(app)"><strong>{{ app.name }}</strong><small>{{ app.description || '暂无说明' }}</small><span>v{{ app.version_number }}</span></button></div></section></div><a-empty v-else description="暂无可发起的已发布流程" /></template></section>
    <template v-if="selectedApp">
      <section class="approval-path"><div class="section-title"><div><p class="eyebrow">STEP 2</p><h2>审批路径</h2><p>提交前确认审批节点和处理人。</p></div><a-tag color="processing">{{ approvalPathRows.length }} 个节点</a-tag></div><a-alert v-if="hasLegacyConditions" type="info" show-icon message="该历史流程包含条件路径，实际审批顺序会根据表单内容确定；下方列出全部可能审批节点。" /><a-alert v-if="usersLoadFailed" type="warning" show-icon message="审批人名称暂时无法同步，请重新加载页面。" /><a-table v-if="approvalPathRows.length" class="approval-path-table" :data-source="approvalPathRows" row-key="key" :pagination="false" size="small"><a-table-column title="顺序" data-index="order" :width="72" /><a-table-column title="审批节点" data-index="name" :width="190"><template #default="{ text }"><strong>{{ text }}</strong></template></a-table-column><a-table-column title="审批方式" data-index="mode" :width="160"><template #default="{ text }"><a-tag>{{ text }}</a-tag></template></a-table-column><a-table-column title="审批人" data-index="approvers" /></a-table><ol v-if="approvalPathRows.length" class="approval-path-mobile"><li v-for="row in approvalPathRows" :key="row.key"><span class="path-index">{{ row.order }}</span><div><strong>{{ row.name }}</strong><span class="path-mode">{{ row.mode }}</span><small>{{ row.approvers }}</small></div></li></ol><a-empty v-else description="该流程尚未配置审批节点" /></section>
      <section class="request-form"><div class="section-title"><div><p class="eyebrow">STEP 3</p><h2>填写申请</h2></div></div><DynamicApprovalForm ref="form" v-model="values" :schema="selectedApp.form_schema" :applicant="auth.user" /><a-alert v-if="submitError" type="error" show-icon :message="submitError" style="margin-bottom:16px" /><a-space wrap><a-button type="primary" size="large" :loading="submitting" @click="submit">提交申请</a-button><a-button size="large" @click="router.back()">取消</a-button></a-space></section>
    </template>
  </div>
</template>

<style scoped>
.category-groups { display:grid; gap:24px; } .category-group { display:grid; gap:10px; } .category-group h3 { margin:0; padding-bottom:8px; border-bottom:1px solid #e5edf1; font-size:16px; } .type-cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:12px; } .type-card { text-align:left; border:1px solid #d9e2e8; border-radius:6px; background:#fff; padding:16px; cursor:pointer; color:#182b35; } .type-card.active { border-color:#147d89; box-shadow:inset 3px 0 #147d89; } .type-card strong,.type-card small,.type-card span { display:block; } .type-card small { color:#687780; margin:6px 0; } .type-card span { color:#147d89; font-size:12px; } .approval-path, .request-form { min-width:0; margin-top:28px; max-width:980px; } .approval-path { display:grid; gap:12px; } .approval-path .section-title { align-items:flex-start; } .approval-path .section-title p:not(.eyebrow) { margin:4px 0 0; color:#687780; } .approval-path-table { border:1px solid #e5edf1; } .approval-path-mobile { display:none; margin:0; padding:0; list-style:none; } @media (max-width: 600px) { .type-cards { grid-template-columns:1fr; } .approval-path .section-title { align-items:flex-start; } .approval-path-table { display:none; } .approval-path-mobile { display:grid; gap:8px; } .approval-path-mobile li { display:grid; grid-template-columns:32px minmax(0,1fr); gap:10px; align-items:start; padding:12px; border:1px solid #d9e2e8; border-radius:6px; background:#fff; } .path-index { display:grid; place-items:center; width:28px; height:28px; border-radius:50%; color:#0b65c2; background:#e8f3ff; font-weight:700; } .approval-path-mobile li div { display:grid; gap:4px; min-width:0; } .approval-path-mobile strong, .approval-path-mobile small { overflow-wrap:anywhere; } .path-mode { color:#52627a; font-size:12px; } .approval-path-mobile small { color:#687780; } }
</style>
