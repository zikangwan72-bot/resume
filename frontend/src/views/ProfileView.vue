<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()
const roleLabel: Record<string, string> = { platform_admin: '平台管理员', product_demo_user: '产品演示用户', auditor: '审计查看者' }
</script>

<template>
  <div class="page-frame">
    <header class="page-heading"><div><p class="eyebrow">IDENTITY</p><h1>个人资料</h1><p>当前演示身份和权限摘要。</p></div></header>
    <a-card class="profile-sheet" :bordered="false">
      <div class="profile-content">
        <div class="profile-avatar">{{ auth.user?.display_name.slice(0, 1) }}</div>
        <div class="profile-main"><h2>{{ auth.user?.display_name }}</h2><p>{{ auth.user?.email }}</p></div>
        <dl>
          <div><dt>所属部门</dt><dd>{{ auth.user?.department }}</dd></div>
          <div><dt>当前角色</dt><dd>{{ roleLabel[auth.user?.role || ''] }}</dd></div>
          <div><dt>权限数量</dt><dd>{{ auth.user?.permissions.length }}</dd></div>
          <div><dt>身份来源</dt><dd>Local demo authentication</dd></div>
        </dl>
      </div>
    </a-card>
  </div>
</template>
