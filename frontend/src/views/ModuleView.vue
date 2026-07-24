<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { CheckOutlined, ClockCircleOutlined, SafetyCertificateOutlined } from '@ant-design/icons-vue'

import api from '@/api/client'
import type { ModuleSummary } from '@/types'

const route = useRoute()
const module = ref<ModuleSummary | null>(null)
const loading = ref(true)
const failed = ref(false)
const errorStatus = ref<number | null>(null)
const errorMessage = ref('')

const businessFlows: Record<string, string[]> = {
  'resume-screening': ['创建岗位', '接收简历', '候选人初筛', '人工复核'],
  'approval-center': ['提交申请', '规则校验', '分级审批', '归档追踪'],
  'asset-management': ['资产建档', '领用调拨', '盘点处置', '运营分析'],
  'service-desk': ['问题受理', '知识检索', '工单派发', '解决复盘'],
}

async function load() {
  loading.value = true
  failed.value = false
  errorStatus.value = null
  errorMessage.value = ''
  try {
    const response = await api.get(`/api/v1/modules/${route.params.moduleKey}/summary`)
    module.value = response.data.data
  } catch (error) {
    failed.value = true
    if (axios.isAxiosError(error)) {
      errorStatus.value = error.response?.status ?? null
      const detail = error.response?.data?.detail
      errorMessage.value = typeof detail === 'string' ? detail : detail?.message || error.response?.data?.message || error.message
    } else {
      errorMessage.value = '网络连接异常，请稍后重试。'
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => route.params.moduleKey, load)

const errorTitle = () => {
  if (errorStatus.value === 403) return '无权访问该模块'
  if (errorStatus.value === 404) return '未找到该模块'
  return '模块加载失败'
}

const canRetry = () => errorStatus.value === null || errorStatus.value >= 500
</script>

<template>
  <div class="page-frame module-page">
    <a-skeleton v-if="loading" active :paragraph="{ rows: 10 }" />
    <a-result v-else-if="failed" :status="errorStatus === 403 ? '403' : errorStatus === 404 ? '404' : 'error'" :title="errorTitle()" :sub-title="errorMessage || '请稍后重试。'">
      <template v-if="canRetry()" #extra><a-button type="primary" @click="load">重试</a-button></template>
    </a-result>
    <template v-else-if="module">
      <header class="page-heading">
        <div>
          <p class="eyebrow">MODULE FOUNDATION / {{ module.key.toUpperCase() }}</p>
          <h1>{{ module.name }}</h1>
          <p>{{ module.description }}</p>
        </div>
        <a-tag color="processing"><ClockCircleOutlined /> Foundation only</a-tag>
      </header>

      <a-card class="flow-section" :bordered="false">
        <div class="section-title"><div><p class="eyebrow">BASELINE FLOW</p><h2>基础业务流</h2></div></div>
        <div class="flow-track">
          <template v-for="(step, index) in businessFlows[module.key]" :key="step">
            <div class="flow-step"><span>{{ index + 1 }}</span><strong>{{ step }}</strong></div>
            <div v-if="index < businessFlows[module.key].length - 1" class="flow-line"></div>
          </template>
        </div>
      </a-card>

      <section class="module-columns">
        <a-card class="plain-panel" :bordered="false">
          <div class="panel-kicker"><SafetyCertificateOutlined /> 当前已具备</div>
          <ul class="check-list">
            <li><CheckOutlined />统一登录和角色权限</li>
            <li><CheckOutlined />模块路由与后端接口</li>
            <li><CheckOutlined />操作审计与请求追踪</li>
            <li><CheckOutlined />AI运行记录公共结构</li>
          </ul>
        </a-card>
        <a-card class="plain-panel ai-panel" :bordered="false">
          <div class="panel-kicker">计划AI能力</div>
          <div class="capability-list">
            <span v-for="(item, index) in module.planned_ai" :key="item"><b>0{{ index + 1 }}</b>{{ item }}</span>
          </div>
        </a-card>
      </section>

      <a-alert type="info" show-icon :message="module.message" description="下一阶段将先完善基础业务闭环，再逐步接入AI能力。" />
    </template>
  </div>
</template>
