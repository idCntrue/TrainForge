import type { ViewKey } from './navigation'

export type NavigationDecision = 'navigate' | 'stay' | 'confirm'

export function navigationDecision(pendingCount: number, current: ViewKey, target: ViewKey): NavigationDecision {
  if (current === target) return 'stay'
  return pendingCount > 0 ? 'confirm' : 'navigate'
}
