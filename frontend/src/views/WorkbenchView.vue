<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRightOutlined, CheckCircleOutlined, CloudServerOutlined, CodeOutlined, DatabaseOutlined, RobotOutlined } from '@ant-design/icons-vue'
import api from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { HealthStatus, ModuleSummary } from '@/types'

const router = useRouter()
const auth = useAuthStore()
const modules = ref<ModuleSummary[]>([])
const health = ref<HealthStatus | null>(null)
const loading = ref(true)
const failed = ref(false)

const moduleCopy: Record<string, { name: string; description: string }> = {
  'resume-screening': { name: 'AI 简历筛选', description: '配置岗位标准，上传简历并完成人工复核。' },
  'approval-center': { name: '流程审批中心', description: '发起、处理和管理企业审批流程。' },
}
const routeFor = (key: string) => `/modules/${key}`
const displayName = (item: ModuleSummary) => moduleCopy[item.key]?.name || item.name
const displayDescription = (item: ModuleSummary) => moduleCopy[item.key]?.description || item.description
const readyCount = computed(() => health.value ? [health.value.database, health.value.supabase, health.value.ai].filter((value) => value === 'configured' || value === 'local' || value === 'postgresql').length : 0)

async function load() {
  loading.value = true
  failed.value = false
  try {
    const moduleResponse = await api.get('/api/v1/modules')
    modules.value = moduleResponse.data.data || []
    loading.value = false
    try {
      const healthResponse = await api.get('/api/v1/health')
      health.value = healthResponse.data.data || null
    } catch {
      health.value = null
    }
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-frame workbench-page">
    <header class="page-heading">
      <div><p class="eyebrow">WORKBENCH</p><h1>工作台</h1><p>按当前账号权限进入业务模块与管理功能。</p></div>
      <div v-if="auth.can('approval:view')" class="heading-actions"><a-button type="primary" @click="router.push('/modules/approval-center')"><CheckCircleOutlined />进入审批中心</a-button></div>
    </header>

    <a-alert v-if="failed" type="error" show-icon message="工作台加载失败" description="请检查后端服务后重试。" class="page-alert"><template #action><a-button size="small" @click="load">重新加载</a-button></template></a-alert>
    <a-skeleton v-if="loading" active :paragraph="{ rows: 8 }" />

    <template v-else-if="!failed">
      <section class="module-grid" aria-label="业务模块">
        <a-card v-for="(item, index) in modules" :key="item.key" class="module-card" :bordered="false">
          <div class="module-status"><span />可用模块 <span class="module-index">{{ String(index + 1).padStart(2, '0') }}</span></div>
          <h2>{{ displayName(item) }}</h2>
          <p>{{ displayDescription(item) }}</p>
          <div class="ai-tags"><a-tag v-for="tag in item.planned_ai" :key="tag">{{ tag }}</a-tag></div>
          <a-button type="link" class="module-link" :aria-label="`进入${displayName(item)}`" @click="router.push(routeFor(item.key))">进入模块 <ArrowRightOutlined /></a-button>
        </a-card>
      </section>

      <section class="operations-band">
        <div class="section-title"><div><p class="eyebrow">PLATFORM STATUS</p><h2>平台状态</h2></div><span>{{ readyCount }}/3 已就绪</span></div>
        <div class="status-list">
          <div class="status-row"><DatabaseOutlined /><span><strong>业务数据库</strong><small>统一业务数据与权限</small></span><a-tag color="green">正常</a-tag></div>
          <div class="status-row"><CloudServerOutlined /><span><strong>Supabase</strong><small>数据库、认证与文件存储</small></span><a-tag :color="health?.supabase === 'configured' ? 'green' : undefined">{{ health?.supabase === 'configured' ? '已配置' : '待配置' }}</a-tag></div>
          <div class="status-row"><RobotOutlined /><span><strong>AI 服务</strong><small>筛选、RAG 与 Agent 能力</small></span><a-tag>{{ health?.ai === 'configured' ? '已配置' : '暂未启用' }}</a-tag></div>
          <div class="status-row"><CodeOutlined /><span><strong>FastAPI</strong><small>接口、鉴权与审计</small></span><a-tag color="green">正常</a-tag></div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.workbench-page { max-width: 1280px; }
</style>
