import type { DatasetReleaseSummary } from '../../api'

export function formatDatasetReleaseLabel(release: DatasetReleaseSummary): string {
  const displayName = release.display_name?.trim() || release.task_id
  return `${displayName} · v${release.version} · ${release.task_id}`
}

export function resolveDatasetReleaseLabel(
  releaseId: string,
  releases: DatasetReleaseSummary[],
): string {
  const release = releases.find((candidate) => candidate.id === releaseId)
  return release ? formatDatasetReleaseLabel(release) : releaseId
}
