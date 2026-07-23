<script setup lang="ts">
import type { ProcessAppStatus } from '@/types/approval'

defineProps<{ status: ProcessAppStatus }>()

const labels: Record<ProcessAppStatus, string> = {
  draft: '草稿',
  published: '已发布',
  inactive: '已停用',
}

const colors: Record<ProcessAppStatus, string> = {
  draft: 'warning',
  published: 'success',
  inactive: 'default',
}
</script>

<template>
  <a-tag :color="colors[status]">{{ labels[status] }}</a-tag>
</template>
