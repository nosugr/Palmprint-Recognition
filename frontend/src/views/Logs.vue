<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { NButton, NTag, useMessage } from 'naive-ui'
import { api, type ApiUser, type LogRow } from '../api'

const message = useMessage()
const users = ref<ApiUser[]>([])
const logs = ref<LogRow[]>([])
const loading = ref(false)

const userColumns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '姓名', key: 'name' },
  { title: '模板数', key: 'template_count', width: 90 },
  { title: '注册时间', key: 'created_at' },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render(row: ApiUser) {
      return h(
        NButton,
        { size: 'small', type: 'error', tertiary: true, onClick: () => onDelete(row.id) },
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
      return row.distance.toFixed(4)
    },
  },
  { title: '时间', key: 'created_at' },
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

async function onDelete(id: number) {
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
    <n-space justify="space-between">
      <n-text strong>用户与识别日志</n-text>
      <n-button :loading="loading" @click="refresh">刷新</n-button>
    </n-space>
    <n-data-table :columns="userColumns" :data="users" :bordered="false" size="small" />
    <n-data-table :columns="logColumns" :data="logs" :bordered="false" size="small" />
  </n-space>
</template>
