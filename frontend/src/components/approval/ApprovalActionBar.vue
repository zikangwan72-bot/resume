<script setup lang="ts">
import { ref } from 'vue'
import { CheckCircleOutlined, CloseCircleOutlined, RollbackOutlined, SwapOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { ApprovalUser } from '@/types/approval'

const props = withDefaults(defineProps<{ preview?: boolean; canTransfer?: boolean; loading?: boolean; users?: Pick<ApprovalUser, 'id' | 'display_name'>[] }>(), { preview: false, canTransfer: false, loading: false, users: () => [] })
const emit = defineEmits<{ return: [comment: string]; reject: [comment: string]; transfer: [payload: { targetUserId: string; comment: string }]; approve: [comment: string] }>()
const comment = ref(''); const transferTarget = ref('')

function run(kind: 'return' | 'reject' | 'transfer' | 'approve') {
  if (props.preview) return
  if ((kind === 'return' || kind === 'reject') && !comment.value.trim()) return message.warning(`${kind === 'return' ? '退回' : '驳回'}必须填写原因`)
  if (kind === 'transfer' && !transferTarget.value) return message.warning('请选择转审目标人')
  if (kind === 'transfer') emit('transfer', { targetUserId: transferTarget.value, comment: comment.value.trim() })
  else if (kind === 'return') emit('return', comment.value.trim())
  else if (kind === 'reject') emit('reject', comment.value.trim())
  else emit('approve', comment.value.trim())
}

function clear() { comment.value = ''; transferTarget.value = '' }
defineExpose({ clear })
</script>

<template>
  <section class="approval-action-bar" aria-label="审批操作">
    <a-textarea v-model:value="comment" aria-label="审批意见" :disabled="preview" placeholder="填写审批意见；退回或驳回时必填" :rows="3" />
    <div v-if="canTransfer" class="transfer-row">
      <a-select v-model:value="transferTarget" aria-label="转审目标人" :disabled="preview" placeholder="选择转审人" :options="users.map((user) => ({ label: user.display_name, value: user.id }))" />
    </div>
    <div class="action-buttons">
      <a-button :disabled="preview" :loading="loading" @click="run('return')"><RollbackOutlined />退回上一步</a-button>
      <a-button danger :disabled="preview" :loading="loading" @click="run('reject')"><CloseCircleOutlined />驳回发起人</a-button>
      <a-button v-if="canTransfer" :disabled="preview" :loading="loading" @click="run('transfer')"><SwapOutlined />转审</a-button>
      <a-button type="primary" :disabled="preview" :loading="loading" @click="run('approve')"><CheckCircleOutlined />同意并提交</a-button>
    </div>
    <p v-if="preview" class="preview-note">预览模式，仅展示最终审批操作。</p>
  </section>
</template>

<style scoped>
.approval-action-bar { display:grid; gap:12px; } .transfer-row { max-width:320px; } .transfer-row :deep(.ant-select) { width:100%; } .action-buttons { display:flex; gap:8px; flex-wrap:wrap; } .preview-note { margin:0; color:#687386; font-size:12px; } @media (max-width:600px) { .action-buttons { display:grid; grid-template-columns:1fr 1fr; } .action-buttons :deep(.ant-btn) { width:100%; } }
</style>
