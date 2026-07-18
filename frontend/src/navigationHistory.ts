export type HistoryTravel = { restoreDelta: number; resumeDelta: number }

export function historyTravel(currentPosition?: number, targetPosition?: number): HistoryTravel | null {
  if (currentPosition == null || targetPosition == null || currentPosition === targetPosition) return null
  return {
    restoreDelta: currentPosition - targetPosition,
    resumeDelta: targetPosition - currentPosition,
  }
}
