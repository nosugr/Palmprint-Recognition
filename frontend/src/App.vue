<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { darkTheme } from 'naive-ui'
import Enroll from './views/Enroll.vue'
import Verify from './views/Verify.vue'
import Logs from './views/Logs.vue'
import ThemeToggle from './components/ThemeToggle.vue'
import { useTheme } from './composables/useTheme'
import { api, type HardwareStatus } from './api'

const tab = ref('enroll')
const { theme } = useTheme()
const naiveTheme = computed(() => (theme.value === 'dark' ? darkTheme : null))

// 硬件状态轮询
const hardware = ref<HardwareStatus | null>(null)
let healthTimer: ReturnType<typeof setInterval> | null = null

async function fetchHealth() {
  try {
    const resp = await api.health()
    hardware.value = resp.hardware
  } catch {
    // 静默失败，保持上次状态
  }
}

onMounted(() => {
  fetchHealth()
  healthTimer = setInterval(fetchHealth, 5000)
})

onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
})

// 三态指示灯计算属性
const hwIndicator = computed(() => {
  const hw = hardware.value
  if (!hw || !hw.enabled) {
    return { cls: 'hw-disabled', label: '硬件未启用' }
  }
  if (hw.connected) {
    return { cls: 'hw-connected', label: `已连接 ${hw.port ?? ''}` }
  }
  return { cls: 'hw-error', label: hw.error || '连接失败' }
})
</script>

<template>
  <n-config-provider :theme="naiveTheme">
    <n-message-provider>
      <div class="layout">
        <div class="topbar">
          <n-page-header title="掌纹识别门禁" />
          <div class="topbar-right">
            <!-- 硬件状态心跳点 -->
            <div v-if="hardware" class="hw-indicator" :class="hwIndicator.cls" :title="hwIndicator.label" aria-live="polite">
              <span class="hw-dot"></span>
              <span class="hw-label">{{ hwIndicator.label }}</span>
            </div>
            <ThemeToggle />
          </div>
        </div>
        <n-tabs v-model:value="tab" type="line" animated>
          <n-tab-pane name="enroll" tab="注册">
            <Enroll />
          </n-tab-pane>
          <n-tab-pane name="verify" tab="验证">
            <Verify />
          </n-tab-pane>
          <n-tab-pane name="logs" tab="日志">
            <Logs />
          </n-tab-pane>
        </n-tabs>
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<style scoped>
.layout {
  max-width: 1200px;
  margin: 0 auto;
  padding: 80px 24px 48px;
}
.topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 24px;
  background: rgba(var(--color-bg-rgb), 0.8);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid var(--color-border);
}
.topbar :deep(.n-page-header) {
  flex: 1;
}
.topbar :deep(.n-page-header__title) {
  font-size: 18px !important;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.hw-indicator {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 14px;
  border-radius: 999px;
  background: rgba(var(--color-bg-rgb), 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  cursor: default;
}
.hw-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  animation: hw-heartbeat 1.6s ease-in-out infinite;
}
.hw-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-muted);
  white-space: nowrap;
}
/* 状态色 */
.hw-disabled .hw-dot { background: var(--color-faint); animation: none; }
.hw-connected .hw-dot { background: var(--color-state-grasped); box-shadow: 0 0 8px var(--color-state-grasped); }
.hw-error .hw-dot { background: var(--color-danger); box-shadow: 0 0 8px var(--color-danger); }
@keyframes hw-heartbeat {
  0%, 100% { transform: scale(1); opacity: 1; }
  50%      { transform: scale(0.75); opacity: 0.6; }
}
</style>
