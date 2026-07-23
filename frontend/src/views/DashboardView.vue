<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRightOutlined,
  CheckCircleFilled,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  RobotOutlined,
} from '@ant-design/icons-vue'

import api from '@/api/client'
import type { HealthStatus, ModuleSummary } from '@/types'

const router = useRouter()
const modules = ref<ModuleSummary[]>([])
const health = ref<HealthStatus | null>(null)
const loading = ref(true)
const failed = ref(false)

const configuredCount = computed(() =>
  health.value ? [health.value.database, health.value.supabase, health.value.ai].filter((v) => v === 'configured' || v === 'local').length : 0,
)

async function load() {
  loading.value = true
  failed.value = false
  try {
    const [moduleResponse, healthResponse] = await Promise.all([
      api.get('/api/v1/modules'),
      api.get('/api/v1/health'),
    ])
    modules.value = moduleResponse.data.data
    health.value = healthResponse.data.data
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-frame">
    <header class="page-heading dashboard-heading">
      <div>
        <p class="eyebrow">平台概览</p>
        <h1>工作台</h1>
        <p>四个企业AI项目共享同一套身份、权限、数据和治理基础。</p>
      </div>
      <div class="heading-actions"><a-button type="primary" @click="router.push('/modules/approval-center')"><CheckCircleFilled />进入审批中心</a-button></div>
    </header>

    <a-alert v-if="failed" type="error" show-icon message="无法连接后端服务" description="请启动FastAPI后重试。" class="page-alert">
      <template #action><a-button size="small" @click="load">重新连接</a-button></template>
    </a-alert>

    <a-skeleton v-if="loading" active :paragraph="{ rows: 8 }" />

    <template v-else-if="!failed">
      <section class="module-grid" aria-label="业务模块">
        <a-card v-for="(item, index) in modules" :key="item.key" class="module-card" :bordered="false">
          <div class="module-status"><span></span>业务模块 <span class="module-index">0{{ index + 1 }}</span></div>
          <h2>{{ item.name }}</h2>
          <p>{{ item.description }}</p>
          <div class="ai-tags">
            <a-tag v-for="tag in item.planned_ai" :key="tag">{{ tag }}</a-tag>
          </div>
          <a-button type="link" class="module-link" @click="router.push(`/modules/${item.key}`)">查看模块 <ArrowRightOutlined /></a-button>
        </a-card>
      </section>

      <a-card class="operations-band" :bordered="false">
        <div class="section-title">
          <div><p class="eyebrow">PLATFORM READINESS</p><h2>基础设施状态</h2></div>
          <span>{{ configuredCount }}/3 已就绪</span>
        </div>
        <div class="status-list">
          <div class="status-row">
            <DatabaseOutlined />
            <span><strong>业务数据库</strong><small>SQLAlchemy统一数据访问层</small></span>
            <a-tag color="green">本地SQLite运行中</a-tag>
          </div>
          <div class="status-row">
            <CloudServerOutlined />
            <span><strong>Supabase云服务</strong><small>PostgreSQL / Auth / Storage</small></span>
            <a-tag>{{ health?.supabase === 'configured' ? '已配置' : '等待配置' }}</a-tag>
          </div>
          <div class="status-row">
            <RobotOutlined />
            <span><strong>模型服务</strong><small>RAG、Copilot与Agent统一入口</small></span>
            <a-tag>{{ health?.ai === 'configured' ? '已配置' : '暂未启用' }}</a-tag>
          </div>
          <div class="status-row">
            <CodeOutlined />
            <span><strong>FastAPI接口</strong><small>鉴权、权限与请求追踪</small></span>
            <a-tag color="green">正常</a-tag>
          </div>
        </div>
      </a-card>
    </template>
  </div>
</template>
