import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import api from '@/api/client'
import type { UserProfile } from '@/types'

const USER_KEY = 'enterprise_ai_user'
const TOKEN_KEY = 'enterprise_ai_token'

export interface DemoAccount {
  email: string
  display_name: string
  department: string
  role: string
}

function storedUser(): UserProfile | null {
  const value = localStorage.getItem(USER_KEY)
  if (!value) return null
  try {
    return JSON.parse(value) as UserProfile
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserProfile | null>(storedUser())
  const loading = ref(false)
  const isAuthenticated = computed(() => Boolean(user.value && localStorage.getItem(TOKEN_KEY)))

  async function demoLogin(role: string) {
    loading.value = true
    try {
      const response = await api.post('/api/v1/auth/demo-login', { role })
      localStorage.setItem(TOKEN_KEY, response.data.data.access_token)
      localStorage.setItem(USER_KEY, JSON.stringify(response.data.data.user))
      user.value = response.data.data.user
    } finally {
      loading.value = false
    }
  }

  async function login(email: string, password: string) {
    loading.value = true
    try {
      const response = await api.post('/api/v1/auth/login', { email, password })
      localStorage.setItem(TOKEN_KEY, response.data.data.access_token)
      localStorage.setItem(USER_KEY, JSON.stringify(response.data.data.user))
      user.value = response.data.data.user
    } finally {
      loading.value = false
    }
  }

  async function fetchDemoAccounts(): Promise<{ password: string; accounts: DemoAccount[] }> {
    const response = await api.get('/api/v1/auth/demo-accounts')
    return response.data.data
  }

  async function refreshMe() {
    if (!localStorage.getItem(TOKEN_KEY)) return
    const response = await api.get('/api/v1/auth/me')
    user.value = response.data.data
    localStorage.setItem(USER_KEY, JSON.stringify(user.value))
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    user.value = null
  }

  function can(permission?: string) {
    return !permission || Boolean(user.value?.permissions.includes(permission))
  }

  return { user, loading, isAuthenticated, demoLogin, login, fetchDemoAccounts, refreshMe, logout, can }
})
