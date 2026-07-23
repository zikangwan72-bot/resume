<!-- frontend/src/views/approval/ApprovalHome.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PlusOutlined, FileTextOutlined, CheckCircleOutlined, SendOutlined } from '@ant-design/icons-vue'

import api from '@/api/client'
import type { PendingItem } from '@/types'

const router = useRouter()
const pendingCount = ref(0)
const handledCount = ref(0)
const pendingList = ref<PendingItem[]>([])
const loading = ref(true)
const failed = ref(false)

async function load() {
  loading.value = true
  failed.value = false
  try {
    const [pendingRes, handledRes] = await Promise.all([
      api.get('/api/v1/approvals/pending'),
      api.get('/api/v1/approvals/handled'),
    ])
    pendingList.value = (pendingRes.data.data as PendingItem[]).slice(0, 5)
    pendingCount.value = pendingRes.data.data.length
    handledCount.value = handledRes.data.data.length
  } catch { failed.value = true }
  finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div class="page-frame approval-home">
    <header class="page-heading">
      <div>
        <p class="eyebrow">APPROVAL CENTER</p>
        <h1>流程审批中心</h1>
        <p>统一承载企业审批流程，快速发起、高效审批、全程可追溯。</p>
      </div>
    </header>

    <!-- 统计卡片 -->
    <div class="stat-row">
      <a-card class="stat-card" :bordered="false"><FileTextOutlined class="stat-icon" /><a-statistic title="待我审批" :value="pendingCount" /></a-card>
      <a-card class="stat-card" :bordered="false"><CheckCircleOutlined class="stat-icon" /><a-statistic title="我已审批" :value="handledCount" /></a-card>
    </div>

    <!-- 快捷操作 -->
    <a-space class="quick-actions" wrap>
      <a-button type="primary" size="large" @click="router.push('/modules/approval-center/new')">
        <PlusOutlined /> 发起申请
      </a-button>
      <a-button size="large" @click="router.push('/modules/approval-center/requests')">
        <FileTextOutlined /> 我的申请
      </a-button>
      <a-button size="large" @click="router.push('/modules/approval-center/pending')">
        <SendOutlined /> 待我审批
      </a-button>
    </a-space>

    <!-- 待审批列表 -->
    <div class="section-title" style="margin-top:28px;">
      <div><p class="eyebrow">PENDING</p><h2>待我审批</h2></div>
    </div>
    <a-skeleton v-if="loading" active :paragraph="{ rows: 4 }" />
    <a-alert v-else-if="failed" type="error" show-icon message="审批中心加载失败"><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert>
    <a-empty v-else-if="pendingList.length === 0" description="暂无待审批项" />
    <a-list v-else class="record-list" :data-source="pendingList"><template #renderItem="{ item }"><a-list-item><a-button type="link" class="pending-card" @click="router.push(`/modules/approval-center/${item.request.id}`)"><span class="pending-info"><strong>{{ item.request.title }}</strong><small>{{ item.request.applicant_name }} · {{ item.request.created_at.slice(0, 10) }}</small></span><a-tag color="processing">待处理</a-tag></a-button></a-list-item></template></a-list>
  </div>
</template>
