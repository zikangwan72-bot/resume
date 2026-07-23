<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { message } from 'ant-design-vue'
import api from '@/api/client'
import FormSchemaDesigner from '@/components/approval/FormSchemaDesigner.vue'
import type { ApiEnvelope, ProcessApp, ProcessAppDraft } from '@/types/approval'

const route = useRoute(); const router = useRouter(); const formRef = ref()
const step = ref(0); const loading = ref(false); const saving = ref(false); const loaded = ref(false); const baseline = ref('')
const draft = reactive<ProcessAppDraft>({ code: '', name: '', category: '通用审批', description: '', form_schema: { fields: [] }, flow_schema: { nodes: [], edges: [] } })
const isEdit = computed(() => typeof route.params.id === 'string')
const formRules = { name: [{ required: true, whitespace: true, message: '请输入流程名称', trigger: 'blur' }], code: [{ required: true, whitespace: true, message: '请输入流程编号', trigger: 'blur' }, { pattern: /^[A-Za-z][A-Za-z0-9_-]*$/, message: '编号须以字母开头，只能使用字母、数字、下划线或连字符', trigger: 'blur' }], category: [{ required: true, message: '请选择流程分类', trigger: 'change' }] }
const snapshot = () => JSON.stringify(draft)
const dirty = computed(() => loaded.value && snapshot() !== baseline.value)
function apply(app: ProcessApp) {
  const ids = new Set<string>()
  const fields = (app.form_schema?.fields ?? []).map((field) => {
    const id = field.id && !ids.has(field.id) ? field.id : crypto.randomUUID()
    ids.add(id)
    return { ...field, id, key: field.key || id }
  })
  Object.assign(draft, { id: app.id, code: app.code, name: app.name, category: app.category, description: app.description ?? '', form_schema: { fields }, flow_schema: app.flow_schema ?? { nodes: [], edges: [] } })
}
function validateSchema() {
  const ids = new Set<string>()
  for (const field of draft.form_schema.fields) {
    if (!field.id || ids.has(field.id)) { message.error('字段标识不能为空或重复'); step.value = 1; return false }
    ids.add(field.id)
    if (['radio', 'checkbox', 'select'].includes(field.type) && !field.options?.some((option) => option.trim())) { message.error(`字段“${field.label || '未命名'}”至少需要一个选项`); step.value = 1; return false }
    const columnIds = new Set<string>()
    for (const column of field.columns ?? []) {
      if (!column.id || columnIds.has(column.id)) { message.error('明细列标识不能为空或重复'); step.value = 1; return false }
      columnIds.add(column.id)
    }
  }
  return true
}
async function load() {
  if (!isEdit.value) { baseline.value = snapshot(); loaded.value = true; return }
  loading.value = true
  try { const response = await api.get<ApiEnvelope<ProcessApp>>(`/api/v1/admin/process-apps/${route.params.id}`); apply(response.data.data); baseline.value = snapshot(); loaded.value = true }
  catch (error) { message.error((error as any).response?.data?.detail ?? '流程应用加载失败') }
  finally { loading.value = false }
}
async function next() { if (step.value === 0) { await formRef.value?.validate(); } if (step.value < 3) step.value += 1 }
function previous() { if (step.value > 0) step.value -= 1 }
async function save() {
  try { await formRef.value?.validate() } catch { step.value = 0; return }
  if (!validateSchema()) return
  saving.value = true
  const payload = { code: draft.code.trim(), name: draft.name.trim(), category: draft.category, description: draft.description || null, form_schema: draft.form_schema, flow_schema: draft.flow_schema }
  try {
    const response = isEdit.value ? await api.put<ApiEnvelope<ProcessApp>>(`/api/v1/admin/process-apps/${draft.id}`, payload) : await api.post<ApiEnvelope<ProcessApp>>('/api/v1/admin/process-apps', payload)
    apply(response.data.data); baseline.value = snapshot(); message.success('草稿已保存')
    if (!isEdit.value) await router.replace(`/admin/process-apps/${draft.id}/edit`)
  } catch (error) { message.error((error as any).response?.data?.detail ?? '草稿保存失败，请重试') } finally { saving.value = false }
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
        <div v-show="step === 2" class="stage placeholder"><a-empty description="流程设计将在 Task 10 实现" /></div>
        <div v-show="step === 3" class="stage placeholder"><a-empty description="预览发布将在后续任务实现" /></div>
        <footer class="editor-footer"><a-button v-if="step > 0" @click="previous">上一环节</a-button><span class="footer-fill" /><a-button :loading="saving" aria-label="保存草稿" @click="save">保存草稿</a-button><a-button v-if="step < 3" type="primary" @click="next">下一步</a-button></footer>
      </section>
    </a-spin>
  </div>
</template>

<style scoped>
.editor-page { max-width: 1440px; } .editor-shell { display: grid; gap: 20px; padding: 20px; border: 1px solid #f0f0f0; background: #fff; } .stage { min-width: 0; } .basic-stage { max-width: 720px; } .basic-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 16px; } .basic-form :deep(.ant-form-item:last-child) { grid-column: 1 / -1; } .placeholder { min-height: 380px; display: grid; place-items: center; background: #fafafa; } .editor-footer { display: flex; align-items: center; gap: 8px; padding-top: 4px; border-top: 1px solid #f0f0f0; } .footer-fill { flex: 1; }
@media (max-width: 760px) { .editor-page { padding: 0; } .editor-shell { padding: 14px; border-left: 0; border-right: 0; } .basic-form { grid-template-columns: 1fr; } .editor-footer { position: sticky; bottom: 0; padding: 10px 0; background: #fff; } }
</style>
