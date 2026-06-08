<script setup lang="ts">
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import { api } from '../api'
import CameraView from '../components/CameraView.vue'
import type { ConnectionState } from '../components/CameraView.vue'

const message = useMessage()
const name = ref('')
const loading = ref(false)

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
  <div class="enroll-layout">
    <!-- 左侧：摄像头 -->
    <div class="enroll-camera">
      <CameraView
        :active="loading"
        :hint="loading ? '正在采集，请保持手掌不动…' : '请将手掌放入框内，自然张开五指'"
        :show-state-card="false"
        @state-change="onCameraStateChange"
      />
    </div>

    <!-- 右侧：状态+表单+说明 -->
    <div class="enroll-sidebar">
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

      <n-card title="注册说明" :bordered="true" class="info-card">
        <p class="info-text">
          手掌放入左侧画面的虚线框内，自然张开五指，输入姓名后点击注册。系统将连续采集多张掌纹模板入库。
        </p>
      </n-card>

      <n-card title="注册信息" :bordered="true" class="form-card">
        <div class="form-group">
          <label for="enroll-name" class="form-label">用户姓名</label>
          <n-input
            id="enroll-name"
            v-model:value="name"
            placeholder="请输入姓名"
            :disabled="loading"
            class="name-input"
            @keyup.enter="onEnroll"
          />
          <n-button
            type="primary"
            size="large"
            :loading="loading"
            class="enroll-btn"
            block
            @click="onEnroll"
          >
            <template #icon>
              <n-icon>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/>
                  <circle cx="12" cy="13" r="4"/>
                </svg>
              </n-icon>
            </template>
            {{ loading ? '采集中…' : '开始注册' }}
          </n-button>
          <p class="form-hint">需要采集 5 张掌纹图像</p>
        </div>
      </n-card>
    </div>
  </div>
</template>

<style scoped>
.enroll-layout {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 24px;
  align-items: start;
}

.enroll-camera {
  min-width: 0;
}

.enroll-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-card .info-text {
  font-size: 14px;
  color: var(--color-muted);
  line-height: 1.6;
  margin: 0;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}

.name-input {
  width: 100%;
}

.enroll-btn {
  width: 100%;
}

.form-hint {
  font-size: 12px;
  color: var(--color-faint);
  text-align: center;
  margin: 0;
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
  .enroll-layout {
    grid-template-columns: 1fr;
  }
}
</style>
