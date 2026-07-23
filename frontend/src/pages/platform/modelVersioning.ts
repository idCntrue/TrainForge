export function nextPatchVersion(versions: string[]): string {
  const patches = versions
    .map((value) => value.trim().match(/^(\d+)\.(\d+)\.(\d+)$/))
    .filter((match): match is RegExpMatchArray => Boolean(match))
    .map((match) => [Number(match[1]), Number(match[2]), Number(match[3])] as const)
  if (!patches.length) return '1.0.0'
  patches.sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]) || (a[2] - b[2]))
  const latest = patches.at(-1)!
  return `${latest[0]}.${latest[1]}.${latest[2] + 1}`
}
