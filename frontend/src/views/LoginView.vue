<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { LockOutlined, SafetyCertificateOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const selectedRole = ref('platform_admin')

const roles = [
  { key: 'platform_admin', name: '平台管理员', detail: '查看四个模块与全部治理页面' },
  { key: 'product_demo_user', name: '产品演示用户', detail: '查看四个业务模块和通知' },
  { key: 'auditor', name: '审计查看者', detail: '只读查看审计和AI运行记录' },
]

async function login() {
  try {
    await auth.demoLogin(selectedRole.value)
    await router.push('/dashboard')
  } catch {
    message.error('后端服务暂时不可用，请确认FastAPI已经启动。')
  }
}
</script>

<template>
  <main class="login-page">
    <div class="login-box">
      <div class="login-brand"><span>EA</span> Enterprise AI Suite</div>
      <a-card>
        <div class="login-heading">
          <span class="security-icon"><SafetyCertificateOutlined /></span>
          <div>
            <h1>企业AI工作流平台</h1>
            <p>选择角色验证菜单与权限边界</p>
          </div>
        </div>

        <div class="role-options">
          <button
            v-for="role in roles"
            :key="role.key"
            class="role-option"
            :class="{ active: selectedRole === role.key }"
            @click="selectedRole = role.key"
          >
            <span class="radio-indicator"></span>
            <span><strong>{{ role.name }}</strong><small>{{ role.detail }}</small></span>
          </button>
        </div>

        <a-button type="primary" block size="large" :loading="auth.loading" @click="login">
          <LockOutlined /> 安全进入
        </a-button>
        <p class="login-note">当前为本地演示登录。接入Supabase Auth后将切换为邮箱身份验证。</p>
      </a-card>
    </div>
  </main>
</template>
