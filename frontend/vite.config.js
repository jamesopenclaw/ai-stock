import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig(() => {
  const isTest = process.env.VITEST === 'true'
  const elementResolver = ElementPlusResolver({
    importStyle: isTest ? false : 'css',
  })

  return {
    plugins: [
      vue(),
      AutoImport({
        imports: ['vue', 'vue-router'],
        resolvers: [elementResolver],
      }),
      Components({
        resolvers: [elementResolver],
      }),
    ],
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true
        }
      }
    },
    test: {
      environment: 'jsdom',
      setupFiles: './tests/setup.js'
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return

            if (id.includes('vue-router')) return 'vendor-vue-router'
            if (id.includes('axios')) return 'vendor-axios'
            if (id.includes('dayjs')) return 'vendor-dayjs'
          },
        }
      }
    }
  }
})
