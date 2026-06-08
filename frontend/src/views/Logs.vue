<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { NButton, NTag, useMessage } from 'naive-ui'
import { api, type ApiUser, type LogRow } from '../api'

const message = useMessage()
const users = ref<ApiUser[]>([])
const logs = ref<LogRow[]>([])
const loading = ref(false)

function formatDate(raw: string): string {
  if (!raw) return '-'
  try {
    const d = new Date(raw)
    if (isNaN(d.getTime())) return raw
    return d.toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return raw
  }
}

const userColumns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '姓名', key: 'name' },
  { title: '模板数', key: 'template_count', width: 90 },
  {
    title: '注册时间',
    key: 'created_at',
    render(row: ApiUser) {
      return formatDate(row.created_at)
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render(row: ApiUser) {
      return h(
        NButton,
        {
          size: 'small', type: 'error', tertiary: true,
          'aria-label': `删除用户 ${row.name}`,
          onClick: () => onDelete(row.id, row.name),
        },
        { default: () => '删除' },
      )
    },
  },
]

const logColumns = [
  { title: 'ID', key: 'id', width: 60 },
  {
    title: '结果',
    key: 'matched',
    width: 90,
    render(row: LogRow) {
      return h(
        NTag,
        { type: row.matched ? 'success' : 'error', size: 'small' },
        { default: () => (row.matched ? '命中' : '未命中') },
      )
    },
  },
  {
    title: '用户',
    key: 'user_name',
    render(row: LogRow) {
      return row.user_name || '-'
    },
  },
  {
    title: '距离',
    key: 'distance',
    render(row: LogRow) {
      return h('span', { class: 'tnum' }, row.distance.toFixed(4))
    },
  },
  {
    title: '时间',
    key: 'created_at',
    render(row: LogRow) {
      return formatDate(row.created_at)
    },
  },
]

async function refresh() {
  loading.value = true
  try {
    ;[users.value, logs.value] = await Promise.all([api.users(), api.logs()])
  } catch (e) {
    message.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

async function onDelete(id: number, name: string) {
  if (!confirm(`确认删除用户「${name}」？此操作不可撤销。`)) return
  try {
    await api.deleteUser(id)
    message.success('已删除')
    await refresh()
  } catch (e) {
    message.error(e instanceof Error ? e.message : '删除失败')
  }
}

onMounted(refresh)
</script>

<template>
  <n-space vertical size="large">
    <div class="logs-header">
      <h2 class="logs-title">用户与识别日志</h2>
      <n-button :loading="loading" @click="refresh">刷新</n-button>
    </div>

    <section>
      <h3 class="section-label">注册用户</h3>
      <n-data-table
        :columns="userColumns"
        :data="users"
        :bordered="false"
        :loading="loading"
        size="small"
      />
    </section>

    <section>
      <h3 class="section-label">识别记录</h3>
      <n-data-table
        :columns="logColumns"
        :data="logs"
        :bordered="false"
        :loading="loading"
        size="small"
      />
    </section>
  </n-space>
</template>

<style scoped>
.logs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.logs-title {
  margin: 0;
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 18px;
  letter-spacing: -0.02em;
  line-height: 1.3;
  color: var(--color-text);
}
.section-label {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-faint);
}
</style>
