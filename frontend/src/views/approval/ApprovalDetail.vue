<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { BellOutlined } from '@ant-design/icons-vue'
import api from '@/api/client'
import ApprovalActionBar from '@/components/approval/ApprovalActionBar.vue'
import DynamicApprovalForm from '@/components/approval/DynamicApprovalForm.vue'
import PageBackButton from '@/components/PageBackButton.vue'
import { useAuthStore } from '@/stores/auth'
import type { ApprovalRequestDetail, FlowNodeDef } from '@/types/approval'

const auth = useAuthStore(); const route = useRoute(); const detail = ref<ApprovalRequestDetail | null>(null); const loading = ref(true); const loadError = ref(''); const submitting = ref(false); const users = ref<{ id: string; display_name: string }[]>([]); const actionBar = ref<InstanceType<typeof ApprovalActionBar>>(); const revisionForm = ref<InstanceType<typeof DynamicApprovalForm>>(); const revisionValues = ref<Record<string, any>>({}); const revisionComment = ref('')
const date = (value?: string | null) => value ? value.slice(0, 16).replace('T', ' ') : '-'
const status = (value: string) => ({ pending: ['processing', '审批中'], revision: ['warning', '待修改'], returned: ['warning', '已退回'], approved: ['success', '已通过'], rejected: ['error', '已驳回'], cancelled: ['default', '已取消'], revoked: ['default', '已撤回'] }[value] || ['default', value])
const flowNode = (index: number): FlowNodeDef | undefined => detail.value?.flow_snapshot.find(node => node.index === index)
const myNode = computed(() => detail.value?.nodes.find(node => node.status === 'pending' && node.approver_id === auth.user?.id))
const myFlowNode = computed(() => myNode.value ? flowNode(myNode.value.node_index) : undefined)
const canTransfer = computed(() => myFlowNode.value?.allow_transfer === true)
const canRevise = computed(() => detail.value?.status === 'revision' && detail.value.return_context?.target_user_id === auth.user?.id)
const actionablePath = computed(() => detail.value?.flow_snapshot.filter(node => node.type === 'approval' || node.type === 'countersign') || [])
const currentPathIndex = computed(() => {
  const pending = detail.value?.nodes.find(node => node.status === 'pending')
  if (!pending) return 0
  const byKey = actionablePath.value.findIndex(node => node.id === pending.node_key)
  if (byKey >= 0) return byKey
  const byLegacyIndex = actionablePath.value.findIndex(node => node.index === pending.node_index)
  return Math.max(0, byLegacyIndex)
})
const canUrge = computed(() => detail.value?.status === 'pending' && detail.value.applicant_id === auth.user?.id)
function errorMessage(error: any, fallback: string) { const detail = error?.response?.data?.detail; return typeof detail === 'string' ? detail : detail?.message || fallback }
async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const payload = (await api.get(`/api/v1/approvals/requests/${route.params.id}`)).data.data as ApprovalRequestDetail
    revisionValues.value = structuredClone(payload.form_data || {})
    detail.value = payload
  } catch (error) {
    detail.value = null
    loadError.value = errorMessage(error, '申请加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
async function nodeAction(kind: 'approve' | 'reject' | 'return', body: Record<string, unknown>) { const node = myNode.value; if (!node) return message.warning('没有可操作的审批节点'); submitting.value = true; try { await api.post(`/api/v1/approvals/nodes/${node.id}/${kind}`, body); message.success(kind === 'return' ? '已退回上一步' : kind === 'reject' ? '已驳回发起人' : '已同意并提交'); actionBar.value?.clear(); await load() } catch (error) { message.error(errorMessage(error, '操作失败')) } finally { submitting.value = false } }
async function transfer(payload: { targetUserId: string; comment: string }) { const node = myNode.value; if (!node) return message.warning('没有可操作的审批节点'); submitting.value = true; try { await api.post(`/api/v1/approvals/nodes/${node.id}/transfer`, { target_user_id: payload.targetUserId, comment: payload.comment }); message.success('已转审'); actionBar.value?.clear(); await load() } catch (error) { message.error(errorMessage(error, '转审失败')) } finally { submitting.value = false } }
async function resubmit() { if (!detail.value || !canRevise.value || !revisionForm.value?.validate()) return; submitting.value = true; try { await api.post(`/api/v1/approvals/requests/${detail.value.id}/resubmit`, { form_data: revisionValues.value, comment: revisionComment.value.trim() || undefined }); message.success('修改已提交，流程返回原审批节点'); revisionComment.value = ''; await load() } catch (error) { message.error(errorMessage(error, '重新提交失败')) } finally { submitting.value = false } }
async function urge() { if (!canUrge.value) return; submitting.value = true; try { await api.put(`/api/v1/approvals/requests/${detail.value!.id}/urge`); message.success('已催办'); await load() } catch (error) { message.error(errorMessage(error, '催办失败')) } finally { submitting.value = false } }
function revoke() { Modal.confirm({ title: '确认撤回', content: '撤回后该申请将标记为已撤回。', onOk: async () => { try { await api.put(`/api/v1/approvals/requests/${detail.value!.id}/revoke`); message.success('已撤回'); await load() } catch (error) { message.error(errorMessage(error, '撤回失败')) } } }) }
onMounted(async () => { await load(); try { users.value = (await api.get('/api/v1/approvals/users')).data.data } catch {} })
</script>

<template>
  <div class="page-frame approval-detail"><a-skeleton v-if="loading" active :paragraph="{ rows: 8 }" /><template v-else-if="detail"><header class="page-heading"><div><p class="eyebrow">REQUEST #{{ detail.id }}</p><h1>{{ detail.title }}</h1><p>{{ detail.applicant_name }} · {{ date(detail.submitted_at || detail.created_at) }}</p></div><div class="heading-actions"><PageBackButton fallback="/modules/approval-center/requests" /><a-tag :color="status(detail.status)[0]">{{ status(detail.status)[1] }}</a-tag></div></header>
    <section class="detail-section"><div class="section-title"><div><p class="eyebrow">SNAPSHOT</p><h2>申请人和版本</h2></div></div><a-descriptions bordered :column="{ xs: 1, sm: 2 }"><a-descriptions-item label="申请人">{{ detail.applicant_snapshot?.display_name || detail.applicant_name }}</a-descriptions-item><a-descriptions-item label="邮箱">{{ detail.applicant_snapshot?.email || '-' }}</a-descriptions-item><a-descriptions-item label="部门">{{ detail.applicant_snapshot?.department || '-' }}</a-descriptions-item><a-descriptions-item label="职位">{{ detail.applicant_snapshot?.position || '-' }}</a-descriptions-item><a-descriptions-item label="流程版本">v{{ detail.process_version_id || '-' }}</a-descriptions-item><a-descriptions-item label="提交时间">{{ date(detail.submitted_at || detail.created_at) }}</a-descriptions-item></a-descriptions></section>
    <section class="detail-section"><div class="section-title"><div><p class="eyebrow">FORM SNAPSHOT</p><h2>{{ canRevise ? '修改申请内容' : '申请内容' }}</h2></div></div><a-alert v-if="detail.return_context" type="warning" show-icon :message="`退回原因：${detail.return_context.reason}`" :description="canRevise ? '完成修改后重新提交，流程会回到退回该申请的审批节点。' : `当前由 ${detail.return_context.target_user_name} 处理返工。`" class="return-alert" /><DynamicApprovalForm v-if="canRevise" ref="revisionForm" v-model="revisionValues" :schema="detail.form_schema_snapshot" :applicant="detail.applicant_snapshot" /><DynamicApprovalForm v-else v-model="revisionValues" :schema="detail.form_schema_snapshot" :applicant="detail.applicant_snapshot" readonly /><div v-if="canRevise" class="revision-submit"><a-textarea v-model:value="revisionComment" aria-label="返工说明" placeholder="说明本次修改内容（可选）" :rows="2" /><a-button type="primary" :loading="submitting" @click="resubmit">修改后重新提交</a-button></div></section>
    <section class="detail-section"><div class="section-title"><div><p class="eyebrow">PATH</p><h2>已选择审批路径</h2></div></div><a-steps direction="vertical" size="small" :current="currentPathIndex"><a-step v-for="node in actionablePath" :key="node.id" :title="node.name || node.label || node.type" :description="node.type === 'countersign' ? '会签节点' : '审批节点'" /></a-steps><div class="node-list"><div v-for="node in detail.nodes" :key="node.id" class="node-row"><strong>{{ flowNode(node.node_index)?.name || `节点 ${node.node_index + 1}` }}</strong><span>{{ node.approver_name }}</span><a-tag :color="status(node.status)[0]">{{ status(node.status)[1] }}</a-tag><small v-if="node.comment">{{ node.comment }}</small></div></div></section>
    <section v-if="myNode" class="detail-section action-panel"><div class="section-title"><div><p class="eyebrow">ACTION</p><h2>审批操作</h2></div></div><ApprovalActionBar ref="actionBar" :loading="submitting" :can-transfer="canTransfer" :users="users" @return="nodeAction('return', { comment: $event })" @reject="nodeAction('reject', { comment: $event })" @approve="nodeAction('approve', { comment: $event || '同意' })" @transfer="transfer" /></section>
    <section v-if="canUrge || (detail.status === 'pending' && detail.applicant_id === auth.user?.id)" class="detail-section"><a-space><a-button v-if="canUrge" :loading="submitting" @click="urge"><BellOutlined />催办</a-button><a-button v-if="detail.status === 'pending' && detail.applicant_id === auth.user?.id" @click="revoke">撤回申请</a-button></a-space></section>
    <section class="detail-section"><div class="section-title"><div><p class="eyebrow">TIMELINE</p><h2>操作记录</h2></div></div><a-timeline v-if="detail.actions.length"><a-timeline-item v-for="item in detail.actions" :key="item.id"><strong>{{ item.actor_name }}</strong> {{ ({ approve: '同意并提交', reject: '驳回发起人', return: '退回上一步', resubmit: '修改后重新提交', transfer: '转审', revoke: '撤回申请', urge: '催办' } as Record<string, string>)[item.action] || item.action }} <span v-if="item.comment">· {{ item.comment }}</span><br /><small>{{ date(item.created_at) }}</small></a-timeline-item></a-timeline><a-empty v-else description="暂无操作记录" /></section>
  </template><a-result v-else status="error" :sub-title="loadError"><template #title><h1>申请加载失败</h1></template><template #extra><a-space><PageBackButton fallback="/modules/approval-center/requests" /><a-button type="primary" @click="load">重新加载</a-button></a-space></template></a-result></div>
</template>

<style scoped>
.detail-section { margin-top:28px; max-width:980px; } .heading-actions { display:flex; gap:10px; align-items:center; } .return-alert { margin-bottom:16px; } .revision-submit { display:grid; justify-items:end; gap:10px; margin-top:16px; padding-top:16px; border-top:1px solid #e5edf1; } .revision-submit :deep(.ant-input) { width:100%; } .node-list { margin-top:12px; border-top:1px solid #e5edf1; } .node-row { display:grid; grid-template-columns:minmax(140px,1fr) minmax(90px,auto) auto; gap:10px; padding:10px 0; border-bottom:1px solid #e5edf1; align-items:center; } .node-row small { grid-column:1 / -1; color:#667780; } .action-panel { border-top:2px solid #147d89; padding-top:16px; } @media (max-width:600px) { .node-row { grid-template-columns:1fr auto; } .heading-actions { align-items:flex-end; } .revision-submit { justify-items:stretch; } }
</style>
