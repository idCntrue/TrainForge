export function createOperationGate() {
  let active = false
  return {
    async run(operation: () => Promise<unknown>) {
      if (active) return false
      active = true
      try {
        await operation()
        return true
      } finally {
        active = false
      }
    },
  }
}
