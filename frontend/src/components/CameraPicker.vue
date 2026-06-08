<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { api, type CameraInfo } from '../api'

const emit = defineEmits<{ (e: 'switched', index: number): void }>()
const message = useMessage()

const cameras = ref<CameraInfo[]>([])
const currentIndex = ref<number | null>(null)
const selected = ref<number | null>(null)
const probing = ref(false)
const switching = ref(false)

const options = computed(() =>
  cameras.value
    .filter((c) => c.available)
    .map((c) => ({ label: labelFor(c), value: c.index })),
)

function labelFor(c: CameraInfo): string {
  const res = c.width && c.height ? `${c.width}×${c.height}` : '分辨率未知'
  const tag = c.index === currentIndex.value ? ' · 使用中' : ''
  return `摄像头 ${c.index} · ${res}${tag}`
}

async function refresh() {
  probing.value = true
  try {
    const data = await api.cameras()
    cameras.value = data.cameras
    currentIndex.value = data.current_index
    if (selected.value === null) selected.value = data.current_index
  } catch (e) {
    message.error(e instanceof Error ? e.message : '探测失败')
  } finally {
    probing.value = false
  }
}

async function doSwitch() {
  if (selected.value === null) return
  const target = selected.value
  switching.value = true
  try {
    await api.selectCamera(target)
    currentIndex.value = target
    message.success(`已切换到摄像头 ${target}`)
    emit('switched', target)
  } catch (e) {
    message.error(e instanceof Error ? e.message : '切换失败')
  } finally {
    switching.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="picker">
    <span class="lbl">摄像头</span>
    <n-select
      v-model:value="selected"
      :options="options"
      :loading="probing"
      :disabled="probing || switching || options.length === 0"
      :placeholder="probing ? '探测中…' : '无可用摄像头'"
      size="small"
      class="sel"
    />
    <n-button size="small" :loading="probing" :disabled="switching" @click="refresh">
      刷新
    </n-button>
    <n-button
      size="small"
      type="primary"
      :loading="switching"
      :disabled="probing || selected === null || selected === currentIndex"
      @click="doSwitch"
    >
      切换
    </n-button>
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.lbl {
  font-size: 12px;
  color: var(--color-muted);
  white-space: nowrap;
}
.sel {
  flex: 1;
  min-width: 200px;
}
</style>
