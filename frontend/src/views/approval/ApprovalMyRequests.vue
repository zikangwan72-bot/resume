<!-- frontend/src/views/approval/ApprovalMyRequests.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PlusOutlined } from '@ant-design/icons-vue'
import api from '@/api/client'
import PageBackButton from '@/components/PageBackButton.vue'
import type { ApprovalRequestDetail } from '@/types'

const router = useRouter()
const requests = ref<ApprovalRequestDetail[]>([])
const loading = ref(true)
const failed = ref(false)
const statusFilter = ref<string | undefined>(undefined)

const statusTagMap: Record<string, string> = { pending: 'processing', approved: 'success', rejected: 'error', revoked: 'default' }
const statusTextMap: Record<string, string> = { pending: '审批中', approved: '已通过', rejected: '已驳回', revoked: '已撤回' }

async function load() {
  loading.value = true
  failed.value = false
  try {
    const config = statusFilter.value ? { params: { status: statusFilter.value } } : {}
    const res = await api.get('/api/v1/approvals/requests', config)
    requests.value = res.data.data
  } catch { failed.value = true } finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div>
        <p class="eyebrow">MY REQUESTS</p>
        <h1>我的申请</h1>
      </div>
      <div class="heading-actions">
        <PageBackButton fallback="/modules/approval-center" />
        <a-button type="primary" @click="router.push('/modules/approval-center/new')"><PlusOutlined /> 发起申请</a-button>
      </div>
    </header>

    <a-radio-group v-model:value="statusFilter" @change="load" button-style="solid" size="small" style="margin-bottom:16px;">
      <a-radio-button :value="undefined">全部</a-radio-button>
      <a-radio-button value="pending">审批中</a-radio-button>
      <a-radio-button value="approved">已通过</a-radio-button>
      <a-radio-button value="rejected">已驳回</a-radio-button>
    </a-radio-group>

    <a-skeleton v-if="loading" active :paragraph="{ rows: 6 }" />
    <a-alert v-else-if="failed" type="error" show-icon message="申请记录加载失败"><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert>
    <a-empty v-else-if="requests.length === 0" description="暂无申请记录" />
    <a-list v-else class="record-list" :data-source="requests"><template #renderItem="{ item }"><a-list-item><a-button type="link" class="request-card" @click="router.push(`/modules/approval-center/${item.id}`)"><span class="request-info"><strong>{{ item.title }}</strong><small>{{ item.created_at.slice(0, 16).replace('T', ' ') }}</small></span><a-tag :color="statusTagMap[item.status]">{{ statusTextMap[item.status] }}</a-tag></a-button></a-list-item></template></a-list>
  </div>
</template>

<style scoped>
.request-card { width:100%; align-items:flex-start; text-align:left; }
</style>
