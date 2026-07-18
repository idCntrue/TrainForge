import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { MobileRecordCard } from './MobileRecordCard'

describe('MobileRecordCard', () => {
  it('renders semantic record content and a full-card action', () => {
    const onClick = vi.fn()
    const html = renderToStaticMarkup(<MobileRecordCard
      title="Inspection training"
      subtitle="Dataset v1.2.0"
      status={<span>Running</span>}
      metric="68%"
      metadata={[['Device', 'CPU'], ['Epoch', '102 / 150']]}
      actions={<button type="button">More</button>}
      onClick={onClick}
    />)

    expect(html).toContain('class="mobile-record-card"')
    expect(html).toContain('type="button"')
    expect(html).toContain('Inspection training')
    expect(html).toContain('Dataset v1.2.0')
    expect(html).toContain('Device')
    expect(html).toContain('102 / 150')
    expect(html).toContain('68%')
    expect(html).toContain('mobile-record-actions')
    expect(html).toContain('More')
  })
})
