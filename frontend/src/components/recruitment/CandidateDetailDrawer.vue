<script setup lang="ts">
import { computed } from 'vue'

type EvidenceDimension = {
  dimension?: string
  score?: number
  matched_keywords?: string[]
  requirement_keywords?: string[]
}

type CandidateDetail = {
  name?: string
  email?: string
  phone?: string
  job_title?: string
  school?: string
  major?: string
  status?: string
  ai_score?: number
  ai_summary?: string
  ai_evidence?: {
    dimensions?: EvidenceDimension[]
    strengths?: string[]
    gaps?: string[]
    recommended_stage?: string
    risk_flags?: string[]
    interview_questions?: string[]
  }
  resume_text?: string
  cover_note?: string
}

const props = defineProps<{
  open: boolean
  detail: CandidateDetail | null
  statusColor: Record<string, string>
  showJob?: boolean
  showSchool?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const evidence = computed(() => props.detail?.ai_evidence)
const dimensions = computed(() => evidence.value?.dimensions || [])
const strengths = computed(() => normalizeList(evidence.value?.strengths))
const gaps = computed(() => normalizeList(evidence.value?.gaps))
const riskFlags = computed(() => normalizeList(evidence.value?.risk_flags))
const questions = computed(() => normalizeList(evidence.value?.interview_questions))
const hasEvidence = computed(() => Boolean(props.detail?.ai_score || props.detail?.ai_summary || evidence.value))

function normalizeList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
}

function keywordText(value: unknown) {
  const items = normalizeList(value)
  return items.length ? items.join('、') : '暂无'
}

function scoreColor(score?: number) {
  if (!score) return 'default'
  if (score >= 75) return 'green'
  if (score >= 55) return 'blue'
  return 'orange'
}

function progressStatus(score?: number) {
  return score && score >= 75 ? 'success' : 'normal'
}
</script>

<template>
  <a-drawer :open="open" title="候选人详情" width="760" @update:open="(value: boolean) => emit('update:open', value)">
    <template v-if="detail">
      <section class="candidate-detail-section">
        <h2>候选人信息</h2>
        <a-descriptions bordered size="small" :column="1">
          <a-descriptions-item label="姓名">{{ detail.name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="联系方式">{{ detail.email || '-' }} / {{ detail.phone || '未填' }}</a-descriptions-item>
          <a-descriptions-item v-if="showJob" label="岗位">{{ detail.job_title || '-' }}</a-descriptions-item>
          <a-descriptions-item v-if="showSchool" label="学校/专业">{{ detail.school || '未填' }} / {{ detail.major || '未填' }}</a-descriptions-item>
          <a-descriptions-item label="当前阶段"><a-tag :color="statusColor[detail.status || '']">{{ detail.status || '-' }}</a-tag></a-descriptions-item>
        </a-descriptions>
      </section>

      <section class="candidate-detail-section">
        <h2>AI 初筛结论</h2>
        <div v-if="hasEvidence" class="candidate-ai-summary">
          <div class="candidate-score">
            <span>匹配分</span>
            <strong>{{ detail.ai_score || '-' }}</strong>
          </div>
          <div class="candidate-summary-copy">
            <a-tag :color="scoreColor(detail.ai_score)">{{ evidence?.recommended_stage || detail.status || '待跟进' }}</a-tag>
            <p>{{ detail.ai_summary || '已生成结构化初筛结果，请结合简历原文人工复核。' }}</p>
          </div>
        </div>
        <a-empty v-else description="点击 AI 初筛后生成岗位匹配证据、风险和面试核验问题。" />
      </section>

      <section v-if="dimensions.length" class="candidate-detail-section">
        <h2>岗位匹配维度</h2>
        <div class="candidate-dimension-grid">
          <article v-for="item in dimensions" :key="item.dimension" class="candidate-dimension-card">
            <div>
              <strong>{{ item.dimension || '未命名维度' }}</strong>
              <a-tag :color="scoreColor(item.score)">{{ item.score || 0 }}</a-tag>
            </div>
            <a-progress :percent="item.score || 0" :show-info="false" size="small" :status="progressStatus(item.score)" />
            <small>命中关键词：{{ keywordText(item.matched_keywords) }}</small>
            <small>待核验要求：{{ keywordText(item.requirement_keywords) }}</small>
          </article>
        </div>
      </section>

      <section v-if="strengths.length || gaps.length || riskFlags.length" class="candidate-detail-section">
        <h2>复核重点</h2>
        <div class="candidate-review-grid">
          <article>
            <span>亮点</span>
            <a-empty v-if="!strengths.length" image="" description="暂无明确亮点" />
            <a-tag v-for="item in strengths" v-else :key="item" color="green">{{ item }}</a-tag>
          </article>
          <article>
            <span>缺口</span>
            <a-empty v-if="!gaps.length" image="" description="暂无明显缺口" />
            <a-tag v-for="item in gaps" v-else :key="item" color="orange">{{ item }}</a-tag>
          </article>
          <article>
            <span>风险</span>
            <a-empty v-if="!riskFlags.length" image="" description="暂无风险提示" />
            <a-tag v-for="item in riskFlags" v-else :key="item" color="red">{{ item }}</a-tag>
          </article>
        </div>
      </section>

      <section v-if="questions.length" class="candidate-detail-section">
        <h2>面试核验问题</h2>
        <ol class="candidate-question-list">
          <li v-for="item in questions" :key="item">{{ item }}</li>
        </ol>
      </section>

      <section class="candidate-detail-section">
        <h2>简历内容</h2>
        <div class="candidate-text-block">{{ detail.resume_text || '未填写' }}</div>
      </section>

      <section v-if="detail.cover_note" class="candidate-detail-section">
        <h2>求职说明</h2>
        <div class="candidate-text-block">{{ detail.cover_note }}</div>
      </section>
    </template>
  </a-drawer>
</template>
