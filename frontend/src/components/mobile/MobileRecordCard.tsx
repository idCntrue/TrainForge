import type { ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'

export function MobileRecordCard({ title, subtitle, status, metric, metadata, progress, actions, onClick }: {
  title: ReactNode
  subtitle?: ReactNode
  status?: ReactNode
  metric?: ReactNode
  metadata?: Array<[ReactNode, ReactNode]>
  progress?: ReactNode
  actions?: ReactNode
  onClick: () => void
}) {
  return <article className="mobile-record-card">
    <button type="button" className="mobile-record-main" onClick={onClick}>
    <span className="mobile-record-heading">
      <span>
        <strong>{title}</strong>
        {subtitle && <small>{subtitle}</small>}
      </span>
      {status && <span className="mobile-record-status">{status}</span>}
    </span>
    {progress && <span className="mobile-record-progress">{progress}</span>}
    {metadata?.length ? <span className="mobile-record-metadata">
      {metadata.map(([label, value], index) => <span key={index}><small>{label}</small><strong>{value}</strong></span>)}
    </span> : null}
    <span className="mobile-record-footer">
      <strong>{metric}</strong>
      <ChevronRight size={17} aria-hidden="true" />
    </span>
    </button>
    {actions && <div className="mobile-record-actions">{actions}</div>}
  </article>
}
