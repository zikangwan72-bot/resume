<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { BellOutlined } from '@ant-design/icons-vue'

import api from '@/api/client'

interface NotificationItem { id: number; title: string; content: string; category: string; read_at: string | null; created_at: string }
const items = ref<NotificationItem[]>([])
const loading = ref(true)
const failed = ref(false)

async function load() {
  loading.value = true
  failed.value = false
  try {
    const response = await api.get('/api/v1/notifications')
    items.value = response.data.data
  } catch { failed.value = true } finally { loading.value = false }
}

async function markRead(item: NotificationItem) {
  if (item.read_at) return
  await api.patch(`/api/v1/notifications/${item.id}/read`)
  await load()
}

onMounted(load)
</script>

<template>
  <div class="page-frame">
    <header class="page-heading"><div><p class="eyebrow">INBOX</p><h1>通知中心</h1><p>查看平台配置、交付与运行状态。</p></div></header>
    <a-spin :spinning="loading">
      <a-alert v-if="failed" type="error" show-icon message="通知加载失败"><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert>
      <a-list v-else-if="items.length" class="record-list" item-layout="horizontal" :data-source="items">
        <template #renderItem="{ item }"><a-list-item class="record-row" :class="{ unread: !item.read_at }" @click="markRead(item)"><a-list-item-meta :description="item.content"><template #title>{{ item.title }}</template><template #avatar><BellOutlined class="record-icon" /></template></a-list-item-meta><span class="record-meta">{{ item.read_at ? '已读' : '标记已读' }}</span></a-list-item></template>
      </a-list>
      <a-empty v-else description="暂无通知" />
    </a-spin>
  </div>
</template>
