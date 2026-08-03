import { describe, expect, it } from 'vitest'
import { manualVendorChunk, vendorChunks } from '../vite.config'

describe('vendor chunk policy', () => {
  it('keeps large stable dependency groups out of the application entry chunk', () => {
    expect(vendorChunks).toEqual({
      react: ['react', 'react-dom'],
      antd: ['antd', '@ant-design/icons', '@ant-design/v5-patch-for-react-19'],
      charts: ['recharts'],
      annotation: ['konva', 'react-konva'],
    })
    expect(manualVendorChunk('C:/project/node_modules/react-dom/client.js')).toBe('react')
    expect(manualVendorChunk('C:/project/node_modules/scheduler/index.js')).toBe('react')
    expect(manualVendorChunk('C:/project/node_modules/antd/es/button/index.js')).toBe('antd')
    expect(manualVendorChunk('C:/project/node_modules/recharts/es6/chart/LineChart.js')).toBe('charts')
    expect(manualVendorChunk('C:/project/node_modules/react-konva/es/ReactKonva.js')).toBe('annotation')
    expect(manualVendorChunk('C:/project/src/App.tsx')).toBeUndefined()
  })
})
