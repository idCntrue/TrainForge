export function formatClassLabel(name: string, displayNames: Record<string, string> = {}) {
  const displayName = displayNames[name]?.trim()
  return displayName && displayName !== name ? `${displayName}（${name}）` : name
}

export function resolveAnnotationTaskId(selectedTaskId?: string, currentImageTaskId?: string) {
  return selectedTaskId || currentImageTaskId
}
