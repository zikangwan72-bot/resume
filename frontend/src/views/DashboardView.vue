<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { FileSearchOutlined, InboxOutlined, UploadOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import api from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const jobs = ref<any[]>([])
const results = ref<any[]>([])
const dashboard = ref<any>({})
const loading = ref(true)
const uploadBusy = ref(false)
const selectedJob = ref<string | undefined>()
const files = ref<File[]>([])
const uploadResults = ref<{ name: string; status: 'processing' | 'success' | 'error'; detail: string }[]>([])
const resultFilter = ref<'all' | 'pending' | 'reviewed'>('pending')
const resultSection = ref<HTMLElement | null>(null)
const allowed = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
const canManage = computed(() => auth.can('resume:manage'))

const metric = computed(() => ({ jobs: dashboard.value.job_count ?? dashboard.value.jobs_count ?? jobs.value.filter((j) => j.status !== 'inactive' && j.status !== '停用').length, resumes: dashboard.value.resume_count ?? dashboard.value.resumes_count ?? results.value.length, pending: dashboard.value.pending_count ?? results.value.filter((r) => ['pending', '待复核', 'pending_review'].includes(r.human_status || r.status)).length, reviewed: dashboard.value.reviewed_count ?? results.value.filter((r) => r.human_status && !['pending', '待复核', 'pending_review'].includes(r.human_status)).length }))
const jobDistribution = computed(() => dashboard.value.job_distribution || dashboard.value.by_job || jobs.value.map((job) => ({ ...job, count: results.value.filter((r) => r.job_id === job.id).length })))
const filteredResults = computed(() => {
  if (resultFilter.value === 'pending') return results.value.filter((r) => !r.human_status || ['pending', '待复核', 'pending_review'].includes(r.human_status))
  if (resultFilter.value === 'reviewed') return results.value.filter((r) => ['approved', 'rejected', 'needs_follow_up'].includes(r.human_status))
  return results.value
})

async function load() {
  loading.value = true
  try {
    const response = await api.get('/api/v1/screening/overview')
    dashboard.value = response.data.data.summary || {}
    jobs.value = response.data.data.jobs || []
    const allResults = await api.get('/api/v1/screening/results')
    results.value = allResults.data.data || response.data.data.pending_results || []
  } catch (error: any) { message.error(error.response?.data?.detail || '筛选看板加载失败') } finally { loading.value = false }
}

function removeFile(file: File) {
  files.value = files.value.filter((item) => item !== file)
}

function focusResults(filter: 'all' | 'pending' | 'reviewed') {
  resultFilter.value = filter
  resultSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const picked = Array.from(input.files || [])
  const existingKeys = new Set(files.value.map((file) => `${file.name}:${file.size}:${file.lastModified}`))
  const added = picked.filter((file) => {
    const key = `${file.name}:${file.size}:${file.lastModified}`
    if (existingKeys.has(key)) return false
    existingKeys.add(key)
    return true
  })
  const invalid = added.filter((file) => !allowed.includes(file.type) && !/\.(pdf|docx)$/i.test(file.name))
  const invalidKeys = new Set(invalid.map((file) => `${file.name}:${file.size}:${file.lastModified}`))
  uploadResults.value = [
    ...uploadResults.value,
    ...invalid.map((file) => ({ name: file.name, status: 'error' as const, detail: '仅支持 PDF、DOCX' })),
  ]
  files.value = [...files.value, ...added.filter((file) => !invalidKeys.has(`${file.name}:${file.size}:${file.lastModified}`))]
  input.value = ''
}

async function uploadFiles() {
  if (!selectedJob.value) return message.warning('请先选择岗位标准')
  if (!files.value.length) return message.warning('请选择简历文件')
  uploadBusy.value = true
  const pendingFiles = [...files.value]
  const completedResultIds: Array<number | undefined> = new Array(pendingFiles.length)
  uploadResults.value = pendingFiles.map((file) => ({ name: file.name, status: 'processing', detail: '分析中' }))
  let nextIndex = 0
  async function worker() {
    while (nextIndex < pendingFiles.length) {
      const index = nextIndex++
      const file = pendingFiles[index]
      try {
        const form = new FormData(); form.append('file', file); form.append('job_id', selectedJob.value as string)
        const uploaded = await api.post('/api/v1/screening/resumes', form, { headers: { 'Content-Type': 'multipart/form-data' } })
        const resume = uploaded.data.data
        const screened = await api.post(`/api/v1/screening/resumes/${resume.id}/screen`, null, { params: { job_id: selectedJob.value } })
        completedResultIds[index] = screened.data.data?.id
        uploadResults.value[index] = { name: file.name, status: 'success', detail: '筛选完成' }
      } catch (error: any) {
        uploadResults.value[index] = { name: file.name, status: 'error', detail: error.response?.data?.detail || '上传或筛选失败' }
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(3, pendingFiles.length) }, () => worker()))
  uploadBusy.value = false
  files.value = []
  await load()
  const firstResultId = completedResultIds.find((id) => typeof id === 'number')
  if (firstResultId) await router.push(`/screening/results/${firstResultId}`)
}
onMounted(load)
</script>

<template>
  <div class="page-frame screening-dashboard">
    <header class="page-heading"><div><p class="eyebrow">AI RESUME SCREENING</p><h1>AI 简历筛选</h1><p>按岗位标准处理简历，所有 AI 结论均需人工确认。</p></div></header>
    <a-spin :spinning="loading">
      <section class="metric-grid screening-metrics"><a-card class="metric-card metric-card-action" :bordered="false" @click="router.push('/screening/jobs')"><FileSearchOutlined /><span>启用岗位</span><strong>{{ metric.jobs }}</strong><small>查看岗位标准</small></a-card><a-card class="metric-card metric-card-action" :bordered="false" @click="focusResults('all')"><InboxOutlined /><span>已处理简历</span><strong>{{ metric.resumes }}</strong><small>查看全部结果</small></a-card><a-card class="metric-card metric-card-action" :bordered="false" @click="focusResults('pending')"><FileSearchOutlined /><span>待跟进</span><strong>{{ metric.pending }}</strong><small>查看待跟进结果</small></a-card><a-card class="metric-card metric-card-action" :bordered="false" @click="focusResults('reviewed')"><FileSearchOutlined /><span>已复核结果</span><strong>{{ metric.reviewed }}</strong><small>查看处理记录</small></a-card></section>
      <section class="screening-dashboard-grid">
        <a-card v-if="canManage" class="plain-panel screening-upload-panel" :bordered="false"><div class="section-title"><div><p class="eyebrow">UPLOAD RESUMES</p><h2>上传简历</h2></div></div><a-select v-model:value="selectedJob" placeholder="选择岗位标准" class="full-control" aria-label="选择岗位标准"><a-select-option v-for="job in jobs.filter((item) => item.status !== 'inactive' && item.status !== '停用')" :key="job.id" :value="job.id">{{ job.name }}</a-select-option></a-select><label class="screening-file-drop"><UploadOutlined /><strong>选择 PDF 或 DOCX</strong><span>支持多文件，系统将逐个上传并筛选</span><input type="file" multiple accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" @change="onFileChange"></label><ul v-if="files.length" class="file-queue"><li v-for="file in files" :key="file.name + file.lastModified"><div><FileSearchOutlined /><strong>{{ file.name }}</strong><small>{{ (file.size / 1024).toFixed(0) }} KB</small></div><a-button type="text" danger :disabled="uploadBusy" aria-label="移除文件" @click="removeFile(file)"><DeleteOutlined /></a-button></li></ul><a-button type="primary" block :loading="uploadBusy" :disabled="!files.length" @click="uploadFiles"><UploadOutlined />开始上传筛选</a-button><ul v-if="uploadResults.length" class="upload-status-list"><li v-for="item in uploadResults" :key="item.name + item.detail"><span>{{ item.name }}</span><a-tag :color="item.status === 'success' ? 'green' : item.status === 'processing' ? 'blue' : 'red'">{{ item.detail }}</a-tag></li></ul></a-card>
        <a-card class="plain-panel" :bordered="false"><div class="section-title"><div><p class="eyebrow">JOB DISTRIBUTION</p><h2>岗位分布</h2></div><a-button v-if="canManage" type="link" @click="router.push('/screening/jobs')">管理岗位</a-button></div><a-empty v-if="!jobDistribution.length" description="暂无岗位数据" /><div v-else class="job-distribution"><div v-for="job in jobDistribution" :key="job.id || job.job_id || job.name" class="job-distribution-row"><span>{{ job.name || job.job_name }}</span><strong>{{ job.count ?? job.result_count ?? 0 }}</strong></div></div></a-card>
      </section>
      <a-card ref="resultSection" class="plain-panel screening-results-panel" :bordered="false"><div class="section-title"><div><p class="eyebrow">SCREENING RESULTS</p><h2>简历处理列表</h2></div><a-segmented v-model:value="resultFilter" :options="[{ label: '全部', value: 'all' }, { label: '待跟进', value: 'pending' }, { label: '已处理', value: 'reviewed' }]" /></div><a-empty v-if="!filteredResults.length" description="暂无符合条件的结果" /><a-table v-else :data-source="filteredResults" :pagination="{ pageSize: 8 }" row-key="id" :scroll="{ x: 720 }" :columns="[{ title: '简历', dataIndex: 'filename' }, { title: '岗位', dataIndex: 'job_name' }, { title: '评分', dataIndex: 'score' }, { title: '状态', dataIndex: 'human_status' }, { title: '操作', dataIndex: 'action' }]" class="data-table"><template #bodyCell="{ column, record }"><template v-if="column.dataIndex === 'filename'"><strong>{{ record.filename || record.resume_filename || '未命名简历' }}</strong></template><template v-else-if="column.dataIndex === 'human_status'"><a-tag :color="record.human_status === 'approved' ? 'green' : record.human_status === 'rejected' ? 'red' : record.human_status === 'needs_follow_up' ? 'blue' : 'orange'">{{ record.human_status === 'approved' ? '通过' : record.human_status === 'rejected' ? '不通过' : '待跟进' }}</a-tag></template><template v-else-if="column.dataIndex === 'action'"><a-button size="small" type="link" @click="router.push(`/screening/results/${record.id}`)">查看结果</a-button></template><template v-else>{{ record[column.dataIndex] ?? record.job?.name ?? '-' }}</template></template></a-table></a-card>
    </a-spin>
  </div>
</template>
