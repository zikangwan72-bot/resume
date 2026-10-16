<script setup lang="ts">
import zhCN from 'ant-design-vue/es/locale/zh_CN'

import ReloginModal from '@/components/ReloginModal.vue'

const theme = {
  token: {
    colorPrimary: '#1677ff',
    colorBgLayout: '#f5f5f5',
    borderRadius: 6,
    fontFamily: '"Segoe UI", "Microsoft YaHei", sans-serif',
  },
}
</script>

<template>
  <a-config-provider :locale="zhCN" :theme="theme">
    <router-view />
    <ReloginModal />
  </a-config-provider>
</template>
