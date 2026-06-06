<script setup lang="ts">
import { ref } from 'vue'
import Enroll from './views/Enroll.vue'
import Verify from './views/Verify.vue'
import Logs from './views/Logs.vue'

const tab = ref('verify')
</script>

<template>
  <n-config-provider>
    <n-message-provider>
      <div class="layout">
        <n-page-header title="掌纹识别门禁" subtitle="注册 · 验证 · 日志" />
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
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}
</style>
