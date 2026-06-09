<script setup lang="ts">
import { useTheme } from '../composables/useTheme'

const { theme, toggle } = useTheme()
</script>

<template>
  <button
    type="button"
    class="theme-toggle"
    :aria-label="theme === 'dark' ? '切换到亮色主题' : '切换到暗色主题'"
    :title="theme === 'dark' ? '切换到亮色主题' : '切换到暗色主题'"
    @click="toggle"
  >
    <!-- 暗色模式下显示太阳（点击切回亮色） -->
    <svg
      v-if="theme === 'dark'"
      xmlns="http://www.w3.org/2000/svg"
      width="18" height="18" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" stroke-width="1.6"
      stroke-linecap="round" stroke-linejoin="round"
    >
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 3v1.8M12 19.2V21M4.2 4.2l1.3 1.3M18.5 18.5l1.3 1.3M3 12h1.8M19.2 12H21M4.2 19.8l1.3-1.3M18.5 5.5l1.3-1.3" />
    </svg>
    <!-- 亮色模式下显示月亮（点击切到暗色） -->
    <svg
      v-else
      xmlns="http://www.w3.org/2000/svg"
      width="18" height="18" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" stroke-width="1.6"
      stroke-linecap="round" stroke-linejoin="round"
    >
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a7.5 7.5 0 1 0 10.5 10.5z" />
    </svg>
  </button>
</template>

<style scoped>
.theme-toggle {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
  transition: color var(--duration-fast) var(--ease-out-expo),
              background-color var(--duration-fast) var(--ease-out-expo);
}
.theme-toggle:hover {
  color: var(--color-text);
  background: var(--color-accent-soft);
}
.theme-toggle:active {
  transform: scale(0.92);
}
</style>
