import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { MobileBottomNavigation, mobileNavigationSections } from './MobileBottomNavigation'

describe('MobileBottomNavigation', () => {
  it('defines four stable root destinations', () => {
    expect(mobileNavigationSections.map((item) => item.key)).toEqual(['dashboard', 'data', 'training', 'more'])
  })

  it('keeps data and operations destinations available from grouped sheets', () => {
    expect(mobileNavigationSections.find((item) => item.key === 'data')?.children).toEqual([
      'tasks', 'videos', 'review', 'annotation', 'datasets',
    ])
    expect(mobileNavigationSections.find((item) => item.key === 'more')?.children).toEqual([
      'models', 'inference', 'help', 'system',
    ])
  })

  it('renders a fixed-navigation landmark with accessible destinations', () => {
    const html = renderToStaticMarkup(
      <MobileBottomNavigation activeView="training" onNavigate={vi.fn()} />,
    )

    expect(html).toContain('aria-label="Mobile navigation"')
    expect(html).toContain('data-mobile-nav="training"')
    expect(html).toContain('aria-current="page"')
  })
})
