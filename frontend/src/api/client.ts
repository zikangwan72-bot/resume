import axios, { type InternalAxiosRequestConfig } from 'axios'

import { requestRelogin } from './session'

function resolveApiBaseUrl() {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim()
  const host = window.location.hostname
  if (configured && !['127.0.0.1', 'localhost'].includes(host)) {
    try {
      const url = new URL(configured)
      if (['127.0.0.1', 'localhost'].includes(url.hostname)) return ''
    } catch {
      return configured
    }
  }
  return configured || ''
}

const api = axios.create({
  baseURL: resolveApiBaseUrl(),
  timeout: 12000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('enterprise_ai_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

type RetriableConfig = InternalAxiosRequestConfig & { _reloginRetried?: boolean }

function storedUserEmail(): string | null {
  try {
    return JSON.parse(localStorage.getItem('enterprise_ai_user') || 'null')?.email ?? null
  } catch {
    return null
  }
}

function redirectToLogin() {
  localStorage.removeItem('enterprise_ai_token')
  localStorage.removeItem('enterprise_ai_user')
  if (window.location.pathname !== '/login') window.location.assign('/login')
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status !== 401) return Promise.reject(error)
    const config = error.config as RetriableConfig | undefined
    const email = storedUserEmail()
    const isAuthCall = /\/api\/v1\/auth\/(demo-)?login$/.test(config?.url ?? '')
    // Ask for the password in place (keeping the page and any unsaved form)
    // and retry the request once; otherwise fall back to the login page.
    if (config && email && !isAuthCall && !config._reloginRetried && window.location.pathname !== '/login') {
      try {
        await requestRelogin(email)
      } catch {
        redirectToLogin()
        return Promise.reject(error)
      }
      config._reloginRetried = true
      return api(config)
    }
    if (!isAuthCall) redirectToLogin()
    return Promise.reject(error)
  },
)

export default api
