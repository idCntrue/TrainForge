type ReleaseVersion = { task_id: string; version: string }

const semver = /^(\d+)\.(\d+)\.(\d+)$/

export function nextDatasetVersion(releases: ReleaseVersion[], taskId: string) {
  const versions = releases
    .filter((release) => release.task_id === taskId)
    .map((release) => release.version.match(semver))
    .filter((match): match is RegExpMatchArray => Boolean(match))
    .map((match) => [Number(match[1]), Number(match[2]), Number(match[3])] as const)
    .sort((left, right) => left[0] - right[0] || left[1] - right[1] || left[2] - right[2])
  const latest = versions.at(-1)
  return latest ? `${latest[0]}.${latest[1]}.${latest[2] + 1}` : '0.1.0'
}

const pad = (value: number, length = 2) => String(value).padStart(length, '0')

export function createNativeExportName(now = new Date()) {
  const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
  const time = `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}-${pad(now.getMilliseconds(), 3)}`
  return `native-reviewed-${date}-${time}`
}
