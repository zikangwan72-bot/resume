<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { CheckCircleOutlined, CloseCircleOutlined, SwapOutlined, BellOutlined } from '@ant-design/icons-vue'
import api from '@/api/client'
import PageBackButton from '@/components/PageBackButton.vue'
import { useAuthStore } from '@/stores/auth'
import type { ApprovalRequestDetail, FlowNodeDef, FormField } from '@/types/approval'

const auth = useAuthStore(); const route = useRoute(); const detail = ref<ApprovalRequestDetail | null>(null); const loading = ref(true); const comment = ref(''); const submitting = ref(false); const transferTarget = ref(''); const users = ref<{ id: string; display_name: string }[]>([])
const schemaFields = computed(() => ((detail.value?.form_schema_snapshot as { fields?: FormField[] } | null)?.fields || []))
const date = (value?: string | null) => value ? value.slice(0, 16).replace('T', ' ') : '-'
const status = (value: string) => ({ pending: ['processing', '审批中'], approved: ['success', '已通过'], rejected: ['error', '已驳回'], revoked: ['default', '已撤回'] }[value] || ['default', value])
const flowNode = (index: number): FlowNodeDef | undefined => detail.value?.flow_snapshot.find(node => node.index === index)
const myNode = computed(() => detail.value?.nodes.find(node => node.status === 'pending' && node.approver_id === auth.user?.id))
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
function valueOf(field: FormField) { const value = detail.value?.form_data[field.id || field.key]; if (value == null || value === '') return '-'; return Array.isArray(value) ? value.map(item => typeof item === 'object' ? Object.values(item).join(' / ') : String(item)).join('；') : typeof value === 'object' ? JSON.stringify(value) : String(value) }
function errorMessage(error: any, fallback: string) { const detail = error?.response?.data?.detail; return typeof detail === 'string' ? detail : detail?.message || fallback }
async function load() { loading.value = true; try { detail.value = (await api.get(`/api/v1/approvals/requests/${route.params.id}`)).data.data } catch (error) { message.error(errorMessage(error, '申请加载失败')) } finally { loading.value = false } }
async function action(kind: 'approve' | 'reject' | 'transfer') { const node = myNode.value; if (!node) return message.warning('没有可操作的审批节点'); if (kind === 'reject' && !comment.value.trim()) return message.warning('驳回必须填写原因'); if (kind === 'transfer' && !transferTarget.value) return message.warning('请选择转审目标人'); submitting.value = true; try { const body = kind === 'transfer' ? { target_user_id: transferTarget.value } : { comment: comment.value || '同意' }; await api.post(`/api/v1/approvals/nodes/${node.id}/${kind}`, body); message.success('操作成功'); comment.value = ''; await load() } catch (error) { message.error(errorMessage(error, '操作失败')) } finally { submitting.value = false } }
async function urge() { if (!canUrge.value) return; submitting.value = true; try { await api.put(`/api/v1/approvals/requests/${detail.value!.id}/urge`); message.success('已催办'); await load() } catch (error) { message.error(errorMessage(error, '催办失败')) } finally { submitting.value = false } }
function revoke() { Modal.confirm({ title: '确认撤回', content: '撤回后该申请将标记为已撤回。', onOk: async () => { try { await api.put(`/api/v1/approvals/requests/${detail.value!.id}/revoke`); message.success('已撤回'); await load() } catch (error) { message.error(errorMessage(error, '撤回失败')) } } }) }
onMounted(async () => { await load(); try { users.value = (await api.get('/api/v1/approvals/users')).data.data } catch {} })
</script>

<template>
  <div class="page-frame approval-detail"><a-skeleton v-if="loading" active :paragraph="{ rows: 8 }" /><template v-else-if="detail"><header class="page-heading"><div><p class="eyebrow">REQUEST #{{ detail.id }}</p><h1>{{ detail.title }}</h1><p>{{ detail.applicant_name }} · {{ date(detail.submitted_at || detail.created_at) }}</p></div><div class="heading-actions"><PageBackButton fallback="/modules/approval-center/requests" /><a-tag :color="status(detail.status)[0]">{{ status(detail.status)[1] }}</a-tag></div></header>
    <section class="detail-section"><div class="section-title"><div><p class="eyebrow">SNAPSHOT</p><h2>申请人和版本</h2></div></div><a-descriptions bordered :column="{ xs: 1, sm: 2 }"><a-descriptions-item label="申请人">{{ detail.applicant_snapshot?.display_name || detail.applicant_name }}</a-descriptions-item><a-descriptions-item label="邮箱">{{ detail.applicant_snapshot?.email || '-' }}</a-descriptions-item><a-descriptions-item label="部门">{{ detail.applicant_snapshot?.department || '-' }}</a-descriptions-item><a-descriptions-item label="职位">{{ detail.applicant_snapshot?.position || '-' }}</a-descriptions-item><a-descriptions-item label="流程版本">v{{ detail.process_version_id || '-' }}</a-descriptions-item><a-descriptions-item label="提交时间">{{ date(detail.submitted_at || detail.created_at) }}</a-descriptions-item></a-descriptions></section>
    <section class="detail-section"><div class="section-title"><div><p class="eyebrow">FORM SNAPSHOT</p><h2>申请内容</h2></div></div><a-descriptions bordered :column="1"><a-descriptions-item v-for="field in schemaFields.filter(field => field.type !== 'section')" :key="field.id || field.key" :label="field.label">{{ valueOf(field) }}</a-descriptions-item></a-descriptions></section>
    <section class="detail-section"><div class="section-title"><div><p class="eyebrow">PATH</p><h2>已选择审批路径</h2></div></div><a-steps direction="vertical" size="small" :current="currentPathIndex"><a-step v-for="node in actionablePath" :key="node.id" :title="node.name || node.label || node.type" :description="node.type === 'countersign' ? '会签节点' : '审批节点'" /></a-steps><div class="node-list"><div v-for="node in detail.nodes" :key="node.id" class="node-row"><strong>{{ flowNode(node.node_index)?.name || `节点 ${node.node_index + 1}` }}</strong><span>{{ node.approver_name }}</span><a-tag :color="status(node.status)[0]">{{ status(node.status)[1] }}</a-tag><small v-if="node.comment">{{ node.comment }}</small></div></div></section>
    <section v-if="myNode" class="detail-section action-panel"><div class="section-title"><div><p class="eyebrow">ACTION</p><h2>审批操作</h2></div></div><a-textarea v-model:value="comment" aria-label="审批意见" placeholder="审批意见（驳回时必填）" :rows="3" /><a-space wrap style="margin-top:12px"><a-button type="primary" :loading="submitting" @click="action('approve')"><CheckCircleOutlined />同意</a-button><a-button danger :loading="submitting" @click="action('reject')"><CloseCircleOutlined />驳回</a-button><a-select v-model:value="transferTarget" aria-label="转审目标人" placeholder="选择转审人" style="min-width:180px"><a-select-option v-for="user in users" :key="user.id" :value="user.id">{{ user.display_name }}</a-select-option></a-select><a-button :loading="submitting" @click="action('transfer')"><SwapOutlined />转审</a-button></a-space></section>
    <section v-if="canUrge || (detail.status === 'pending' && detail.applicant_id === auth.user?.id)" class="detail-section"><a-space><a-button v-if="canUrge" :loading="submitting" @click="urge"><BellOutlined />催办</a-button><a-button v-if="detail.status === 'pending' && detail.applicant_id === auth.user?.id" @click="revoke">撤回申请</a-button></a-space></section>
    <section class="detail-section"><div class="section-title"><div><p class="eyebrow">TIMELINE</p><h2>操作记录</h2></div></div><a-timeline v-if="detail.actions.length"><a-timeline-item v-for="item in detail.actions" :key="item.id"><strong>{{ item.actor_name }}</strong> {{ item.action }} <span v-if="item.comment">· {{ item.comment }}</span><br /><small>{{ date(item.created_at) }}</small></a-timeline-item></a-timeline><a-empty v-else description="暂无操作记录" /></section>
  </template></div>
</template>

<style scoped>
.detail-section { margin-top:28px; max-width:980px; } .heading-actions { display:flex; gap:10px; align-items:center; } .node-list { margin-top:12px; border-top:1px solid #e5edf1; } .node-row { display:grid; grid-template-columns:minmax(140px,1fr) minmax(90px,auto) auto; gap:10px; padding:10px 0; border-bottom:1px solid #e5edf1; align-items:center; } .node-row small { grid-column:1 / -1; color:#667780; } .action-panel { border-top:2px solid #147d89; padding-top:16px; } @media (max-width:600px) { .node-row { grid-template-columns:1fr auto; } .heading-actions { align-items:flex-end; } }
</style>
