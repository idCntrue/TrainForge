import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export const vendorChunks = {
  react: ['react', 'react-dom'],
  antd: ['antd', '@ant-design/icons', '@ant-design/v5-patch-for-react-19'],
  charts: ['recharts'],
  annotation: ['konva', 'react-konva'],
}

export function manualVendorChunk(id: string): string | undefined {
  const normalized = id.replace(/\\/g, '/')
  if (!normalized.includes('/node_modules/')) return undefined
  if (/\/node_modules\/(react|react-dom|scheduler)\//.test(normalized)) return 'react'
  if (/\/node_modules\/(antd|@ant-design)\//.test(normalized)) return 'antd'
  if (normalized.includes('/node_modules/recharts/')) return 'charts'
  if (/\/node_modules\/(konva|react-konva)\//.test(normalized)) return 'annotation'
  return undefined
}

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: manualVendorChunk,
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
