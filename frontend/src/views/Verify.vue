<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { api, type VerifyResult } from '../api'
import CameraView from '../components/CameraView.vue'
import type { ConnectionState } from '../components/CameraView.vue'

const message = useMessage()
const loading = ref(false)
const result = ref<VerifyResult | null>(null)

// 摄像头状态
const cameraState = ref<{
  label: string
  sub?: string
  color: string
  connectionState?: ConnectionState
  reconnectAttempts?: number
  maxReconnectAttempts?: number
  canManualReconnect?: boolean
}>({
  label: '连接中',
  sub: '正在连接摄像头…',
  color: 'var(--color-muted)',
})

function onCameraStateChange(state: {
  label: string
  sub?: string
  color: string
  connectionState: ConnectionState
  reconnectAttempts: number
  maxReconnectAttempts: number
  canManualReconnect: boolean
}) {
  cameraState.value = state
}

const confidencePct = computed(() =>
  result.value ? Math.round(result.value.confidence * 100) : 0,
)
const gaugeColor = computed(() => {
  if (!result.value) return 'var(--color-muted)'
  return result.value.matched ? 'var(--color-state-grasped)' : 'var(--color-danger)'
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
  <div class="verify-layout">
    <!-- 左侧：摄像头 -->
    <div class="verify-camera">
      <CameraView
        :active="loading"
        :hint="loading ? '正在比对，请保持手掌不动…' : '请将手掌放入框内进行验证'"
        :picker="false"
        :show-state-card="false"
        @state-change="onCameraStateChange"
      />
    </div>

    <!-- 右侧：状态+操作+结果 -->
    <div class="verify-sidebar">
      <!-- 状态卡片 -->
      <n-card :bordered="true" class="state-card">
        <div class="state-header">
          <span class="state-dot" :style="{ background: cameraState.color }" />
          <span class="state-eyebrow">当前状态</span>
        </div>
        <div class="state-label" :style="{ color: cameraState.color }">
          {{ cameraState.label }}
        </div>
        <div v-if="cameraState.sub" class="state-sub">{{ cameraState.sub }}</div>
        <!-- 连接状态详情 -->
        <div v-if="cameraState.connectionState" class="connection-info">
          <span class="connection-dot" :class="cameraState.connectionState" />
          <span class="connection-text">
            {{ cameraState.connectionState === 'connected' ? 'MJPEG 流正常' :
               cameraState.connectionState === 'reconnecting' ? `重连中 ${cameraState.reconnectAttempts}/${cameraState.maxReconnectAttempts}` :
               cameraState.connectionState === 'disconnected' ? 'MJPEG 流断开' : '连接中' }}
          </span>
        </div>
      </n-card>
      <n-button
        type="primary"
        size="large"
        :loading="loading"
        block
        @click="onVerify"
      >
        <template #icon>
          <n-icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
              <path d="M8 12l3 3 5-5"/>
            </svg>
          </n-icon>
        </template>
        {{ loading ? '验证中…' : '验证' }}
      </n-button>

      <Transition name="result-fade">
        <n-card v-if="result" :bordered="true" class="result-card">
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
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.verify-layout {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 24px;
  align-items: start;
}

.verify-camera {
  min-width: 0;
}

.verify-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-card {
  transition: all 0.3s ease;
}

.gauge-inner {
  text-align: center;
}
.gauge-pct {
  font-size: 26px;
  font-weight: 500;
  font-family: var(--font-mono);
}
.gauge-label {
  font-size: 12px;
  color: var(--color-muted);
}
.detail {
  text-align: center;
}
.result-fade-enter-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.result-fade-enter-from {
  opacity: 0;
  transform: translateY(12px);
}

/* 状态卡片样式 */
.state-card {
  background: var(--color-surface);
}

.state-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.state-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  animation: state-pulse 1.6s ease-in-out infinite;
}

.state-eyebrow {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--color-faint);
}

.state-label {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.state-sub {
  margin-top: 4px;
  font-size: 13px;
  color: var(--color-muted);
}

@keyframes state-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(0.85); }
}

/* 连接状态信息 */
.connection-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}

.connection-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.connection-dot.connected {
  background: var(--color-state-grasped);
  box-shadow: 0 0 6px var(--color-state-grasped);
}

.connection-dot.connecting {
  background: var(--color-muted);
  animation: state-pulse 1.6s ease-in-out infinite;
}

.connection-dot.disconnected {
  background: var(--color-danger);
}

.connection-dot.reconnecting {
  background: var(--color-state-search);
  animation: state-pulse 1.6s ease-in-out infinite;
}

.connection-text {
  font-size: 12px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 960px) {
  .verify-layout {
    grid-template-columns: 1fr;
  }
}
</style>
