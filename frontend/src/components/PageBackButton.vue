<script setup lang="ts">
import { LeftOutlined } from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'

const props = withDefaults(defineProps<{ fallback?: string; label?: string }>(), {
  fallback: '/dashboard',
  label: '返回',
})

const router = useRouter()

function goBack() {
  if (window.history.length > 1) {
    router.back()
    return
  }
  router.push(props.fallback)
}
</script>

<template>
  <a-button class="page-back-button" @click="goBack">
    <LeftOutlined />
    {{ label }}
  </a-button>
</template>
