<script setup lang="ts">
import { computed, ref } from 'vue'
import dayjs, { type Dayjs } from 'dayjs'
import type { DetailColumn, FormField, FormSchema } from '@/types/approval'

type Value = string | number | string[] | Record<string, unknown>[] | null
const props = withDefaults(defineProps<{ schema: FormSchema | Record<string, unknown> | null; modelValue: Record<string, Value>; applicant?: Record<string, unknown> | null; readonly?: boolean }>(), { applicant: null, readonly: false })
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, Value>]; validationChange: [errors: Record<string, string>] }>()
const errors = ref<Record<string, string>>({})
const fields = computed(() => Array.isArray((props.schema as FormSchema | null)?.fields) ? (props.schema as FormSchema).fields : [])
const supported = new Set(['text', 'textarea', 'number', 'money', 'date', 'date_range', 'radio', 'checkbox', 'select', 'user', 'department', 'attachment', 'section', 'detail_table'])
const keyOf = (field: Pick<FormField, 'id' | 'key'>) => field.id || field.key
function setValue(key: string, value: Value) { emit('update:modelValue', { ...props.modelValue, [key]: value }); validate() }
function isEmpty(value: unknown) { return value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0) }
function numberError(field: Pick<FormField, 'label' | 'min' | 'max' | 'precision'>, value: unknown) {
  if (typeof value !== 'number' || Number.isNaN(value)) return `${field.label}必须是数字`
  if (field.min != null && value < field.min) return `${field.label}不能小于最小值`
  if (field.max != null && value > field.max) return `${field.label}不能大于最大值`
  if (field.precision != null && String(value).split('.')[1]?.length > field.precision) return `${field.label}最多保留 ${field.precision} 位小数`
  return ''
}
function validate() {
  const next: Record<string, string> = {}
  for (const field of fields.value) {
    const key = keyOf(field); const value = props.modelValue[key]
    if (field.type === 'section') continue
    if (!supported.has(field.type)) next[key] = `${field.label}字段类型不受支持`
    else if (field.required && isEmpty(value)) next[key] = `请填写：${field.label}`
    else if (!isEmpty(value) && (field.type === 'number' || field.type === 'money')) next[key] = numberError(field, value)
    else if (!isEmpty(value) && ['radio', 'select'].includes(field.type) && (!field.options?.includes(value as string))) next[key] = `${field.label}选项无效`
    else if (field.type === 'detail_table' && Array.isArray(value)) value.forEach((row, index) => { const detailRow = row as Record<string, unknown>; (field.columns || []).forEach(column => { const result = columnError(column, detailRow[column.id || column.key]); if (result) next[`${key}.${index}.${column.id || column.key}`] = result }) })
  }
  errors.value = Object.fromEntries(Object.entries(next).filter(([, value]) => value)); emit('validationChange', errors.value); return Object.keys(errors.value).length === 0
}
function columnError(column: DetailColumn, value: unknown) { if (column.required && isEmpty(value)) return `请填写：${column.label}`; if (!isEmpty(value) && (column.type === 'number' || column.type === 'money')) return numberError(column, value); if (!isEmpty(value) && column.type === 'select' && !column.options?.includes(value as string)) return `${column.label}选项无效`; return '' }
function dateValue(value: unknown) { return typeof value === 'string' ? dayjs(value) : undefined }
function rangeValue(value: unknown) { return Array.isArray(value) ? value.map(dateValue).filter(Boolean) as Dayjs[] : undefined }
function changeDate(key: string, value: Dayjs | null) { setValue(key, value?.format('YYYY-MM-DD') || null) }
function changeRange(key: string, value: Dayjs[] | null) { setValue(key, value?.map(item => item.format('YYYY-MM-DD')) || null) }
function addRow(field: FormField) { const key = keyOf(field); setValue(key, [...((props.modelValue[key] as Record<string, unknown>[]) || []), {}]) }
function updateRow(field: FormField, rowIndex: number, column: DetailColumn, value: unknown) { const key = keyOf(field); const rows = [...((props.modelValue[key] as Record<string, unknown>[]) || [])]; rows[rowIndex] = { ...rows[rowIndex], [column.id || column.key]: value }; setValue(key, rows) }
function removeRow(field: FormField, rowIndex: number) { const key = keyOf(field); setValue(key, ((props.modelValue[key] as Record<string, unknown>[]) || []).filter((_, index) => index !== rowIndex)) }
function attachmentChange(field: FormField, info: { fileList: Array<{ name: string; size?: number; type?: string }> }) { setValue(keyOf(field), info.fileList.map(file => JSON.stringify({ name: file.name, size: file.size ?? 0, type: file.type ?? '' }))) }
function displayValue(value: Value | undefined) { return Array.isArray(value) ? value.map(item => typeof item === 'object' ? JSON.stringify(item) : item).join('，') : value || '-' }
defineExpose({ validate, setErrors: (next: Record<string, string>) => { errors.value = next; emit('validationChange', next) } })
</script>

<template>
  <a-descriptions v-if="applicant" title="申请人信息" bordered :column="{ xs: 1, sm: 2 }" class="applicant-info">
    <a-descriptions-item label="姓名">{{ applicant.display_name || applicant.name }}</a-descriptions-item><a-descriptions-item label="邮箱">{{ applicant.email }}</a-descriptions-item><a-descriptions-item label="部门">{{ applicant.department }}</a-descriptions-item><a-descriptions-item label="职位">{{ applicant.position }}</a-descriptions-item>
  </a-descriptions>
  <a-form layout="vertical" class="dynamic-form">
    <template v-for="field in fields" :key="keyOf(field)">
      <h3 v-if="field.type === 'section'" class="form-section">{{ field.label }}</h3>
      <a-alert v-else-if="!supported.has(field.type)" type="warning" show-icon :message="`${field.label}字段类型不受支持`" />
      <a-form-item v-else :label="field.label" :required="field.required" :help="errors[keyOf(field)]" :validate-status="errors[keyOf(field)] ? 'error' : undefined">
        <template v-if="readonly"><span class="readonly-value">{{ displayValue(modelValue[keyOf(field)]) }}</span></template>
        <a-textarea v-else-if="field.type === 'textarea'" :value="modelValue[keyOf(field)] as string" :placeholder="field.placeholder || `请输入${field.label}`" :rows="3" @update:value="setValue(keyOf(field), $event)" />
        <a-input-number v-else-if="field.type === 'number' || field.type === 'money'" :value="modelValue[keyOf(field)] as number" :min="field.min" :max="field.max" :precision="field.precision" :aria-label="field.label" style="width:100%" @update:value="setValue(keyOf(field), $event)" />
        <a-date-picker v-else-if="field.type === 'date'" :value="dateValue(modelValue[keyOf(field)])" :aria-label="field.label" :input-read-only="false" style="width:100%" @update:value="changeDate(keyOf(field), $event)" />
        <a-range-picker v-else-if="field.type === 'date_range'" :value="rangeValue(modelValue[keyOf(field)])" :aria-label="field.label" :input-read-only="false" style="width:100%" @update:value="changeRange(keyOf(field), $event)" />
        <a-radio-group v-else-if="field.type === 'radio'" :value="modelValue[keyOf(field)]" @update:value="setValue(keyOf(field), $event)"><a-radio v-for="option in field.options || []" :key="option" :value="option">{{ option }}</a-radio></a-radio-group>
        <a-checkbox-group v-else-if="field.type === 'checkbox'" :value="modelValue[keyOf(field)] as string[]" :options="field.options" @update:value="setValue(keyOf(field), $event)" />
        <a-select v-else-if="['select', 'user', 'department'].includes(field.type)" :value="modelValue[keyOf(field)]" :aria-label="field.label" allow-clear style="width:100%" @update:value="setValue(keyOf(field), $event)"><a-select-option v-for="option in field.options || []" :key="option" :value="option">{{ option }}</a-select-option></a-select>
        <a-upload v-else-if="field.type === 'attachment'" :file-list="[]" :before-upload="() => false" @change="attachmentChange(field, $event)"><a-button>选择附件</a-button></a-upload>
        <template v-else-if="field.type === 'detail_table'"><a-table :data-source="(modelValue[keyOf(field)] as Record<string, unknown>[]) || []" :pagination="false" size="small" :scroll="{ x: true }"><a-table-column v-for="column in field.columns || []" :key="column.id || column.key" :title="column.label"><template #default="{ record, index }"><a-input-number v-if="column.type === 'number' || column.type === 'money'" :value="record[column.id || column.key] as number" :aria-label="`${field.label} 第${index + 1}行 ${column.label}`" @update:value="updateRow(field, index, column, $event)" /><a-date-picker v-else-if="column.type === 'date'" :value="dateValue(record[column.id || column.key])" :aria-label="`${field.label} 第${index + 1}行 ${column.label}`" @update:value="updateRow(field, index, column, $event?.format('YYYY-MM-DD'))" /><a-select v-else-if="column.type === 'select'" :value="record[column.id || column.key]" :aria-label="`${field.label} 第${index +1}行 ${column.label}`" @update:value="updateRow(field, index, column, $event)"><a-select-option v-for="option in column.options || []" :key="option" :value="option">{{ option }}</a-select-option></a-select><a-input v-else :value="record[column.id || column.key] as string" :aria-label="`${field.label} 第${index +1}行 ${column.label}`" @update:value="updateRow(field, index, column, $event)" /></template></a-table-column><a-table-column title="操作" fixed="right" :width="64"><template #default="{ index }"><a-button type="text" danger :aria-label="`删除第${index + 1}行`" @click="removeRow(field, index)">删除</a-button></template></a-table-column></a-table><a-button type="dashed" block style="margin-top:8px" @click="addRow(field)">添加明细行</a-button></template>
        <a-input v-else :value="modelValue[keyOf(field)] as string" :placeholder="field.placeholder || `请输入${field.label}`" :aria-label="field.label" @update:value="setValue(keyOf(field), $event)" />
      </a-form-item>
    </template>
  </a-form>
</template>

<style scoped>
.applicant-info { margin-bottom: 20px; } .form-section { border-bottom: 1px solid #d9e2e8; padding-bottom: 8px; margin: 24px 0 12px; } .readonly-value { white-space: pre-wrap; } :deep(.ant-table-wrapper) { overflow-x: auto; }
</style>
