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
      message.success(`识别成功：${result.value.user?.name}（置信度 ${confidencePct.value}%）— 门锁已开`)
    } else {
      message.error(`未匹配（置信度 ${confidencePct.value}%）— 门锁未开`)
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
      <div class="bezel">
        <div class="bezel-core">
          <div>
            <div class="status-row">
              <span class="status-dot-lg" :style="{ background: cameraState.color, boxShadow: `0 0 12px ${cameraState.color}` }"></span>
              <span class="status-text" :style="{ color: cameraState.color }">{{ cameraState.label }}</span>
            </div>
            <div v-if="cameraState.sub" class="status-sub">{{ cameraState.sub }}</div>
            <div v-if="cameraState.connectionState" class="conn-row">
              <span class="conn-dot" :class="cameraState.connectionState"></span>
              <span class="conn-text">
                {{ cameraState.connectionState === 'connected' ? '摄像头已连接' :
                   cameraState.connectionState === 'reconnecting' ? `重连中 ${cameraState.reconnectAttempts}/${cameraState.maxReconnectAttempts}` :
                   cameraState.connectionState === 'disconnected' ? '连接已断开' : '连接中' }}
              </span>
            </div>
          </div>
        </div>
      </div>
      <button class="cta" :disabled="loading" @click="onVerify">
        <span>{{ loading ? '验证中…' : '验证身份' }}</span>
        <span class="cta-icon">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M8 12l3 3 5-5"/></svg>
        </span>
      </button>

      <Transition name="result-pop">
        <div v-if="result" class="result-card" :class="result.matched ? 'result-success' : 'result-fail'">
          <div class="bezel">
            <div class="bezel-core">
              <div class="result-glow" />
              <n-space vertical size="large" align="center" style="position: relative; z-index: 1;">
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

                <div class="lock-status" :class="result.matched ? 'lock-open' : 'lock-locked'">
                  <span class="lock-icon">{{ result.matched ? '🔓' : '🔒' }}</span>
                  <span>{{ result.matched ? '门锁已开' : '门锁未开' }}</span>
                </div>

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
            </div>
          </div>
        </div>
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
  animation: slide-in-left 0.5s var(--ease-out-expo) 0.1s both;
}

.verify-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.verify-sidebar > :deep(*) {
  animation:
    slide-in-right 0.5s var(--ease-out-expo) both,
    stagger-up 0.4s var(--ease-out-expo) both;
}

.verify-sidebar > :deep(*:nth-child(1)) { animation-delay: 0.15s, 0.2s; }
.verify-sidebar > :deep(*:nth-child(2)) { animation-delay: 0.22s, 0.28s; }
.verify-sidebar > :deep(*:nth-child(3)) { animation-delay: 0.29s, 0.36s; }

.result-card {
  position: relative;
  overflow: hidden;
}

/* 径向光晕背景 */
.result-glow {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  z-index: 0;
  opacity: 0;
  animation: glow-in 0.6s 0.2s var(--ease-out-expo) forwards;
}

.result-success .result-glow {
  background: radial-gradient(ellipse at center, var(--color-state-grasped), transparent 70%);
  opacity: 0;
}

.result-fail .result-glow {
  background: radial-gradient(ellipse at center, var(--color-danger), transparent 70%);
  opacity: 0;
}

@keyframes glow-in {
  from { opacity: 0; }
  to   { opacity: 0.1; }
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
/* 结果卡片弹出动画 */
.result-pop-enter-active {
  animation: result-pop-in 0.45s var(--ease-spring);
}

@keyframes result-pop-in {
  0%   { opacity: 0; transform: scale(0.8); }
  60%  { transform: scale(1.04); }
  100% { opacity: 1; transform: scale(1); }
}

/* 门锁状态 */
.lock-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.lock-open {
  color: var(--color-state-grasped);
}
.lock-locked {
  color: var(--color-danger);
}
.lock-icon {
  font-size: 24px;
  display: inline-block;
}
.lock-open .lock-icon {
  animation: lock-bounce 0.6s 0.3s var(--ease-spring) both;
}
.lock-locked .lock-icon {
  animation: lock-shake 0.5s 0.3s ease-in-out both;
}

@keyframes lock-bounce {
  0%   { transform: scale(1) rotate(0deg); }
  30%  { transform: scale(1.3) rotate(-10deg); }
  50%  { transform: scale(0.9) rotate(5deg); }
  70%  { transform: scale(1.1) rotate(-3deg); }
  100% { transform: scale(1) rotate(0deg); }
}

@keyframes lock-shake {
  0%, 100% { transform: translateX(0); }
  15%      { transform: translateX(-6px); }
  30%      { transform: translateX(5px); }
  45%      { transform: translateX(-4px); }
  60%      { transform: translateX(3px); }
  75%      { transform: translateX(-2px); }
  90%      { transform: translateX(1px); }
}

/* 状态卡片样式 */
.status-row { display: flex; align-items: center; gap: 10px; }
.status-dot-lg { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; animation: state-pulse 2s var(--ease-out-expo) infinite; }
.status-text { font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
.status-sub { font-size: 13px; color: var(--color-faint); margin-top: 4px; }
.conn-row { display: flex; align-items: center; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--color-border); font-size: 12px; color: var(--color-faint); font-variant-numeric: tabular-nums; }
.conn-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.conn-dot.connected { background: var(--color-state-grasped); box-shadow: 0 0 6px var(--color-state-grasped); }
.conn-dot.connecting { background: var(--color-faint); animation: state-pulse 2s var(--ease-out-expo) infinite; }
.conn-dot.disconnected { background: var(--color-danger); }
.conn-dot.reconnecting { background: var(--color-state-search); animation: state-pulse 2s var(--ease-out-expo) infinite; }
.conn-text { font-size: 12px; color: var(--color-faint); }

@keyframes state-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(0.85); }
}

@media (max-width: 960px) {
  .verify-layout {
    grid-template-columns: 1fr;
  }
}
</style>
