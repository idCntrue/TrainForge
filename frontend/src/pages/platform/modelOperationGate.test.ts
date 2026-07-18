import { describe, expect, it, vi } from 'vitest'

import { createOperationGate } from './modelOperationGate'

describe('model operation gate', () => {
  it('runs only one operation until the first one settles', async () => {
    let finish!: () => void
    const pending = new Promise<void>((resolve) => { finish = resolve })
    const operation = vi.fn(() => pending)
    const gate = createOperationGate()

    const first = gate.run(operation)
    const duplicate = await gate.run(operation)

    expect(duplicate).toBe(false)
    expect(operation).toHaveBeenCalledTimes(1)
    finish()
    await first
    expect(await gate.run(async () => undefined)).toBe(true)
  })
})
