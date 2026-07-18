import type { ReviewStatusFilter } from './bulkSelection'

export type ReviewUrlState = {
  batch: string | null
  status: ReviewStatusFilter
  page: number
  search: string
}

const statuses: ReviewStatusFilter[] = ['all', 'candidate', 'selected', 'rejected']

export function parseReviewUrlState(search: string): ReviewUrlState {
  const params = new URLSearchParams(search)
  const status = params.get('status') as ReviewStatusFilter | null
  const page = Number.parseInt(params.get('page') ?? '1', 10)
  return {
    batch: params.get('batch'),
    status: status && statuses.includes(status) ? status : 'all',
    page: Number.isFinite(page) && page > 0 ? page : 1,
    search: params.get('search') ?? '',
  }
}

export function reviewUrlSearch(state: ReviewUrlState): string {
  const params = new URLSearchParams()
  if (state.batch) params.set('batch', state.batch)
  if (state.status !== 'all') params.set('status', state.status)
  if (state.page > 1) params.set('page', String(state.page))
  if (state.search) params.set('search', state.search)
  const value = params.toString()
  return value ? `?${value}` : ''
}
