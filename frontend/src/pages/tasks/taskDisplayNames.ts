export type TaskDisplayNameRow = {
  classId: number
  className: string
  displayName: string
}

export function taskDisplayNameRows(classes: string[], displayNames: Record<string, string>): TaskDisplayNameRow[] {
  return classes.map((className, classId) => ({
    classId,
    className,
    displayName: displayNames[className] ?? '',
  }))
}

export function buildDisplayNamePayload(rows: TaskDisplayNameRow[]) {
  return Object.fromEntries(
    rows
      .map((row) => [row.className, row.displayName.trim()] as const)
      .filter(([, displayName]) => Boolean(displayName)),
  )
}
