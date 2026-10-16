<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { DeleteOutlined, EditOutlined, FileSearchOutlined, PlusOutlined, TeamOutlined } from '@ant-design/icons-vue'
import { Modal, message } from 'ant-design-vue'

import api from '@/api/client'
import PageBackButton from '@/components/PageBackButton.vue'
import CandidateDetailDrawer from '@/components/recruitment/CandidateDetailDrawer.vue'

const jobs = ref<any[]>([])
const applications = ref<any[]>([])
const loading = ref(false)
const activeTab = ref('jobs')
const jobDrawer = ref(false)
const editingJobId = ref<number | null>(null)
const detail = ref<any>(null)
const detailOpen = ref(false)
const keyword = ref('')
const statusFilter = ref('全部')
const jobFilter = ref<number | '全部'>('全部')

const statuses = ['待初筛', '待面试', '面试中', 'Offer', '已录用', '不合适', '人才库']
const jobStatuses = ['开放', '暂停', '已关闭']
const filterStatuses = ['全部', ...statuses]
const statusColor: Record<string, string> = {
  待初筛: 'default',
  待面试: 'blue',
  面试中: 'processing',
  Offer: 'purple',
  已录用: 'green',
  不合适: 'red',
  人才库: 'gold',
}

const emptyJobForm = {
  title: '',
  department: '',
  location: 'Singapore',
  employment_type: '实习',
  description: '',
  requirements: '',
  status: '开放',
}
const jobForm = reactive({ ...emptyJobForm })

const openJobs = computed(() => jobs.value.filter((item) => item.status === '开放'))
const todoCandidates = computed(() => applications.value.filter((item) => item.status === '待初筛' || item.ai_status !== '已筛选'))
const interviewCandidates = computed(() => applications.value.filter((item) => ['待面试', '面试中', 'Offer'].includes(item.status)))
const hiredCount = computed(() => applications.value.filter((item) => item.status === '已录用').length)
const jobFilterOptions = computed(() => [
  { label: '全部岗位', value: '全部' },
  ...jobs.value.map((job) => ({ label: job.title, value: job.id })),
])
const jobRows = computed(() =>
  jobs.value.map((job) => {
    const rows = applications.value.filter((item) => item.job_id === job.id)
    return {
      ...job,
      candidate_count: rows.length,
      waiting_count: rows.filter((item) => item.status === '待初筛').length,
      interview_count: rows.filter((item) => ['待面试', '面试中', 'Offer'].includes(item.status)).length,
      hired_count: rows.filter((item) => item.status === '已录用').length,
    }
  }),
)
const filteredApplications = computed(() =>
  applications.value.filter((item) => {
    const text = `${item.name}${item.email}${item.job_title}${item.school || ''}${item.major || ''}`.toLowerCase()
    return (
      (!keyword.value || text.includes(keyword.value.toLowerCase())) &&
      (statusFilter.value === '全部' || item.status === statusFilter.value) &&
      (jobFilter.value === '全部' || item.job_id === jobFilter.value)
    )
  }),
)

async function load() {
  loading.value = true
  try {
    const [jobResponse, applicationResponse] = await Promise.all([
      api.get('/api/v1/recruitment/jobs'),
      api.get('/api/v1/recruitment/applications'),
    ])
    jobs.value = jobResponse.data.data
    applications.value = applicationResponse.data.data
  } catch (error:any) {
    message.error(error.response?.data?.detail || '招聘数据加载失败')
  } finally {
    loading.value = false
  }
}

function resetJobForm() {
  editingJobId.value = null
  Object.assign(jobForm, emptyJobForm)
}

function openCreateJob() {
  resetJobForm()
  jobDrawer.value = true
}

function openEditJob(row:any) {
  editingJobId.value = row.id
  Object.assign(jobForm, {
    title: row.title,
    department: row.department,
    location: row.location,
    employment_type: row.employment_type,
    description: row.description,
    requirements: row.requirements,
    status: row.status,
  })
  jobDrawer.value = true
}

async function saveJob() {
  if (![jobForm.title, jobForm.department, jobForm.location, jobForm.description, jobForm.requirements].every((value) => value.trim())) return message.warning('请完整填写岗位信息')
  try {
    if (editingJobId.value) {
      await api.patch(`/api/v1/recruitment/jobs/${editingJobId.value}`, jobForm)
      message.success('岗位已更新')
    } else {
      await api.post('/api/v1/recruitment/jobs', jobForm)
      message.success('岗位已创建')
    }
    jobDrawer.value = false
    resetJobForm()
    await load()
  } catch (error:any) {
    message.error(error.response?.data?.detail || '岗位保存失败')
  }
}

async function setJobStatus(row:any, status:string) {
  try {
    await api.patch(`/api/v1/recruitment/jobs/${row.id}`, { status })
    message.success(status === '开放' ? '岗位已开放' : '岗位状态已更新')
    await load()
  } catch (error:any) {
    message.error(error.response?.data?.detail || '岗位状态更新失败')
  }
}

function removeJob(row:any) {
  Modal.confirm({
    title: '删除岗位？',
    content: row.candidate_count ? '该岗位已有候选人，系统会阻止删除。建议关闭岗位保留记录。' : '删除后公开投递端将不再显示该岗位。',
    okText: '删除',
    okType: 'danger',
    async onOk() {
      try {
        await api.delete(`/api/v1/recruitment/jobs/${row.id}`)
        message.success('岗位已删除')
        await load()
      } catch (error:any) {
        message.error(error.response?.data?.detail || '岗位删除失败')
      }
    },
  })
}

async function screenCandidate(item:any) {
  try {
    detail.value = (await api.post(`/api/v1/recruitment/applications/${item.id}/screen`)).data.data
    detailOpen.value = true
    message.success('AI 初筛已完成，请人工复核')
    await load()
  } catch (error:any) {
    message.error(error.response?.data?.detail || 'AI 初筛失败')
  }
}

async function changeStatus(item:any, status:string) {
  try {
    await api.patch(`/api/v1/recruitment/applications/${item.id}/status`, { status, review_note: item.review_note || '招聘人员人工更新' })
    message.success('候选人阶段已更新')
    await load()
  } catch (error:any) {
    message.error(error.response?.data?.detail || '状态更新失败')
  }
}

function openDetail(item:any) {
  detail.value = item
  detailOpen.value = true
}

onMounted(load)
</script>

<template>
  <div class="page-frame business-page recruitment-admin-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">RECRUITMENT WORKSPACE</p>
        <h1>招聘管理端</h1>
        <p>先维护岗位，再处理候选人，最后推进面试和录用。AI 初筛只提供辅助建议，最终由招聘人员复核。</p>
      </div>
      <div class="heading-actions">
        <PageBackButton fallback="/modules/resume-screening" />
        <a-button type="primary" @click="openCreateJob"><PlusOutlined /> 新增岗位</a-button>
      </div>
    </header>

    <a-spin :spinning="loading">
      <section class="metric-grid">
        <a-card class="metric-card" :bordered="false"><FileSearchOutlined /><span>开放岗位</span><strong>{{ openJobs.length }}</strong></a-card>
        <a-card class="metric-card" :bordered="false"><TeamOutlined /><span>候选人总数</span><strong>{{ applications.length }}</strong></a-card>
        <a-card class="metric-card" :bordered="false"><TeamOutlined /><span>待处理</span><strong>{{ todoCandidates.length }}</strong></a-card>
        <a-card class="metric-card" :bordered="false"><TeamOutlined /><span>Offer/录用</span><strong>{{ hiredCount }}</strong></a-card>
      </section>

      <a-tabs v-model:active-key="activeTab" class="business-tabs">
        <a-tab-pane key="jobs" tab="岗位管理">
          <a-card class="plain-panel" :bordered="false">
            <div class="section-title">
              <div><p class="eyebrow">JOB CRUD</p><h2>岗位列表</h2></div>
              <a-button type="primary" @click="openCreateJob"><PlusOutlined /> 新增岗位</a-button>
            </div>
            <a-table
              class="recruitment-job-table"
              size="small"
              :pagination="{ pageSize: 8 }"
              :data-source="jobRows"
              :columns="[
                { title: '岗位信息', dataIndex: 'title', width: '34%' },
                { title: '部门/地点', dataIndex: 'department', width: '20%' },
                { title: '状态', dataIndex: 'status', width: '10%' },
                { title: '候选人', dataIndex: 'candidate_count', width: '10%' },
                { title: '阶段进度', dataIndex: 'stage_counts', width: '14%' },
                { title: '操作', dataIndex: 'actions', width: '12%' },
              ]"
              row-key="id"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'title'">
                  <strong>{{ record.title }}</strong>
                  <span class="table-subline">{{ record.employment_type }} · {{ record.description.slice(0, 36) }}{{ record.description.length > 36 ? '...' : '' }}</span>
                </template>
                <template v-if="column.dataIndex === 'department'">
                  <span>{{ record.department }}</span>
                  <span class="table-subline">{{ record.location }}</span>
                </template>
                <template v-if="column.dataIndex === 'status'"><a-tag :color="record.status === '开放' ? 'green' : record.status === '暂停' ? 'orange' : 'default'">{{ record.status }}</a-tag></template>
                <template v-if="column.dataIndex === 'stage_counts'">
                  <span>待筛 {{ record.waiting_count }} / 面试 {{ record.interview_count }} / 录用 {{ record.hired_count }}</span>
                </template>
                <template v-if="column.dataIndex === 'actions'">
                  <a-space class="table-action-group" :size="6">
                    <a-button size="small" @click="openEditJob(record)"><EditOutlined /> 编辑</a-button>
                    <a-button v-if="record.status !== '已关闭'" size="small" @click="setJobStatus(record, '已关闭')">关闭</a-button>
                    <a-button v-else size="small" @click="setJobStatus(record, '开放')">重新开放</a-button>
                    <a-button size="small" danger @click="removeJob(record)"><DeleteOutlined /> 删除</a-button>
                  </a-space>
                </template>
              </template>
            </a-table>
          </a-card>
        </a-tab-pane>

        <a-tab-pane key="candidates" tab="候选人处理">
          <a-card class="plain-panel" :bordered="false">
            <div class="section-title">
              <div><p class="eyebrow">PIPELINE</p><h2>候选人池</h2></div>
              <a-space wrap>
                <a-input v-model:value="keyword" allow-clear placeholder="搜索候选人、邮箱、岗位" style="width:220px" />
                <a-select v-model:value="jobFilter" :options="jobFilterOptions" style="width:180px" />
                <a-select v-model:value="statusFilter" :options="filterStatuses.map((value) => ({ label: value, value }))" style="width:120px" />
              </a-space>
            </div>
            <a-table
              v-if="filteredApplications.length"
              class="recruitment-candidate-table"
              size="small"
              :pagination="{ pageSize: 8 }"
              :data-source="filteredApplications"
              :columns="[
                { title: '候选人', dataIndex: 'name', width: '30%' },
                { title: '岗位', dataIndex: 'job_title', width: '26%' },
                { title: 'AI评分', dataIndex: 'ai_score', width: '12%' },
                { title: '阶段', dataIndex: 'status', width: '14%' },
                { title: '操作', dataIndex: 'actions', width: '18%' },
              ]"
              row-key="id"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'name'">
                  <strong>{{ record.name }}</strong>
                  <span class="table-subline">{{ record.email }} · {{ record.school || '学校未填' }} / {{ record.major || '专业未填' }}</span>
                </template>
                <template v-if="column.dataIndex === 'ai_score'"><a-tag :color="record.ai_score >= 75 ? 'green' : record.ai_score ? 'orange' : 'default'">{{ record.ai_score || '未筛选' }}</a-tag></template>
                <template v-if="column.dataIndex === 'status'"><a-select :value="record.status" size="small" style="width:112px" :options="statuses.map((value) => ({ label: value, value }))" @change="(value:string) => changeStatus(record, value)" /></template>
                <template v-if="column.dataIndex === 'actions'">
                  <a-space class="table-action-group" :size="6">
                    <a-button size="small" type="primary" ghost @click="screenCandidate(record)">AI 初筛</a-button>
                    <a-button size="small" @click="changeStatus(record, '待面试')">进面试</a-button>
                    <a-button size="small" @click="openDetail(record)">详情</a-button>
                  </a-space>
                </template>
              </template>
            </a-table>
            <a-empty v-else description="没有符合条件的候选人" />
          </a-card>
        </a-tab-pane>

        <a-tab-pane key="interview" tab="面试推进">
          <a-card class="plain-panel" :bordered="false">
            <div class="section-title"><div><p class="eyebrow">INTERVIEW</p><h2>面试与 Offer</h2></div><a-tag color="blue">{{ interviewCandidates.length }} 人</a-tag></div>
            <a-empty v-if="!interviewCandidates.length" description="暂无待推进候选人" />
            <a-table
              v-else
              class="recruitment-candidate-table"
              size="small"
              :pagination="{ pageSize: 8 }"
              :data-source="interviewCandidates"
              :columns="[
                { title: '候选人', dataIndex: 'name', width: '28%' },
                { title: '岗位', dataIndex: 'job_title', width: '28%' },
                { title: '阶段', dataIndex: 'status', width: '12%' },
                { title: 'AI评分', dataIndex: 'ai_score', width: '10%' },
                { title: '操作', dataIndex: 'actions', width: '22%' },
              ]"
              row-key="id"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'name'">
                  <strong>{{ record.name }}</strong>
                  <span class="table-subline">{{ record.email }}</span>
                </template>
                <template v-if="column.dataIndex === 'status'"><a-tag :color="statusColor[record.status]">{{ record.status }}</a-tag></template>
                <template v-if="column.dataIndex === 'ai_score'"><a-tag :color="record.ai_score >= 75 ? 'green' : record.ai_score ? 'orange' : 'default'">{{ record.ai_score || '未筛选' }}</a-tag></template>
                <template v-if="column.dataIndex === 'actions'">
                  <a-space class="table-action-group" :size="6">
                    <a-button size="small" @click="changeStatus(record, '面试中')">面试中</a-button>
                    <a-button size="small" type="primary" ghost @click="changeStatus(record, 'Offer')">发 Offer</a-button>
                    <a-button size="small" @click="changeStatus(record, '已录用')">录用</a-button>
                    <a-button size="small" danger @click="changeStatus(record, '不合适')">淘汰</a-button>
                    <a-button size="small" @click="openDetail(record)">详情</a-button>
                  </a-space>
                </template>
              </template>
            </a-table>
          </a-card>
        </a-tab-pane>
      </a-tabs>
    </a-spin>

    <a-drawer v-model:open="jobDrawer" :title="editingJobId ? '编辑岗位' : '新增岗位'" width="640">
      <a-form layout="vertical">
        <a-form-item label="岗位名称" required><a-input v-model:value="jobForm.title" placeholder="例如：AI产品经理实习生" /></a-form-item>
        <a-form-item label="部门" required><a-input v-model:value="jobForm.department" placeholder="例如：产品与流程创新部" /></a-form-item>
        <a-form-item label="地点" required><a-input v-model:value="jobForm.location" placeholder="例如：Singapore / 上海 / 远程" /></a-form-item>
        <a-form-item label="用工类型"><a-select v-model:value="jobForm.employment_type" :options="['实习','校招','社招','合同'].map((value) => ({ label: value, value }))" /></a-form-item>
        <a-form-item label="岗位状态"><a-select v-model:value="jobForm.status" :options="jobStatuses.map((value) => ({ label: value, value }))" /></a-form-item>
        <a-form-item label="岗位描述" required><a-textarea v-model:value="jobForm.description" :rows="5" placeholder="写清这个岗位要负责什么业务、和谁协作、交付什么结果。" /></a-form-item>
        <a-form-item label="岗位要求" required><a-textarea v-model:value="jobForm.requirements" :rows="5" placeholder="写清必须能力、加分项、不能接受的缺口。AI 初筛会基于这里给出匹配证据。" /></a-form-item>
        <a-space style="width:100%; justify-content:flex-end">
          <a-button @click="jobDrawer = false">取消</a-button>
          <a-button type="primary" @click="saveJob">{{ editingJobId ? '保存修改' : '保存岗位' }}</a-button>
        </a-space>
      </a-form>
    </a-drawer>

    <CandidateDetailDrawer v-model:open="detailOpen" :detail="detail" :status-color="statusColor" show-school />
  </div>
</template>
