import { createApp } from 'vue'
import {
  create,
  NAlert,
  NButton,
  NConfigProvider,
  NDataTable,
  NInput,
  NMessageProvider,
  NPageHeader,
  NResult,
  NSpace,
  NTabPane,
  NTabs,
  NTag,
  NText,
} from 'naive-ui'
import './style.css'
import App from './App.vue'

const naive = create({
  components: [
    NAlert,
    NButton,
    NConfigProvider,
    NDataTable,
    NInput,
    NMessageProvider,
    NPageHeader,
    NResult,
    NSpace,
    NTabPane,
    NTabs,
    NTag,
    NText,
  ],
})

const app = createApp(App)
app.use(naive)
app.mount('#app')
