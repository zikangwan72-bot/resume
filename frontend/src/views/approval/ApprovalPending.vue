<!-- frontend/src/views/approval/ApprovalPending.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import api from '@/api/client'
import PageBackButton from '@/components/PageBackButton.vue'
import type { PendingItem } from '@/types'

const router = useRouter()
const items = ref<PendingItem[]>([])
const loading = ref(true)
const failed = ref(false)

async function load() {
  loading.value = true
  failed.value = false
  try {
    const res = await api.get('/api/v1/approvals/pending')
    items.value = res.data.data
  } catch { failed.value = true } finally { loading.value = false }
}

onMounted(load)

async function quickApprove(item: PendingItem) {
  try {
    await api.post(`/api/v1/approvals/nodes/${item.node_id}/approve`, { comment: '同意' })
    message.success('已审批通过')
    items.value = items.value.filter(i => i.node_id !== item.node_id)
  } catch { message.error('操作失败') }
}

async function quickReject(item: PendingItem) {
  try {
    await api.post(`/api/v1/approvals/nodes/${item.node_id}/reject`, { comment: '不同意' })
    message.success('已驳回')
    items.value = items.value.filter(i => i.node_id !== item.node_id)
  } catch { message.error('操作失败') }
}
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div>
        <p class="eyebrow">PENDING APPROVAL</p>
        <h1>待我审批</h1>
        <p>共 {{ items.length }} 项待处理</p>
      </div>
      <PageBackButton fallback="/modules/approval-center" />
    </header>

    <a-skeleton v-if="loading" active :paragraph="{ rows: 6 }" />
    <a-alert v-else-if="failed" type="error" show-icon message="待审批列表加载失败"><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert>
    <a-empty v-else-if="items.length === 0" description="没有待审批项" />
    <a-list v-else class="record-list" :data-source="items"><template #renderItem="{ item }"><a-list-item class="pending-card-full">
        <a-button type="link" class="pending-main" @click="router.push(`/modules/approval-center/${item.request.id}`)"><strong>{{ item.request.title }}</strong><small>{{ item.request.applicant_name }} · {{ item.request.created_at.slice(0, 10) }}</small></a-button>
        <div class="pending-actions">
          <a-button size="small" type="primary" @click="quickApprove(item)"><CheckCircleOutlined /> 同意</a-button>
          <a-button size="small" danger @click="quickReject(item)"><CloseCircleOutlined /> 驳回</a-button>
        </div>
    </a-list-item></template></a-list>
  </div>
</template>
