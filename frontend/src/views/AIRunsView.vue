<script setup lang="ts">
import { onMounted, ref } from 'vue'
import api from '@/api/client'

const rows = ref([])
const loading = ref(true)
const failed = ref(false)
const columns = [
  { title: '模块', dataIndex: 'module' },
  { title: '任务类型', dataIndex: 'task_type' },
  { title: '模型', dataIndex: 'model' },
  { title: '状态', dataIndex: 'status' },
  { title: '延迟(ms)', dataIndex: 'latency_ms' },
  { title: '人工复核', dataIndex: 'human_review' },
  { title: '时间', dataIndex: 'created_at' },
]
async function load() { loading.value = true; failed.value = false; try { const response = await api.get('/api/v1/ai-runs'); rows.value = response.data.data } catch { failed.value = true } finally { loading.value = false } }
onMounted(load)
</script>

<template>
  <div class="page-frame">
    <header class="page-heading"><div><p class="eyebrow">AI GOVERNANCE</p><h1>AI运行记录</h1><p>统一记录模型、任务、成本、延迟与人工复核状态。</p></div></header>
    <a-alert type="warning" show-icon message="模型服务尚未配置" description="当前只建立治理结构，不会发送真实模型请求。" class="page-alert" />
    <a-alert v-if="failed" class="page-alert" type="error" show-icon message="运行记录加载失败"><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert>
    <a-table v-else :columns="columns" :data-source="rows" :loading="loading" row-key="id" :scroll="{ x: 840 }" class="data-table">
      <template #bodyCell="{ column, record }">
        <a-tag v-if="column.dataIndex === 'status'">{{ record.status }}</a-tag>
        <span v-else-if="column.dataIndex === 'human_review'">{{ record.human_review ? '需要' : '不需要' }}</span>
      </template>
    </a-table>
  </div>
</template>
