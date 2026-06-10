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
    const handLabel = res.hand_side === 'L' ? '左手' : res.hand_side === 'R' ? '右手' : ''
    const handInfo = handLabel ? `，检测到${handLabel}` : ''
    message.success(`注册成功：${res.captured} 张，质量 ${(res.quality * 100).toFixed(1)}%${handInfo}`)
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
      <div class="bezel">
        <div class="bezel-core">
          <div>
            <div class="status-row">
              <span class="status-dot-lg" />
              <span class="status-text" :style="{ color: cameraState.color }">{{ cameraState.label }}</span>
            </div>
            <div v-if="cameraState.sub" class="status-sub">{{ cameraState.sub }}</div>
            <div v-if="cameraState.connectionState" class="conn-row">
              <span class="conn-dot" />
              <span>
                {{ cameraState.connectionState === 'connected' ? 'MJPEG 流正常' :
                   cameraState.connectionState === 'reconnecting' ? `重连中 ${cameraState.reconnectAttempts}/${cameraState.maxReconnectAttempts}` :
                   cameraState.connectionState === 'disconnected' ? 'MJPEG 流断开' : '连接中' }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="hint">
        手掌放入左侧画面的虚线框内，自然张开五指，输入姓名后点击注册。系统将连续采集多张掌纹模板入库。
      </div>

      <!-- 表单卡片 -->
      <div class="bezel">
        <div class="bezel-core">
          <div>
            <div class="input-bezel">
              <input id="enroll-name" class="input-core" v-model="name" placeholder="请输入姓名" :disabled="loading" @keyup.enter="onEnroll" />
            </div>
            <button class="cta" :disabled="loading" @click="onEnroll">
              <span>{{ loading ? '采集中…' : '开始注册' }}</span>
              <span class="cta-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>
              </span>
            </button>
            <p class="form-hint">需要采集 5 张掌纹图像</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.enroll-layout {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 24px;
  align-items: start;
  padding: 0;
}

.enroll-camera {
  min-width: 0;
  animation: slide-in-left 0.5s var(--ease-out-expo) 0.1s both;
}

.enroll-sidebar {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.enroll-sidebar > :deep(*) {
  animation:
    slide-in-right 0.5s var(--ease-out-expo) both,
    stagger-up 0.4s var(--ease-out-expo) both;
}

.enroll-sidebar > :deep(*:nth-child(1)) { animation-delay: 0.15s, 0.2s; }
.enroll-sidebar > :deep(*:nth-child(2)) { animation-delay: 0.22s, 0.28s; }
.enroll-sidebar > :deep(*:nth-child(3)) { animation-delay: 0.29s, 0.36s; }

/* 状态卡片 */
.status-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-dot-lg {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-state-grasped);
  box-shadow: 0 0 12px var(--color-state-grasped);
  flex-shrink: 0;
  animation: state-pulse 2s var(--ease-out-expo) infinite;
}

.status-text {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--color-state-grasped);
}

.status-sub {
  font-size: 13px;
  color: var(--color-faint);
  margin-top: 4px;
}

.conn-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-faint);
  font-variant-numeric: tabular-nums;
}

.conn-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-state-grasped);
  box-shadow: 0 0 6px var(--color-state-grasped);
}

.hint {
  font-size: 13px;
  color: var(--color-muted);
  line-height: 1.7;
  padding: 14px 18px;
  background: var(--color-surface-sunken);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-hairline);
}

.form-hint {
  font-size: 12px;
  color: var(--color-faint);
  text-align: center;
  margin: 12px 0 0;
}

@media (max-width: 960px) {
  .enroll-layout {
    grid-template-columns: 1fr;
  }
}
</style>
