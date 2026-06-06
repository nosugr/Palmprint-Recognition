<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, type PreviewStatus } from '../api'

const props = withDefaults(
  defineProps<{ hint?: string; active?: boolean; guide?: boolean }>(),
  {
    hint: '请将手掌放入框内，自然张开五指',
    active: false,
    guide: true,
  },
)

const feedUrl = '/video_feed'
const failed = ref(false)
const live = ref<PreviewStatus | null>(null)
let timer: number | undefined

async function poll() {
  if (!props.guide || props.active) return
  try {
    live.value = await api.previewStatus()
  } catch {
    live.value = null
  }
}

onMounted(() => {
  if (props.guide) {
    poll()
    timer = window.setInterval(poll, 700)
  }
})
onBeforeUnmount(() => timer && window.clearInterval(timer))
watch(() => props.active, (busy) => { if (busy) live.value = null })

const ready = computed(() => !props.active && !!live.value?.ready)
const showGuideOk = computed(() => props.guide && ready.value)

const displayHint = computed(() => {
  if (props.active) return props.hint
  if (props.guide && live.value) {
    return live.value.ready ? '✓ 手掌位置良好，可以开始' : live.value.reason
  }
  return props.hint
})
</script>

<template>
  <div class="cam" :class="{ active: active || showGuideOk }">
    <img
      :src="feedUrl"
      alt="实时画面"
      class="cam-img"
      @error="failed = true"
      @load="failed = false"
    />
    <div class="overlay">
      <div class="guide" :class="{ ok: showGuideOk }" />
      <span class="badge">
        <span class="dot" :class="{ live: !failed }" />
        {{ failed ? '摄像头未就绪' : '实时画面' }}
      </span>
    </div>
    <div class="hint" :class="{ ok: showGuideOk }">{{ displayHint }}</div>
  </div>
</template>

<style scoped>
.cam {
  position: relative;
  width: 100%;
  max-width: 560px;
  aspect-ratio: 4 / 3;
  border-radius: 12px;
  overflow: hidden;
  background: #0c0c0f;
  border: 2px solid transparent;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.cam.active {
  border-color: #36ad6a;
  box-shadow: 0 0 0 4px rgba(54, 173, 106, 0.15);
}
.cam-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.guide {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 58%;
  aspect-ratio: 1 / 1;
  transform: translate(-50%, -55%);
  border: 2px dashed rgba(255, 255, 255, 0.7);
  border-radius: 14px;
  transition: border-color 0.2s;
}
.guide.ok {
  border-color: #36ad6a;
  border-style: solid;
}
.badge {
  position: absolute;
  top: 10px;
  left: 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  font-size: 12px;
  color: #fff;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 999px;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #888;
}
.dot.live {
  background: #36ad6a;
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.hint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 8px 12px;
  font-size: 13px;
  color: #fff;
  text-align: center;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.6));
}
.hint.ok {
  color: #b6f0cf;
  font-weight: 600;
}
</style>
