import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  // 单元测试配置。用 node 环境而不是 jsdom：目前测的都是纯函数
  // （金额格式化、月份计算），不需要 DOM，跑得更快、依赖更少。
  // 以后要测组件，把 environment 换成 'jsdom' 并装 jsdom 即可。
  test: {
    environment: 'node',
    include: ['src/**/*.test.js'],
  },
})
