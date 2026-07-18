import { useMemo, useState } from 'react'
import { Drawer } from 'antd'
import { Database, Gauge, Menu, PlayCircle } from 'lucide-react'

import { navigationLabels, type ViewKey } from '../../navigation'

type MobileSectionKey = 'dashboard' | 'data' | 'training' | 'more'

type MobileNavigationSection = {
  key: MobileSectionKey
  label: string
  icon: typeof Gauge
  children?: ViewKey[]
}

export const mobileNavigationSections: MobileNavigationSection[] = [
  { key: 'dashboard', label: '概览', icon: Gauge },
  { key: 'data', label: '数据', icon: Database, children: ['tasks', 'videos', 'review', 'annotation', 'datasets'] },
  { key: 'training', label: '训练', icon: PlayCircle },
  { key: 'more', label: '更多', icon: Menu, children: ['models', 'inference', 'help', 'system'] },
]

function activeSection(view: ViewKey): MobileSectionKey {
  const grouped = mobileNavigationSections.find((section) => section.children?.includes(view))
  return grouped?.key ?? (view === 'training' ? 'training' : 'dashboard')
}

export function MobileBottomNavigation({ activeView, onNavigate }: {
  activeView: ViewKey
  onNavigate: (view: ViewKey) => void
}) {
  const [openSection, setOpenSection] = useState<MobileNavigationSection>()
  const currentSection = useMemo(() => activeSection(activeView), [activeView])

  const selectSection = (section: MobileNavigationSection) => {
    if (section.children) {
      setOpenSection(section)
      return
    }
    onNavigate(section.key as ViewKey)
  }

  const selectChild = (view: ViewKey) => {
    setOpenSection(undefined)
    onNavigate(view)
  }

  return <>
    <nav className="mobile-bottom-navigation" aria-label="Mobile navigation">
      {mobileNavigationSections.map((section) => {
        const Icon = section.icon
        const selected = currentSection === section.key
        return <button
          key={section.key}
          type="button"
          data-mobile-nav={section.key}
          aria-current={selected ? 'page' : undefined}
          onClick={() => selectSection(section)}
        >
          <Icon size={20} aria-hidden="true" />
          <span>{section.label}</span>
        </button>
      })}
    </nav>
    <Drawer
      className="mobile-navigation-drawer"
      placement="bottom"
      height="auto"
      title={openSection?.label}
      open={Boolean(openSection)}
      onClose={() => setOpenSection(undefined)}
    >
      <div className="mobile-navigation-grid">
        {openSection?.children?.map((view) => <button
          key={view}
          type="button"
          className={view === activeView ? 'active' : ''}
          onClick={() => selectChild(view)}
        >
          {navigationLabels[view]}
        </button>)}
      </div>
    </Drawer>
  </>
}
