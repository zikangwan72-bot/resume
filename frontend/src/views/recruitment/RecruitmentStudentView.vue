<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { FileTextOutlined, SafetyCertificateOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import api from '@/api/client'

const jobs = ref<any[]>([])
const loading = ref(false)
const drawer = ref(false)
const selectedJob = ref<any>(null)
const submittedJob = ref('')
const resumeFileName = ref('')
const consent = ref(false)
const statusEmail = ref('')

const form = reactive({
  name: '',
  email: '',
  phone: '',
  school: '',
  major: '',
  graduation_year: 2027,
  resume_text: '',
  cover_note: '',
})

async function load() {
  loading.value = true
  try {
    jobs.value = (await api.get('/api/v1/recruitment/public/jobs')).data.data
  } catch (error:any) {
    message.error(error.response?.data?.detail || '岗位加载失败')
  } finally {
    loading.value = false
  }
}

function apply(job:any) {
  selectedJob.value = job
  consent.value = false
  resumeFileName.value = ''
  Object.assign(form, { name: '', email: '', phone: '', school: '', major: '', graduation_year: 2027, resume_text: '', cover_note: '' })
  drawer.value = true
}

function beforeResumeUpload(file: File) {
  resumeFileName.value = file.name
  return false
}

async function submit() {
  if (!selectedJob.value) return
  if (!form.name.trim() || !form.email.trim()) return message.warning('请填写姓名和邮箱')
  if (!form.resume_text.trim() && !resumeFileName.value) return message.warning('请填写简历内容或选择简历文件')
  if (!consent.value) return message.warning('请先同意隐私与 AI 辅助筛选说明')
  try {
    await api.post('/api/v1/recruitment/public/applications', { ...form, job_id: selectedJob.value.id, cover_note: [form.cover_note, resumeFileName.value ? `附件：${resumeFileName.value}` : ''].filter(Boolean).join('\n') })
    submittedJob.value = selectedJob.value.title
    statusEmail.value = form.email
    message.success('投递成功')
    drawer.value = false
  } catch (error:any) {
    message.error(error.response?.data?.detail || '投递失败')
  }
}

function queryStatus() {
  if (!statusEmail.value.trim()) return message.warning('请填写投递邮箱')
  message.info('演示版已记录投递邮箱。正式版会返回带凭证的候选人进度页。')
}

onMounted(load)
</script>

<template>
  <div class="careers-page">
    <header class="careers-header">
      <div class="careers-brand">
        <span>EA</span>
        <strong>招聘投递</strong>
      </div>
    </header>

    <main class="careers-main">
      <header class="careers-heading">
        <div>
          <p class="eyebrow">CAREERS</p>
          <h1>岗位投递</h1>
          <p>选择岗位，填写资料，提交后等待招聘团队联系。</p>
        </div>
        <a-tag color="blue">公开门户</a-tag>
      </header>

      <a-alert v-if="submittedJob" type="success" show-icon message="投递已提交" :description="`你已成功投递「${submittedJob}」。招聘团队会通过邮箱或电话联系你。`" class="careers-success" />

      <a-spin :spinning="loading">
        <section class="careers-grid">
          <a-card class="plain-panel careers-jobs" :bordered="false">
            <div class="section-title">
              <div><p class="eyebrow">OPEN POSITIONS</p><h2>开放岗位</h2></div>
              <a-tag>{{ jobs.length }} 个岗位</a-tag>
            </div>
            <a-empty v-if="!jobs.length" description="暂无开放岗位" />
            <a-list v-else item-layout="vertical" :data-source="jobs">
              <template #renderItem="{ item }">
                <a-list-item class="job-list-item">
                  <template #actions><a-button type="primary" @click="apply(item)">查看详情并投递</a-button></template>
                  <a-list-item-meta :title="item.title" :description="`${item.department} · ${item.location} · ${item.employment_type}`" />
                  <p>{{ item.description }}</p>
                  <p><strong>岗位要求：</strong>{{ item.requirements }}</p>
                </a-list-item>
              </template>
            </a-list>
          </a-card>

          <aside class="careers-aside">
            <a-card class="plain-panel" :bordered="false">
              <p class="eyebrow">FLOW</p>
              <h2>流程</h2>
              <div class="vertical-steps">
                <div><span>1</span><strong>选岗位</strong><small>确认岗位内容和要求</small></div>
                <div><span>2</span><strong>交资料</strong><small>填写联系方式和简历</small></div>
                <div><span>3</span><strong>等反馈</strong><small>招聘团队人工复核后联系</small></div>
              </div>
            </a-card>

            <a-card class="privacy-panel" :bordered="false">
              <SafetyCertificateOutlined />
              <div><strong>资料说明</strong><p>资料仅用于招聘。AI 只辅助整理信息，最终由招聘人员判断。</p></div>
            </a-card>

            <a-card class="plain-panel" :bordered="false">
              <p class="eyebrow">STATUS</p>
              <h2>进度查询</h2>
              <a-input v-model:value="statusEmail" placeholder="输入投递邮箱" style="margin-bottom:8px" />
              <a-button block @click="queryStatus"><SearchOutlined /> 查询进度</a-button>
            </a-card>
          </aside>
        </section>
      </a-spin>
    </main>

    <a-drawer v-model:open="drawer" title="提交岗位申请" width="560">
      <a-alert v-if="selectedJob" type="info" :message="selectedJob.title" :description="`${selectedJob.department} · ${selectedJob.location}`" class="drawer-job-summary" />
      <a-form layout="vertical">
        <a-form-item label="姓名" required><a-input v-model:value="form.name" aria-label="姓名" /></a-form-item>
        <a-form-item label="邮箱" required><a-input v-model:value="form.email" aria-label="邮箱" /></a-form-item>
        <a-form-item label="手机号"><a-input v-model:value="form.phone" /></a-form-item>
        <a-form-item label="学校"><a-input v-model:value="form.school" /></a-form-item>
        <a-form-item label="专业"><a-input v-model:value="form.major" /></a-form-item>
        <a-form-item label="毕业年份"><a-input-number v-model:value="form.graduation_year" :min="2000" :max="2100" style="width:100%" /></a-form-item>
        <a-form-item label="简历文件"><a-upload :before-upload="beforeResumeUpload" :max-count="1" accept=".pdf,.doc,.docx"><a-button><FileTextOutlined /> 选择 PDF / DOCX</a-button></a-upload><small v-if="resumeFileName">已选择：{{ resumeFileName }}</small></a-form-item>
        <a-form-item label="简历内容"><a-textarea v-model:value="form.resume_text" aria-label="简历内容" :rows="7" placeholder="粘贴教育、实习、项目、技能。" /></a-form-item>
        <a-form-item label="求职说明"><a-textarea v-model:value="form.cover_note" aria-label="求职说明" :rows="3" /></a-form-item>
        <a-checkbox v-model:checked="consent" class="careers-consent">我同意招聘团队处理我的投递资料，并了解 AI 仅提供辅助筛选建议，最终由招聘人员人工复核。</a-checkbox>
        <a-button type="primary" block style="margin-top:16px" @click="submit"><FileTextOutlined /> 提交投递</a-button>
      </a-form>
    </a-drawer>
  </div>
</template>
