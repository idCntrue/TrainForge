import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

describe('React 19 Ant Design compatibility', () => {
  it('loads the Ant Design React 19 patch before rendering the app', () => {
    const mainPath = fileURLToPath(new URL('./main.tsx', import.meta.url))
    const source = readFileSync(mainPath, 'utf8')

    expect(source).toContain("import '@ant-design/v5-patch-for-react-19'")
    expect(source.indexOf("import '@ant-design/v5-patch-for-react-19'")).toBeLessThan(
      source.indexOf("import App from './App'"),
    )
  })
})
