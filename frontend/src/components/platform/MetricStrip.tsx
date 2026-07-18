import type { LucideIcon } from 'lucide-react'

export interface MetricItem { label: string; value: string | number; detail?: string; icon: LucideIcon; tone?: string }

export function MetricStrip({ items }: { items: MetricItem[] }) {
  return (
    <section className="platform-metric-grid">
      {items.map(({ label, value, detail, icon: Icon, tone = 'green' }) => (
        <div className="platform-metric" key={label}>
          <span className={`platform-metric-icon ${tone}`}><Icon size={19} /></span>
          <div><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>
        </div>
      ))}
    </section>
  )
}
