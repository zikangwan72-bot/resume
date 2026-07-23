<script setup lang="ts">
import { onMounted, ref } from 'vue'
import api from '@/api/client'

const rows = ref([])
const loading = ref(true)
const failed = ref(false)
const columns = [
  { title: '操作者', dataIndex: 'actor_name' },
  { title: '动作', dataIndex: 'action' },
  { title: '资源', dataIndex: 'resource' },
  { title: '结果', dataIndex: 'result' },
  { title: '请求ID', dataIndex: 'request_id', ellipsis: true },
  { title: '时间', dataIndex: 'created_at' },
]
async function load() { loading.value = true; failed.value = false; try { const response = await api.get('/api/v1/audit-logs'); rows.value = response.data.data } catch { failed.value = true } finally { loading.value = false } }
onMounted(load)
</script>

<template>
  <div class="page-frame">
    <header class="page-heading"><div><p class="eyebrow">GOVERNANCE</p><h1>审计日志</h1><p>追踪关键操作、资源和请求ID。</p></div></header>
    <a-alert v-if="failed" class="page-alert" type="error" show-icon message="审计日志加载失败"><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert>
    <a-table v-else :columns="columns" :data-source="rows" :loading="loading" row-key="id" :scroll="{ x: 800 }" class="data-table" />
  </div>
</template>
