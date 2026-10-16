import axios from 'axios'

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

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('enterprise_ai_token')
      localStorage.removeItem('enterprise_ai_user')
      if (window.location.pathname !== '/login') window.location.assign('/login')
    }
    return Promise.reject(error)
  },
)

export default api
