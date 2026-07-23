<!-- frontend/src/views/approval/ApprovalHandled.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/client'
import PageBackButton from '@/components/PageBackButton.vue'

const router = useRouter()
const items = ref<any[]>([])
const loading = ref(true)
const failed = ref(false)

const statusTagMap: Record<string, string> = { approved: 'success', rejected: 'error' }
const statusTextMap: Record<string, string> = { approved: '已通过', rejected: '已驳回' }

async function load() {
  loading.value = true
  failed.value = false
  try {
    const res = await api.get('/api/v1/approvals/handled')
    items.value = res.data.data
  } catch { failed.value = true } finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div>
        <p class="eyebrow">HANDLED</p>
        <h1>我已审批</h1>
        <p>共 {{ items.length }} 条记录</p>
      </div>
      <PageBackButton fallback="/modules/approval-center" />
    </header>

    <a-skeleton v-if="loading" active :paragraph="{ rows: 6 }" />
    <a-alert v-else-if="failed" type="error" show-icon message="已审批记录加载失败"><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert>
    <a-empty v-else-if="items.length === 0" description="暂无已审批记录" />
    <a-list v-else class="record-list" :data-source="items"><template #renderItem="{ item }"><a-list-item><a-button type="link" class="request-card" @click="router.push(`/modules/approval-center/${item.request.id}`)"><span class="request-info"><strong>{{ item.request.title }}</strong><small>{{ item.request.applicant_name }} · {{ item.acted_at?.slice(0, 10) || '' }}</small></span><a-tag :color="statusTagMap[item.node_status]">{{ statusTextMap[item.node_status] || item.node_status }}</a-tag></a-button></a-list-item></template></a-list>
  </div>
</template>
