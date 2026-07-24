<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { message } from 'ant-design-vue'
import api from '@/api/client'
import FormSchemaDesigner from '@/components/approval/FormSchemaDesigner.vue'
import FlowSchemaDesigner from '@/components/approval/FlowSchemaDesigner.vue'
import type { ApiEnvelope, ApprovalUser, FlowValidationIssue, ProcessApp, ProcessAppDraft } from '@/types/approval'

const route = useRoute(); const router = useRouter(); const formRef = ref()
const step = ref(0); const loading = ref(false); const saving = ref(false); const loaded = ref(false); const baseline = ref('')
const users = ref<ApprovalUser[]>([]); const flowIssues = ref<FlowValidationIssue[]>([]); const publishIssues = ref<FlowValidationIssue[]>([])
const flowDesigner = ref<{ focusTarget: (id?: string) => void } | null>(null)
const draft = reactive<ProcessAppDraft>({ code: '', name: '', category: '通用审批', description: '', form_schema: { fields: [] }, flow_schema: { nodes: [], edges: [] } })
const isEdit = computed(() => typeof route.params.id === 'string')
const visibleFlowIssues = computed(() => {
  const errors = new Map<string, { issue: FlowValidationIssue; type: 'warning' | 'error' }>()
  const keyFor = (issue: FlowValidationIssue) => `${issue.code}\u0000${issue.target_id ?? ''}`
  flowIssues.value.forEach((issue) => errors.set(keyFor(issue), { issue, type: 'warning' }))
  publishIssues.value.forEach((issue) => errors.set(keyFor(issue), { issue, type: 'error' }))
  return [...errors.values()]
})
const formRules = { name: [{ required: true, whitespace: true, message: '请输入流程名称', trigger: 'blur' }], code: [{ required: true, whitespace: true, message: '请输入流程编号', trigger: 'blur' }, { pattern: /^[A-Za-z][A-Za-z0-9_-]*$/, message: '编号须以字母开头，只能使用字母、数字、下划线或连字符', trigger: 'blur' }], category: [{ required: true, message: '请选择流程分类', trigger: 'change' }] }
const snapshot = () => JSON.stringify(draft)
const dirty = computed(() => loaded.value && snapshot() !== baseline.value)
function nonemptyString(value: unknown) { return typeof value === 'string' && value.trim() ? value.trim() : undefined }
function normalizeOptionalText(value: unknown) { return typeof value === 'string' ? value.trim() : value }
function normalizedOptions(options: unknown) { return Array.isArray(options) ? options.map((option) => typeof option === 'string' ? option.trim() : option) : options }
function normalizeFields(fields: unknown): ProcessAppDraft['form_schema']['fields'] {
  const fieldIds = new Set<string>()
  const legacyFields = Array.isArray(fields) ? fields as Array<Record<string, unknown>> : []
  return legacyFields.map((field) => {
    let id = nonemptyString(field.id) ?? nonemptyString(field.key)
    if (!id || fieldIds.has(id)) id = crypto.randomUUID()
    fieldIds.add(id)
    const columnIds = new Set<string>()
    const legacyColumns = Array.isArray(field.columns) ? field.columns as Array<Record<string, unknown>> : undefined
    const columns = legacyColumns?.map((column) => {
      let columnId = nonemptyString(column.id) ?? nonemptyString(column.key)
      if (!columnId || columnIds.has(columnId)) columnId = crypto.randomUUID()
      columnIds.add(columnId)
      return {
        ...column,
        id: columnId,
        key: columnId,
        label: nonemptyString(column.label) ?? columnId ?? String(column.type ?? '明细列'),
        placeholder: normalizeOptionalText(column.placeholder),
        help: normalizeOptionalText(column.help),
        options: normalizedOptions(column.options),
      }
    })
    return {
      ...field,
      id,
      key: id,
      label: nonemptyString(field.label) ?? id ?? String(field.type ?? '字段'),
      placeholder: normalizeOptionalText(field.placeholder),
      help: normalizeOptionalText(field.help),
      options: normalizedOptions(field.options),
      columns,
    }
  }) as ProcessAppDraft['form_schema']['fields']
}
function apply(app: ProcessApp) {
  const fields = normalizeFields(app.form_schema?.fields ?? [])
  Object.assign(draft, { id: app.id, code: app.code, name: app.name, category: app.category, description: app.description ?? '', form_schema: { fields }, flow_schema: app.flow_schema ?? { nodes: [], edges: [] } })
}
function validateSchema() {
  draft.form_schema = { fields: normalizeFields(draft.form_schema.fields) }
  const ids = new Set<string>()
  for (const field of draft.form_schema.fields) {
    if (!field.id || ids.has(field.id)) { message.error('字段标识不能为空或重复'); step.value = 1; return false }
    ids.add(field.id)
    if (['radio', 'checkbox', 'select'].includes(field.type)) {
      const options = field.options ?? []
      if (!options.length || options.some((option) => !option) || new Set(options).size !== options.length) { message.error(`字段“${field.label || '未命名'}”的选项不能为空或重复`); step.value = 1; return false }
    }
    if (['number', 'money'].includes(field.type) && (!Number.isInteger(field.precision ?? 0) || (field.precision ?? 0) < 0 || (field.precision ?? 0) > 6 || (field.min !== undefined && field.max !== undefined && field.min > field.max))) { message.error(`字段“${field.label || '未命名'}”的数值范围或小数位无效`); step.value = 1; return false }
    const columnIds = new Set<string>()
    for (const column of field.columns ?? []) {
      if (!column.id || columnIds.has(column.id)) { message.error('明细列标识不能为空或重复'); step.value = 1; return false }
      columnIds.add(column.id)
      if (!column.label) { message.error('明细列名称不能为空'); step.value = 1; return false }
      if (column.type === 'select') { const options = column.options ?? []; if (!options.length || options.some((option) => !option) || new Set(options).size !== options.length) { message.error(`明细列“${column.label}”的选项不能为空或重复`); step.value = 1; return false } }
      if (['number', 'money'].includes(column.type) && (!Number.isInteger(column.precision ?? 0) || (column.precision ?? 0) < 0 || (column.precision ?? 0) > 6 || (column.min !== undefined && column.max !== undefined && column.min > column.max))) { message.error(`明细列“${column.label}”的数值范围或小数位无效`); step.value = 1; return false }
    }
  }
  return true
}
async function load() {
  await loadUsers()
  if (!isEdit.value) { baseline.value = snapshot(); loaded.value = true; return }
  loading.value = true
  try { const response = await api.get<ApiEnvelope<ProcessApp>>(`/api/v1/admin/process-apps/${route.params.id}`); apply(response.data.data); baseline.value = snapshot(); loaded.value = true }
  catch (error) { message.error((error as any).response?.data?.detail ?? '流程应用加载失败') }
  finally { loading.value = false }
}
async function loadUsers() {
  try { const response = await api.get<ApiEnvelope<ApprovalUser[]>>('/api/v1/admin/users'); users.value = response.data.data.filter((user) => user.is_active) }
  catch { message.error('启用员工加载失败，请重试') }
}
async function next() { if (step.value === 0) { await formRef.value?.validate(); } if (step.value < 3) step.value += 1 }
function previous() { if (step.value > 0) step.value -= 1 }
async function save(): Promise<ProcessApp | null> {
  try { await formRef.value?.validate() } catch { step.value = 0; return }
  if (!validateSchema()) return
  saving.value = true
  const payload = { code: draft.code.trim(), name: draft.name.trim(), category: draft.category, description: draft.description || null, form_schema: draft.form_schema, flow_schema: draft.flow_schema }
  try {
    const response = isEdit.value ? await api.put<ApiEnvelope<ProcessApp>>(`/api/v1/admin/process-apps/${draft.id}`, payload) : await api.post<ApiEnvelope<ProcessApp>>('/api/v1/admin/process-apps', payload)
    apply(response.data.data); baseline.value = snapshot(); message.success('草稿已保存')
    if (!isEdit.value) await router.replace(`/admin/process-apps/${draft.id}/edit`)
    return response.data.data
  } catch (error) { message.error((error as any).response?.data?.detail ?? '草稿保存失败，请重试'); return null } finally { saving.value = false }
}
async function focusDefinitionIssue(issue: FlowValidationIssue) {
  const field = draft.form_schema.fields.find((item) => item.id === issue.target_id)
  if (field) { step.value = 1; await nextTick(); document.querySelector<HTMLElement>(`[data-field-id="${CSS.escape(field.id)}"]`)?.focus(); return }
  step.value = 2; await nextTick(); flowDesigner.value?.focusTarget(issue.target_id)
}
async function publish() {
  publishIssues.value = []
  const saved = await save()
  if (!saved?.id) return
  saving.value = true
  try {
    const response = await api.post<ApiEnvelope<ProcessApp>>(`/api/v1/admin/process-apps/${saved.id}/publish`)
    apply(response.data.data); baseline.value = snapshot()
    message.success(`流程已发布，当前版本 v${response.data.data.version_number ?? ''}`)
    await router.push('/admin/process-apps')
  } catch (error) {
    const detail = (error as any).response?.data?.detail
    if (detail?.code === 'definition_invalid' && Array.isArray(detail.errors)) {
      publishIssues.value = detail.errors
      await focusDefinitionIssue(detail.errors[0])
    } else message.error(detail ?? '发布失败，请重试')
  } finally { saving.value = false }
}
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => { void load(); window.addEventListener('beforeunload', beforeUnload) }); onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
onBeforeRouteLeave(() => !dirty.value || window.confirm('有未保存的修改，确定离开吗？'))
watch(() => route.params.id, () => { void load() })
</script>

<template>
  <div class="page-frame editor-page">
    <a-page-header :title="isEdit ? '编辑流程应用' : '新建流程应用'" @back="router.push('/admin/process-apps')" />
    <a-spin :spinning="loading">
      <section class="editor-shell">
        <a-steps :current="step" responsive>
          <a-step title="基本信息" /><a-step title="表单设计" /><a-step title="流程设计" /><a-step title="预览发布" />
        </a-steps>
        <div v-show="step === 0" class="stage basic-stage">
          <a-form ref="formRef" :model="draft" :rules="formRules" layout="vertical" class="basic-form">
            <a-form-item label="流程名称" name="name"><a-input v-model:value="draft.name" aria-label="流程名称" maxlength="120" /></a-form-item>
            <a-form-item label="流程编号" name="code"><a-input v-model:value="draft.code" aria-label="流程编号" maxlength="80" /></a-form-item>
            <a-form-item label="流程分类" name="category"><a-select v-model:value="draft.category" aria-label="流程分类" :options="['通用审批', '行政', '财务', '采购', '人事'].map((value) => ({ value }))" /></a-form-item>
            <a-form-item label="流程说明"><a-textarea v-model:value="draft.description" aria-label="流程说明" :rows="4" maxlength="500" /></a-form-item>
          </a-form>
        </div>
        <div v-show="step === 1" class="stage"><FormSchemaDesigner v-model="draft.form_schema" /></div>
        <div v-show="step === 2" class="stage flow-stage">
          <a-alert v-for="entry in visibleFlowIssues" :key="`${entry.issue.code}-${entry.issue.target_id}`" class="definition-alert" :type="entry.type" show-icon :message="entry.issue.message" @click="focusDefinitionIssue(entry.issue)" />
          <FlowSchemaDesigner ref="flowDesigner" v-model="draft.flow_schema" :users="users" :fields="draft.form_schema.fields" @validationChange="flowIssues = $event" />
        </div>
        <div v-show="step === 3" class="stage preview-stage">
          <div class="preview-heading"><div><h2>预览发布</h2><p>确认应用元信息、表单字段与审批流后发布新版本。</p></div><a-tag :color="flowIssues.length ? 'warning' : 'success'">{{ flowIssues.length ? `${flowIssues.length} 项流程校验提示` : '流程校验通过' }}</a-tag></div>
          <div class="preview-grid">
            <section><h3>基本信息</h3><dl><dt>名称</dt><dd>{{ draft.name || '未命名流程' }}</dd><dt>编号</dt><dd>{{ draft.code || '未设置' }}</dd><dt>分类</dt><dd>{{ draft.category }}</dd></dl></section>
            <section><h3>表单字段</h3><p v-if="!draft.form_schema.fields.length" class="muted">尚未配置业务字段</p><ul v-else><li v-for="field in draft.form_schema.fields" :key="field.id">{{ field.label || field.id }} <span>{{ field.type }}</span></li></ul></section>
            <section><h3>审批流</h3><p>{{ draft.flow_schema.nodes.filter((node) => node.type === 'approval' || node.type === 'countersign').length }} 个审批节点，{{ draft.flow_schema.nodes.filter((node) => node.type === 'condition').length }} 个条件分支</p><a-button @click="step = 2">查看流程设计</a-button></section>
          </div>
        </div>
        <footer class="editor-footer"><a-button v-if="step > 0" @click="previous">上一环节</a-button><span class="footer-fill" /><a-button :loading="saving" aria-label="保存草稿" @click="save">保存草稿</a-button><a-button v-if="step < 3" type="primary" @click="next">下一步</a-button><a-button v-else type="primary" :loading="saving" @click="publish">发布流程</a-button></footer>
      </section>
    </a-spin>
  </div>
</template>

<style scoped>
.editor-page { max-width: 1440px; } .editor-shell { display: grid; gap: 20px; padding: 20px; background: #fff; } .stage { min-width: 0; } .basic-stage { max-width: 720px; } .basic-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 16px; } .basic-form :deep(.ant-form-item:last-child) { grid-column: 1 / -1; } .flow-stage { display: grid; gap: 12px; } .definition-alert { cursor: pointer; } .preview-stage { display: grid; gap: 16px; } .preview-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; border-bottom: 1px solid #e7ebf1; padding-bottom: 12px; } .preview-heading h2, .preview-grid h3 { margin: 0; } .preview-heading p, .muted { margin: 4px 0 0; color: #687386; } .preview-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; } .preview-grid section { min-width: 0; padding-right: 16px; border-right: 1px solid #edf0f4; } .preview-grid section:last-child { border-right: 0; } dl { display: grid; grid-template-columns: 64px 1fr; gap: 8px; margin: 14px 0 0; } dt, .preview-grid li span { color: #687386; } dd { margin: 0; overflow-wrap: anywhere; } .preview-grid ul { display: grid; gap: 8px; margin: 14px 0 0; padding: 0; list-style: none; } .preview-grid li { display: flex; justify-content: space-between; gap: 8px; } .editor-footer { display: flex; align-items: center; gap: 8px; padding-top: 4px; border-top: 1px solid #f0f0f0; } .footer-fill { flex: 1; }
@media (max-width: 760px) { .editor-page { padding: 0; } .editor-shell { padding: 14px; } .basic-form, .preview-grid { grid-template-columns: 1fr; } .preview-grid section { padding: 0 0 14px; border-right: 0; border-bottom: 1px solid #edf0f4; } .preview-grid section:last-child { border-bottom: 0; } .preview-heading .ant-tag { display: none; } .editor-footer { position: static; padding: 14px 0 0; background: #fff; flex-wrap: wrap; } }
</style>
