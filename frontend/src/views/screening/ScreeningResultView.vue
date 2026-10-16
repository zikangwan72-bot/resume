<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CheckOutlined, SafetyCertificateOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'

import api from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import PageBackButton from '@/components/PageBackButton.vue'

type ReviewStatus = 'needs_follow_up' | 'approved' | 'rejected'
type ResumeSection = { title: string; content: string }

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const result = ref<any>(null)
const loading = ref(true)
const saving = ref(false)
const reviewStatus = ref<ReviewStatus>('needs_follow_up')
const reviewNote = ref('')
const canReview = computed(() => auth.can('resume:manage'))
const statusMeta = computed(() => {
  const status = result.value?.human_status || 'pending_review'
  const metadata: Record<string, { label: string; color: string }> = {
    pending_review: { label: '待跟进', color: 'orange' },
    approved: { label: '人工已通过', color: 'green' },
    rejected: { label: '人工未通过', color: 'red' },
    needs_follow_up: { label: '待跟进', color: 'blue' },
  }
  return metadata[status] || metadata.pending_review
})

const array = (value: any) => Array.isArray(value) ? value : value ? [value] : []

function normalizeStatus(value: unknown): ReviewStatus {
  if (value === 'approved' || value === 'rejected' || value === 'needs_follow_up') return value
  return 'needs_follow_up'
}

const resumeHeadings = [
  '个人信息', '基本信息', '个人资料', '联系方式', '求职意向', '教育背景', '专业技能',
  '技能专长', '核心技能', '工作经历', '工作经验', '项目经历', '项目经验', '个人优势',
  '自我评价', '语言能力', '证书资质', '证书',
]

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function tidyResumeContent(value: string) {
  return value
    .replace(/\s*[·•]\s*/g, '\n• ')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function splitResumeSource(source: string): ResumeSection[] {
  const normalized = source.replace(/\r\n?/g, '\n').trim()
  if (!normalized) return []
  const labels = resumeHeadings.map(escapeRegex).join('|')
  let matches = [...normalized.matchAll(new RegExp(`(^|[\\n。；;·])\\s*(${labels})\\s*[：:]?\\s*`, 'g'))]
  if (matches.length < 2) {
    matches = [...normalized.matchAll(new RegExp(`(^|\\s)(${labels})\\s*[：:]?\\s*`, 'g'))]
  }
  if (!matches.length) return [{ title: '原文内容', content: tidyResumeContent(normalized) }]

  const sections: ResumeSection[] = []
  const prefix = normalized.slice(0, matches[0].index).trim()
  if (prefix) sections.push({ title: '基本信息', content: tidyResumeContent(prefix) })
  matches.forEach((match, index) => {
    const start = (match.index || 0) + match[0].length
    const end = index + 1 < matches.length ? matches[index + 1].index : normalized.length
    const content = tidyResumeContent(normalized.slice(start, end))
    if (content) sections.push({ title: match[2], content })
  })
  return sections.length ? sections : [{ title: '原文内容', content: tidyResumeContent(normalized) }]
}

const resumeSections = computed(() => splitResumeSource(result.value?.extracted_text || result.value?.resume_text || ''))

async function load() {
  loading.value = true
  try {
    result.value = (await api.get(`/api/v1/screening/results/${route.params.id}`)).data.data
    reviewStatus.value = normalizeStatus(result.value?.human_status)
    reviewNote.value = result.value?.review_note || ''
  } catch (error: any) {
    message.error(error.response?.data?.detail || '筛选结果加载失败')
  } finally {
    loading.value = false
  }
}

async function review() {
  if (!canReview.value) return
  saving.value = true
  try {
    await api.patch(`/api/v1/screening/results/${route.params.id}/review`, {
      human_status: reviewStatus.value,
      review_note: reviewNote.value,
    })
    message.success('人工复核已保存')
    await router.replace('/modules/resume-screening')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '复核保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-frame screening-result-page">
    <a-spin :spinning="loading">
      <template v-if="result">
        <header class="page-heading">
          <div>
            <p class="eyebrow">SCREENING RESULT</p>
            <h1>{{ result.filename || result.resume_filename || '简历筛选结果' }}</h1>
            <p>{{ result.job_name || result.job?.name || '未命名岗位' }} · {{ result.created_at || '' }}</p>
          </div>
          <div class="heading-actions"><PageBackButton fallback="/modules/resume-screening" label="返回结果列表" /><a-tag :color="statusMeta.color"><SafetyCertificateOutlined /> {{ statusMeta.label }}</a-tag></div>
        </header>

        <section class="result-score-strip">
          <div class="result-score-card"><span>AI 综合评分</span><strong>{{ result.score ?? '-' }}</strong><small>/ 100</small></div>
          <div class="result-summary-copy"><span class="result-summary-label">筛选摘要</span><p>{{ result.summary || '暂无摘要' }}</p></div>
        </section>

        <section class="result-detail-grid">
          <a-card class="evidence-panel evidence-panel-positive" :bordered="false"><div class="evidence-heading"><span class="evidence-marker">+</span><h2>优势</h2></div><ul class="evidence-list"><li v-for="item in array(result.strengths)" :key="item">{{ item }}</li></ul><a-empty v-if="!array(result.strengths).length" description="暂无优势" /></a-card>
          <a-card class="evidence-panel evidence-panel-gap" :bordered="false"><div class="evidence-heading"><span class="evidence-marker">!</span><h2>缺点</h2></div><ul class="evidence-list"><li v-for="item in [...array(result.gaps), ...array(result.risk_flags)]" :key="item">{{ item }}</li></ul><a-empty v-if="!array(result.gaps).length && !array(result.risk_flags).length" description="暂无缺点" /></a-card>
          <a-card class="evidence-panel evidence-panel-source" :bordered="false"><div class="evidence-heading"><span class="evidence-marker">✓</span><h2>依据</h2></div><ul class="evidence-list"><li v-for="item in array(result.evidence)" :key="typeof item === 'string' ? item : JSON.stringify(item)">{{ typeof item === 'string' ? item : item.text || item.content || JSON.stringify(item) }}</li></ul><a-empty v-if="!array(result.evidence).length" description="暂无依据" /></a-card>
        </section>

        <section class="result-action-grid">
          <a-card class="recommendation-panel" :bordered="false"><p class="eyebrow">RECOMMENDATION</p><h2>{{ result.recommendation || '待跟进' }}</h2><p>{{ result.summary || '暂无建议说明' }}</p></a-card>
          <a-card class="review-panel" :bordered="false">
            <div class="section-title"><h2>人工复核</h2><CheckOutlined /></div>
            <a-form layout="vertical">
              <a-form-item label="复核结论">
                <a-select v-model:value="reviewStatus" :disabled="!canReview">
                  <a-select-option value="needs_follow_up">待跟进</a-select-option>
                  <a-select-option value="approved">通过</a-select-option>
                  <a-select-option value="rejected">不通过</a-select-option>
                </a-select>
              </a-form-item>
              <a-form-item label="复核备注"><a-textarea v-model:value="reviewNote" :disabled="!canReview" :rows="5" placeholder="记录人工判断和补充依据" /></a-form-item>
              <a-button v-if="canReview" type="primary" block :loading="saving" @click="review">保存复核</a-button>
              <a-alert v-else type="info" show-icon message="当前账号可查看结果，但无权修改复核结论。" />
            </a-form>
          </a-card>
        </section>

        <a-card class="resume-source-panel" :bordered="false">
          <div class="section-title"><div><p class="eyebrow">RESUME SOURCE</p><h2>简历原文</h2></div><span class="source-hint">按原文模块整理展示，内容未改写</span></div>
          <div v-if="resumeSections.length" class="resume-section-grid">
            <article v-for="(section, index) in resumeSections" :key="`${section.title}-${index}`" class="resume-section" :class="{ 'resume-section-wide': section.content.length > 260 }">
              <h3>{{ section.title }}</h3>
              <p>{{ section.content }}</p>
            </article>
          </div>
          <a-empty v-else description="暂无简历原文" />
        </a-card>
      </template>
      <a-empty v-else description="暂无筛选结果" />
    </a-spin>
  </div>
</template>
