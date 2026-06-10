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
const tabs = [
  { key: 'enroll', label: '注册' },
  { key: 'verify', label: '验证' },
  { key: 'logs', label: '日志' },
]
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
        <div class="topbar-wrapper">
          <div class="topbar">
            <span class="topbar-brand">掌纹识别门禁</span>
            <div class="topbar-right">
              <div v-if="hardware" class="hw-pill" :class="hwIndicator.cls" :title="hwIndicator.label" aria-live="polite">
                <span class="hw-dot"></span>
                <span class="hw-label">{{ hwIndicator.label }}</span>
              </div>
              <ThemeToggle />
            </div>
          </div>
        </div>
        <!-- 填充药丸标签 -->
        <div class="pill-tabs">
          <button
            v-for="t in tabs"
            :key="t.key"
            class="pill-tab"
            :class="{ active: tab === t.key }"
            @click="tab = t.key"
          >{{ t.label }}</button>
        </div>

        <div class="tab-content">
          <Enroll v-if="tab === 'enroll'" />
          <Verify v-else-if="tab === 'verify'" />
          <Logs v-else />
        </div>
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<style scoped>
.layout {
  max-width: 1200px;
  margin: 0 auto;
  padding: 100px 24px 80px;
  animation: layout-fade-in 0.4s var(--ease-out-expo) both;
}

/* 浮动玻璃药丸顶栏 */
.topbar-wrapper {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  width: calc(100% - 32px);
  max-width: 1200px;
  animation: topbar-slide-down 0.6s var(--ease-out-expo) both;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: rgba(var(--color-bg-rgb), 0.7);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  border: 1px solid var(--color-border-hairline);
  border-radius: var(--radius-pill);
  box-shadow:
    0 1px 2px rgba(26,23,20,0.03),
    0 4px 16px rgba(26,23,20,0.04),
    0 12px 40px rgba(26,23,20,0.03);
}
.dark .topbar {
  box-shadow:
    0 1px 2px rgba(0,0,0,0.2),
    0 4px 16px rgba(0,0,0,0.3),
    0 12px 40px rgba(0,0,0,0.2);
}

@keyframes topbar-slide-down {
  from { opacity: 0; transform: translateX(-50%) translateY(-24px); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0); }
}

@keyframes layout-fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.topbar-brand {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--color-text);
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 硬件状态药丸 */
.hw-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 500;
  cursor: default;
  transition: all var(--duration-fast) var(--ease-out-expo);
}
.hw-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
  animation: hw-pulse 2s var(--ease-out-expo) infinite;
}
.hw-label {
  white-space: nowrap;
}
.hw-disabled {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border);
  color: var(--color-faint);
}
.hw-disabled .hw-dot { background: var(--color-faint); animation: none; }
.hw-connected {
  background: var(--color-success-soft);
  border: 1px solid rgba(22,163,74,0.12);
  color: var(--color-state-grasped);
}
.hw-connected .hw-dot { background: var(--color-state-grasped); box-shadow: 0 0 8px var(--color-state-grasped); }
.hw-error {
  background: var(--color-danger-soft);
  border: 1px solid rgba(220,38,38,0.12);
  color: var(--color-danger);
}
.hw-error .hw-dot { background: var(--color-danger); box-shadow: 0 0 8px var(--color-danger); }

@keyframes hw-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50%      { transform: scale(0.8); opacity: 0.5; }
}

/* 填充药丸标签 */
.pill-tabs {
  display: inline-flex;
  gap: 4px;
  background: var(--color-surface-sunken);
  border-radius: var(--radius-pill);
  padding: 4px;
  margin-bottom: 28px;
}
.pill-tab {
  padding: 7px 22px;
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-sans);
  color: var(--color-muted);
  background: transparent;
  border: none;
  border-radius: var(--radius-pill);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out-expo);
}
.pill-tab:hover:not(.active) {
  color: var(--color-text);
  background: rgba(26,23,20,0.04);
}
.dark .pill-tab:hover:not(.active) {
  background: rgba(255,255,255,0.06);
}
.pill-tab.active {
  color: #fff;
  background: var(--color-text);
  box-shadow: 0 1px 3px rgba(26,23,20,0.15);
}
.dark .pill-tab.active {
  box-shadow: 0 1px 3px rgba(0,0,0,0.35);
}

.tab-content {
  animation: tab-fade 0.3s var(--ease-out-expo) both;
}
@keyframes tab-fade {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
