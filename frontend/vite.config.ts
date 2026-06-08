import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      imports: [
        'vue',
        { 'naive-ui': ['useMessage', 'useDialog', 'useNotification', 'useLoadingBar'] },
      ],
    }),
    Components({
      resolvers: [NaiveUiResolver()],
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:5000',
      '/video_feed': 'http://localhost:5000',
    },
  },
})
