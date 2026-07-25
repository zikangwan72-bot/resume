<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { FileSearchOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import api from '@/api/client'
import PageBackButton from '@/components/PageBackButton.vue'
const router = useRouter(); const jobs = ref<any[]>([]); const applications = ref<any[]>([])
onMounted(async()=>{try{jobs.value=(await api.get('/api/v1/recruitment/jobs')).data.data; applications.value=(await api.get('/api/v1/recruitment/applications')).data.data}catch{message.error('招聘数据加载失败')}})
</script>
<template><div class="page-frame business-page"><header class="page-heading"><div><p class="eyebrow">RECRUITMENT SYSTEM</p><h1>招聘系统</h1><p>学生投递端与招聘管理端已经拆开，数据通过后端 API 持久化。</p></div><PageBackButton/></header><section class="metric-grid"><a-card class="metric-card" :bordered="false"><FileSearchOutlined/><span>开放岗位</span><strong>{{jobs.filter(item=>item.status==='开放').length}}</strong></a-card><a-card class="metric-card" :bordered="false"><TeamOutlined/><span>候选人总数</span><strong>{{applications.length}}</strong></a-card><a-card class="metric-card" :bordered="false"><UserOutlined/><span>待初筛</span><strong>{{applications.filter(item=>item.status==='待初筛').length}}</strong></a-card></section><section class="business-grid two-columns"><a-card class="plain-panel" :bordered="false"><p class="eyebrow">C-SIDE</p><h2>学生投递端</h2><p>浏览开放岗位，填写基本信息和简历文本，提交后可以查看投递记录。</p><a-button type="primary" @click="router.push('/recruitment/student')">进入学生端</a-button></a-card><a-card class="plain-panel" :bordered="false"><p class="eyebrow">B-SIDE</p><h2>招聘管理端</h2><p>管理岗位、查看候选人池、记录人工初筛状态。AI 暂未启用。</p><a-button type="primary" @click="router.push('/recruitment/admin')">进入管理端</a-button></a-card></section></div></template>
