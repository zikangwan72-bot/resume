<script setup lang="ts">
import { ref, watch } from 'vue'
import { isAxiosError } from 'axios'

import { finishRelogin, reloginState } from '@/api/session'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const password = ref('')
const error = ref('')
const submitting = ref(false)

watch(
  () => reloginState.visible,
  (visible) => {
    if (visible) {
      password.value = ''
      error.value = ''
    }
  },
)

async function submit() {
  if (!password.value) {
    error.value = '请输入密码。'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    await auth.login(reloginState.email, password.value)
    finishRelogin(true)
  } catch (err) {
    if (isAxiosError(err) && err.response?.status === 429) {
      error.value = '登录失败次数过多，请稍后再试。'
    } else if (isAxiosError(err) && err.response?.status === 401) {
      error.value = '密码不正确。'
    } else {
      error.value = '登录失败，请确认后端服务已启动。'
    }
  } finally {
    submitting.value = false
  }
}

function switchAccount() {
  finishRelogin(false)
}
</script>

<template>
  <a-modal
    :open="reloginState.visible"
    title="登录已过期"
    :closable="false"
    :mask-closable="false"
    :keyboard="false"
    :confirm-loading="submitting"
    ok-text="重新登录"
    cancel-text="切换账号"
    @ok="submit"
    @cancel="switchAccount"
  >
    <p class="relogin-hint">请重新输入密码。登录后会继续刚才的操作，当前页面填写的内容不会丢失。</p>
    <a-form layout="vertical" @submit.prevent="submit">
      <a-form-item label="账号">
        <a-input :value="reloginState.email" disabled />
      </a-form-item>
      <a-form-item label="密码" :validate-status="error ? 'error' : ''" :help="error || undefined">
        <a-input-password
          v-model:value="password"
          autocomplete="current-password"
          placeholder="密码"
          @press-enter="submit"
        />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.relogin-hint {
  margin-bottom: 16px;
  color: rgba(0, 0, 0, 0.65);
}
</style>
