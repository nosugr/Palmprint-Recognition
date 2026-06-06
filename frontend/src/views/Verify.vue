<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { api, type VerifyResult } from '../api'
import CameraView from '../components/CameraView.vue'

const message = useMessage()
const loading = ref(false)
const result = ref<VerifyResult | null>(null)

const confidencePct = computed(() =>
  result.value ? Math.round(result.value.confidence * 100) : 0,
)
const gaugeColor = computed(() => {
  if (!result.value) return '#888'
  return result.value.matched ? '#36ad6a' : '#d03050'
})

async function onVerify() {
  loading.value = true
  result.value = null
  try {
    result.value = await api.verify()
    if (result.value.matched) {
      message.success(`识别成功：${result.value.user?.name}（置信度 ${confidencePct.value}%）`)
    } else {
      message.error(`未匹配（置信度 ${confidencePct.value}%）`)
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : '验证失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <n-space vertical size="large">
    <CameraView
      :active="loading"
      :hint="loading ? '正在比对，请保持手掌不动…' : '请将手掌放入框内进行验证'"
    />

    <n-button type="primary" size="large" :loading="loading" @click="onVerify">
      {{ loading ? '验证中…' : '验证' }}
    </n-button>

    <n-card v-if="result" :bordered="true">
      <n-space vertical size="large" align="center">
        <n-progress
          type="circle"
          :percentage="confidencePct"
          :color="gaugeColor"
          :stroke-width="10"
          style="width: 140px"
        >
          <div class="gauge-inner">
            <div class="gauge-pct">{{ confidencePct }}%</div>
            <div class="gauge-label">置信度</div>
          </div>
        </n-progress>

        <n-tag :type="result.matched ? 'success' : 'error'" size="large" round>
          {{ result.matched ? `识别为 ${result.user?.name}` : '未识别 / 拒绝' }}
        </n-tag>

        <n-descriptions :column="3" label-placement="top" size="small" class="detail">
          <n-descriptions-item label="匹配距离">
            {{ result.distance.toFixed(4) }}
          </n-descriptions-item>
          <n-descriptions-item label="判定阈值">
            {{ result.threshold.toFixed(4) }}
          </n-descriptions-item>
          <n-descriptions-item label="结果">
            {{ result.matched ? '通过' : '拒绝' }}
          </n-descriptions-item>
        </n-descriptions>
      </n-space>
    </n-card>
  </n-space>
</template>

<style scoped>
.gauge-inner {
  text-align: center;
}
.gauge-pct {
  font-size: 26px;
  font-weight: 600;
}
.gauge-label {
  font-size: 12px;
  color: #888;
}
.detail {
  text-align: center;
}
</style>
