<!-- frontend/src/views/approval/ApprovalHandled.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/client'
import PageBackButton from '@/components/PageBackButton.vue'

const router = useRouter()
const items = ref<any[]>([])
const loading = ref(true)

const statusTagMap: Record<string, string> = { approved: 'success', rejected: 'error' }
const statusTextMap: Record<string, string> = { approved: '已通过', rejected: '已驳回' }

onMounted(async () => {
  try {
    const res = await api.get('/api/v1/approvals/handled')
    items.value = res.data.data
  } finally { loading.value = false }
})
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
    <a-empty v-else-if="items.length === 0" description="暂无已审批记录" />
    <a-list v-else class="record-list" :data-source="items"><template #renderItem="{ item }"><a-list-item class="request-card" @click="router.push(`/modules/approval-center/${item.request.id}`)"><a-list-item-meta :title="item.request.title" :description="`${item.request.applicant_name} · ${item.acted_at?.slice(0, 10) || ''}`" /><a-tag :color="statusTagMap[item.node_status]">{{ statusTextMap[item.node_status] || item.node_status }}</a-tag></a-list-item></template></a-list>
  </div>
</template>
