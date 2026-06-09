<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import { api, type PreviewStatus } from '../api'
import CameraPicker from './CameraPicker.vue'

// 连接状态类型
export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting'

const props = withDefaults(
  defineProps<{ hint?: string; active?: boolean; guide?: boolean; picker?: boolean; showStateCard?: boolean }>(),
  {
    hint: '请将手掌放入框内，自然张开五指',
    active: false,
    guide: true,
    picker: true,
    showStateCard: true,
  },
)

const emit = defineEmits<{
  stateChange: [state: {
    label: string
    sub?: string
    color: string
    connectionState: ConnectionState
    reconnectAttempts: number
    maxReconnectAttempts: number
    canManualReconnect: boolean
  }]
}>()

const failed = ref(false)
const reloadKey = ref(0)

// ========== 连接状态检测 ==========
const connectionState = ref<ConnectionState>('connecting')
const reconnectAttempts = ref(0)
const MAX_RECONNECT_ATTEMPTS = 10
const RECONNECT_INTERVAL = 3000
const POLL_TIMEOUT_THRESHOLD = 3 // 连续失败次数阈值

let reconnectTimer: number | null = null
let consecutiveFailures = 0

// 自动重连
function startReconnect() {
  if (reconnectTimer || reconnectAttempts.value >= MAX_RECONNECT_ATTEMPTS) return
  connectionState.value = 'reconnecting'

  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    reconnectAttempts.value++
    reloadKey.value++ // 强制 <img> 重连
  }, RECONNECT_INTERVAL)
}

function stopReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

// 手动重连（用户点击）
function manualReconnect() {
  reconnectAttempts.value = 0
  consecutiveFailures = 0
  connectionState.value = 'connecting'
  reloadKey.value++
}

// 图片加载事件处理
function onImageLoad() {
  failed.value = false
  consecutiveFailures = 0
  if (connectionState.value !== 'connected') {
    connectionState.value = 'connected'
    reconnectAttempts.value = 0
    stopReconnect()
  }
}

function onImageError() {
  failed.value = true
  consecutiveFailures++
  if (consecutiveFailures >= POLL_TIMEOUT_THRESHOLD) {
    connectionState.value = 'disconnected'
    startReconnect()
  }
}

// 调试：显示后端识别到的手掌轮廓/指尖几何（叠加在视频流上）
const debug = ref(false)
const feedUrl = computed(() => (debug.value ? '/video_feed?debug=1' : '/video_feed'))
function onDebugToggle() {
  failed.value = false
  consecutiveFailures = 0
  reloadKey.value += 1 // 切换流地址，强制 <img> 重连
}

// 摄像头切换/重连的瞬时提示（在状态卡显示一会儿）
const switchInfo = ref<string | null>(null)
let switchTimer: number | undefined

function onCameraSwitched(index: number) {
  // 后端已热切换；强制 <img> 重连 MJPEG 流，立即拉到新摄像头画面。
  failed.value = false
  consecutiveFailures = 0
  connectionState.value = 'connecting'
  stopReconnect()
  reconnectAttempts.value = 0
  reloadKey.value += 1
  switchInfo.value = `正在重连摄像头 ${index}…`
  if (switchTimer) window.clearTimeout(switchTimer)
  switchTimer = window.setTimeout(() => { switchInfo.value = null }, 2500)
  poll()
}

const live = ref<PreviewStatus | null>(null)
let pollTimer: number | undefined

async function poll() {
  if (!props.guide || props.active) return
  try {
    const result = await api.previewStatus()
    live.value = result
    consecutiveFailures = 0 // 轮询成功，重置失败计数
    // 轮询成功且摄像头状态正常，标记为已连接
    if (result.status !== 'no_camera' && connectionState.value !== 'connected') {
      connectionState.value = 'connected'
      reconnectAttempts.value = 0
      stopReconnect()
    }
  } catch {
    live.value = null
    consecutiveFailures++
    if (consecutiveFailures >= POLL_TIMEOUT_THRESHOLD && connectionState.value === 'connected') {
      connectionState.value = 'disconnected'
      startReconnect()
    }
  }
}

onMounted(() => {
  if (props.guide) {
    poll()
    pollTimer = window.setInterval(poll, 700)
  }
})

// 统一的清理逻辑
onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer)
  if (switchTimer) window.clearTimeout(switchTimer)
  stopReconnect()
})

watch(() => props.active, (busy) => { if (busy) live.value = null })

const ready = computed(() => !props.active && !!live.value?.ready)
const showGuideOk = computed(() => props.guide && ready.value)

// 检测状态 → 标签/颜色（颜色取自 SpiRob 的状态色 token）
const STATUS_META: Record<string, { label: string; color: string }> = {
  ok: { label: '位置良好', color: 'var(--color-state-grasped)' },
  no_hand: { label: '请放置手掌', color: 'var(--color-muted)' },
  bad_pose: { label: '请张开手掌', color: 'var(--color-state-search)' },
  out_of_bounds: { label: '请居中', color: 'var(--color-state-locked)' },
  no_camera: { label: '摄像头未就绪', color: 'var(--color-danger)' },
}

// 调试模式下在状态卡显示 solidity，便于看着调阈值
const solidityText = computed(() => {
  if (!debug.value || props.active) return ''
  const s = live.value?.solidity
  return s == null ? '' : `solidity ${s.toFixed(2)}（阈值 ≤0.90 才算张开手）`
})

// 连接状态元信息
const CONNECTION_META: Record<ConnectionState, { label: string; color: string }> = {
  connecting: { label: '连接中', color: 'var(--color-muted)' },
  connected: { label: '已连接', color: 'var(--color-state-grasped)' },
  disconnected: { label: '连接断开', color: 'var(--color-danger)' },
  reconnecting: { label: '重连中', color: 'var(--color-state-search)' },
}

// 是否可以手动重连
const canManualReconnect = computed(() =>
  connectionState.value === 'disconnected' && reconnectAttempts.value >= MAX_RECONNECT_ATTEMPTS
)

// 状态卡 / 徽标统一的当前状态：忙(比对中) > 切换中 > 连接异常 > 实时检测 > 连接中
const stateInfo = computed(() => {
  if (props.active) {
    return { label: '处理中', sub: props.hint, color: 'var(--color-accent)' }
  }
  if (switchInfo.value) {
    return { label: '切换摄像头', sub: switchInfo.value, color: 'var(--color-state-aligning)' }
  }
  // 连接异常状态
  if (connectionState.value === 'disconnected' || connectionState.value === 'reconnecting') {
    const meta = CONNECTION_META[connectionState.value]
    const sub = connectionState.value === 'reconnecting'
      ? `正在重连... (${reconnectAttempts.value}/${MAX_RECONNECT_ATTEMPTS})`
      : reconnectAttempts.value >= MAX_RECONNECT_ATTEMPTS
        ? '重连失败，请检查摄像头连接后点击重试'
        : 'MJPEG 流已断开，正在尝试重连'
    return { label: meta.label, sub, color: meta.color }
  }
  if (props.guide && live.value) {
    const meta = STATUS_META[live.value.status] ?? STATUS_META.no_hand
    return { label: meta.label, sub: live.value.reason, color: meta.color }
  }
  if (failed.value) {
    return { label: '摄像头未就绪', sub: '请检查摄像头连接或在上方切换设备', color: 'var(--color-danger)' }
  }
  return { label: '连接中', sub: '正在连接摄像头…', color: 'var(--color-muted)' }
})

// 向父组件暴露状态变化（节流 emit）
let lastEmittedState = ''
watchEffect(() => {
  const state = {
    ...stateInfo.value,
    connectionState: connectionState.value,
    reconnectAttempts: reconnectAttempts.value,
    maxReconnectAttempts: MAX_RECONNECT_ATTEMPTS,
    canManualReconnect: canManualReconnect.value,
  }
  const stateKey = JSON.stringify(state)
  if (stateKey !== lastEmittedState) {
    lastEmittedState = stateKey
    emit('stateChange', state)
  }
})
</script>

<template>
  <div class="cam-wrap">
    <CameraPicker v-if="picker" @switched="onCameraSwitched" />

    <div class="debug-row">
      <n-switch v-model:value="debug" size="small" @update:value="onDebugToggle" />
      <span class="debug-lbl">显示识别轮廓</span>
    </div>

    <div class="cam-bezel" :class="{ active: active || showGuideOk }">
      <div class="cam-core">
        <img
          :key="reloadKey"
          :src="feedUrl"
          alt="摄像头实时画面"
          class="cam-img"
          @error="onImageError"
          @load="onImageLoad"
        />
        <div class="overlay">
          <!-- HUD 四角角标 -->
          <div class="hud-corner hud-corner-tl" />
          <div class="hud-corner hud-corner-tr" />
          <div class="hud-corner hud-corner-bl" />
          <div class="hud-corner hud-corner-br" />
          <!-- 引导框 -->
          <div class="guide" :class="{ ok: showGuideOk }" />
          <!-- HUD 药丸：毛玻璃状态徽标 -->
          <div class="hud-pill-badge" :style="{ '--pill-accent': stateInfo.color }">
            <span class="hud-pill-dot" />
            <span class="hud-pill-text">{{ stateInfo.label }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 框下方状态卡 -->
    <section v-if="showStateCard" class="bezel">
      <div class="bezel-core">
        <div>
          <div class="state-row">
            <span class="state-dot-lg" :style="{ background: stateInfo.color, boxShadow: `0 0 12px ${stateInfo.color}` }"></span>
            <span class="state-label-text" :style="{ color: stateInfo.color }">{{ stateInfo.label }}</span>
          </div>
          <div class="state-sub">{{ stateInfo.sub }}</div>
          <div v-if="solidityText" class="state-metric">{{ solidityText }}</div>
          <n-button v-if="canManualReconnect" type="primary" size="small" class="reconnect-btn" @click="manualReconnect">重新连接</n-button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.cam-wrap {
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
}
.cam-bezel {
  position: relative;
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  background: var(--color-border);
  border: 1px solid var(--color-border-hairline);
  border-radius: var(--radius-xl);
  padding: 6px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.02), 0 8px 24px rgba(0,0,0,0.03);
  transition: box-shadow 0.2s var(--ease-out-expo);
}
.cam-bezel.active {
  box-shadow: 0 2px 4px rgba(0,0,0,0.02), 0 8px 24px rgba(0,0,0,0.03), 0 0 0 3px var(--color-accent-glow);
}
.cam-core {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: calc(var(--radius-xl) - 4px);
  overflow: hidden;
  background: #0a0a0c;
  box-shadow: inset 0 1px 1px rgba(255,255,255,0.03);
}
.cam-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
}
.overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

/* 引导框：几何必须与后端 config.ROI_GUIDE_CX/CY/SIDE 严格一致 */
.guide {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 55%;
  aspect-ratio: 1 / 1;
  transform: translate(-50%, -50%);
  border: 1.5px dashed rgba(255, 255, 255, 0.5);
  border-radius: var(--radius-sm);
  transition: border-color var(--duration-med) var(--ease-out-expo), box-shadow var(--duration-med) var(--ease-out-expo);
}
.guide.ok {
  border-color: var(--color-state-grasped);
  border-style: solid;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.2), 0 0 24px -4px var(--color-state-grasped);
}

/* HUD 药丸徽标（毛玻璃） */
.hud-pill-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  border-radius: var(--radius-pill);
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #fff;
  background: rgba(10, 10, 12, 0.65);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.hud-pill-badge .hud-pill-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--pill-accent, #fff);
  box-shadow: 0 0 8px var(--pill-accent, #fff);
  animation: hud-pulse 1.6s var(--ease-out-expo) infinite;
}

/* 状态卡 */
.state-row { display: flex; align-items: center; gap: 10px; }
.state-dot-lg { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; animation: hud-pulse 2s var(--ease-out-expo) infinite; }
.state-label-text { font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
.state-sub { margin-top: 4px; font-size: 13px; color: var(--color-faint); }
.state-metric {
  margin-top: 6px;
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--color-faint);
}
.reconnect-btn {
  margin-top: 12px;
}
.debug-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.debug-lbl {
  font-size: 12px;
  color: var(--color-muted);
}
</style>
