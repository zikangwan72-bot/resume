<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import api from '@/api/client'
import DynamicApprovalForm from '@/components/approval/DynamicApprovalForm.vue'
import PageBackButton from '@/components/PageBackButton.vue'
import { useAuthStore } from '@/stores/auth'
import type { ProcessApp } from '@/types/approval'

const router = useRouter(); const auth = useAuthStore()
const apps = ref<ProcessApp[]>([]); const selectedApp = ref<ProcessApp | null>(null); const values = ref<Record<string, any>>({}); const form = ref<InstanceType<typeof DynamicApprovalForm>>(); const submitting = ref(false); const submitError = ref(''); const idempotencyKey = ref('')
const activeApps = computed(() => apps.value.filter(app => app.status === 'published' && app.version_status === 'published'))
function freshKey() { return globalThis.crypto?.randomUUID?.() || `request-${Date.now()}-${Math.random().toString(36).slice(2)}` }
function selectApp(app: ProcessApp) { selectedApp.value = app; values.value = {}; idempotencyKey.value = freshKey(); submitError.value = '' }
onMounted(async () => { try { apps.value = (await api.get('/api/v1/approvals/apps')).data.data } catch (error) { message.error(errorMessage(error, '流程应用加载失败')) } })
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
    <header class="page-heading"><div><p class="eyebrow">NEW REQUEST</p><h1>发起申请</h1></div><PageBackButton fallback="/modules/approval-center" /></header>
    <section><div class="section-title"><div><p class="eyebrow">STEP 1</p><h2>选择流程应用</h2></div></div><div class="type-cards"><button v-for="app in activeApps" :key="app.id" type="button" class="type-card" :class="{ active: selectedApp?.id === app.id }" @click="selectApp(app)"><strong>{{ app.name }}</strong><small>{{ app.description || app.category }}</small><span>v{{ app.version_number }}</span></button></div><a-empty v-if="!activeApps.length" description="暂无可发起的已发布流程" /></section>
    <section v-if="selectedApp" class="request-form"><div class="section-title"><div><p class="eyebrow">STEP 2</p><h2>填写申请</h2></div></div><DynamicApprovalForm ref="form" v-model="values" :schema="selectedApp.form_schema" :applicant="auth.user" /><a-alert v-if="submitError" type="error" show-icon :message="submitError" style="margin-bottom:16px" /><a-space wrap><a-button type="primary" size="large" :loading="submitting" @click="submit">提交申请</a-button><a-button size="large" @click="router.back()">取消</a-button></a-space></section>
  </div>
</template>

<style scoped>
.type-cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:12px; } .type-card { text-align:left; border:1px solid #d9e2e8; border-radius:6px; background:#fff; padding:16px; cursor:pointer; color:#182b35; } .type-card.active { border-color:#147d89; box-shadow:inset 3px 0 #147d89; } .type-card strong,.type-card small,.type-card span { display:block; } .type-card small { color:#687780; margin:6px 0; } .type-card span { color:#147d89; font-size:12px; } .request-form { margin-top:28px; max-width:980px; } @media (max-width: 600px) { .type-cards { grid-template-columns:1fr; } }
</style>
