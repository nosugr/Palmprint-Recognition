<script setup lang="ts">
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import { api } from '../api'
import CameraView from '../components/CameraView.vue'

const message = useMessage()
const name = ref('')
const loading = ref(false)

async function onEnroll() {
  if (!name.value.trim()) {
    message.warning('请输入姓名')
    return
  }
  loading.value = true
  try {
    const res = await api.enroll(name.value.trim())
    message.success(`注册成功：${res.captured} 张，质量 ${(res.quality * 100).toFixed(1)}%`)
    name.value = ''
  } catch (e) {
    message.error(e instanceof Error ? e.message : '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <n-space vertical size="large">
    <n-alert type="info" title="注册说明">
      手掌放入下方画面的虚线框内，自然张开五指，输入姓名后点击注册。系统将连续采集多张掌纹模板入库。
    </n-alert>

    <CameraView
      :active="loading"
      :hint="loading ? '正在采集，请保持手掌不动…' : '请将手掌放入框内，自然张开五指'"
    />

    <n-input v-model:value="name" placeholder="姓名" :disabled="loading" @keyup.enter="onEnroll" />
    <n-button type="primary" size="large" :loading="loading" @click="onEnroll">
      {{ loading ? '采集中…' : '开始注册' }}
    </n-button>
  </n-space>
</template>
