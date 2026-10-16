<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { LockOutlined, MailOutlined, SafetyCertificateOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import { useAuthStore } from '@/stores/auth'
import type { DemoAccount } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const email = ref('admin@demo.local')
const password = ref('Demo@2026!')
const demoPassword = ref('Demo@2026!')
const selectedEmail = ref('admin@demo.local')
const showDemoAccounts = import.meta.env.DEV || import.meta.env.VITE_DEMO_MODE === 'true'

const roleLabel: Record<string, string> = {
  platform_admin: '平台管理员',
  recruitment_admin: '招聘管理员',
  asset_admin: '资产管理员',
  department_manager: '部门经理',
  approval_finance: '财务审批',
  it_support: 'IT运维',
  employee: '员工',
}

const fallbackAccounts: DemoAccount[] = [
  { email: 'admin@demo.local', display_name: '平台管理员', department: '企业数字化中心', role: 'platform_admin' },
  { email: 'owner@demo.local', display_name: '平台负责人', department: '企业数字化中心', role: 'platform_admin' },
  { email: 'recruit01@demo.local', display_name: '招聘负责人', department: '人才发展部', role: 'recruitment_admin' },
  { email: 'recruit02@demo.local', display_name: '校招运营', department: '人才发展部', role: 'recruitment_admin' },
  { email: 'recruit03@demo.local', display_name: '用人协同HR', department: '人力资源部', role: 'recruitment_admin' },
  { email: 'asset01@demo.local', display_name: '资产管理员A', department: '行政资产组', role: 'asset_admin' },
  { email: 'asset02@demo.local', display_name: '区域资产专员', department: '深圳行政资产组', role: 'asset_admin' },
  { email: 'asset03@demo.local', display_name: 'IT资产专员', department: '信息技术部', role: 'asset_admin' },
  { email: 'it01@demo.local', display_name: 'IT运维工程师', department: '信息技术部', role: 'it_support' },
  { email: 'it02@demo.local', display_name: 'IT桌面支持', department: '信息技术部', role: 'it_support' },
  { email: 'manager01@demo.local', display_name: '产品研发经理', department: '产品与流程创新', role: 'department_manager' },
  { email: 'manager02@demo.local', display_name: '数据平台经理', department: '数据平台组', role: 'department_manager' },
  { email: 'manager03@demo.local', display_name: '质量检测经理', department: '质量检测部', role: 'department_manager' },
  { email: 'manager04@demo.local', display_name: '流程创新经理', department: '流程创新中心', role: 'department_manager' },
  { email: 'finance01@demo.local', display_name: '财务审批A', department: '财务管理部', role: 'approval_finance' },
  { email: 'finance02@demo.local', display_name: '财务审批B', department: '财务管理部', role: 'approval_finance' },
  { email: 'finance03@demo.local', display_name: '区域财务', department: '区域财务组', role: 'approval_finance' },
  { email: 'employee01@demo.local', display_name: '员工一', department: '产品研发部', role: 'employee' },
  { email: 'employee02@demo.local', display_name: '员工二', department: '数据平台组', role: 'employee' },
  { email: 'employee03@demo.local', display_name: '员工三', department: '质量检测部', role: 'employee' },
  { email: 'employee04@demo.local', display_name: '员工四', department: '行政资产组', role: 'employee' },
  { email: 'employee05@demo.local', display_name: '员工五', department: '流程创新中心', role: 'employee' },
]
const accounts = ref<DemoAccount[]>(fallbackAccounts)

function pickAccount(account: DemoAccount) {
  selectedEmail.value = account.email
  email.value = account.email
  password.value = demoPassword.value
}

async function login() {
  if (!email.value || !password.value) {
    message.warning('请输入邮箱和密码。')
    return
  }
  try {
    await auth.login(email.value, password.value)
    const redirect = localStorage.getItem('enterprise_ai_post_login_redirect')
    localStorage.removeItem('enterprise_ai_post_login_redirect')
    await router.push(redirect || '/dashboard')
  } catch {
    message.error('登录失败，请检查账号密码或确认FastAPI已经启动。')
  }
}

onMounted(async () => {
  try {
    const payload = await auth.fetchDemoAccounts()
    demoPassword.value = payload.password
    accounts.value = payload.accounts
    password.value = payload.password
  } catch {
    accounts.value = fallbackAccounts
  }
})
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
            <p>选择试用账号进入对应角色工作台</p>
          </div>
        </div>

        <a-form layout="vertical" class="login-form" @submit.prevent="login">
          <a-form-item label="邮箱">
            <a-input v-model:value="email" size="large" autocomplete="username">
              <template #prefix><MailOutlined /></template>
            </a-input>
          </a-form-item>
          <a-form-item label="密码">
            <a-input-password v-model:value="password" size="large" autocomplete="current-password">
              <template #prefix><LockOutlined /></template>
            </a-input-password>
          </a-form-item>
        </a-form>

        <div v-if="showDemoAccounts" class="demo-password">统一试用密码：<strong>{{ demoPassword }}</strong></div>

        <div v-if="showDemoAccounts" class="role-options trial-accounts">
          <button
            v-for="account in accounts"
            :key="account.email"
            class="role-option"
            :class="{ active: selectedEmail === account.email }"
            @click="pickAccount(account)"
          >
            <span class="radio-indicator"></span>
            <span>
              <strong>{{ account.display_name }} · {{ roleLabel[account.role] }}</strong>
              <small>{{ account.email }} / {{ account.department }}</small>
            </span>
          </button>
        </div>

        <a-button type="primary" block size="large" :loading="auth.loading" @click="login">
          <LockOutlined /> 安全进入
        </a-button>
        <p class="login-note">{{ showDemoAccounts ? '当前为本地邮箱密码登录。' : '请输入企业账号登录。' }} AI 结果不会自动录用或淘汰候选人。</p>
      </a-card>
    </div>
  </main>
</template>
