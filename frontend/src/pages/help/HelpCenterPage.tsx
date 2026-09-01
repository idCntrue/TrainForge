import { Fragment, useMemo, useState, type ReactNode } from 'react'
import { Input, Tag } from 'antd'
import { BookOpen, Search } from 'lucide-react'

import { helpChapters, searchHelpHits } from './helpContent'

function Highlight({ text, query }: { text: string; query: string }) {
  const keyword = query.trim()
  if (!keyword) return <>{text}</>
  const lower = text.toLocaleLowerCase()
  const needle = keyword.toLocaleLowerCase()
  const parts: ReactNode[] = []
  let cursor = 0
  let index = lower.indexOf(needle)
  let key = 0
  while (index !== -1) {
    if (index > cursor) parts.push(<Fragment key={key++}>{text.slice(cursor, index)}</Fragment>)
    parts.push(<mark key={key++}>{text.slice(index, index + keyword.length)}</mark>)
    cursor = index + keyword.length
    index = lower.indexOf(needle, cursor)
  }
  if (cursor < text.length) parts.push(<Fragment key={key++}>{text.slice(cursor)}</Fragment>)
  return parts.length ? <>{parts}</> : <>{text}</>
}

export default function HelpCenterPage() {
  const [query, setQuery] = useState('')
  const [activeId, setActiveId] = useState(helpChapters[0].id)
  const hits = useMemo(() => searchHelpHits(query), [query])
  const active = hits.find((hit) => hit.chapter.id === activeId) ?? hits[0]
  const sections = active ? (active.matchedSections.length ? active.matchedSections : active.chapter.sections) : []
  const searching = query.trim().length > 0

  return <div className="help-center">
    <header className="help-header">
      <div><span className="help-eyebrow"><BookOpen size={15} /> 离线用户手册</span><h2>帮助中心</h2><p>从数据准备到云端部署的完整 TrainForge 操作手册。</p></div>
      <Input allowClear prefix={<Search size={15} />} placeholder="搜索操作、错误或术语" value={query} onChange={(event) => setQuery(event.target.value)} />
    </header>
    <div className="help-layout">
      <nav className="help-nav" aria-label="帮助章节">
        <strong>文档目录</strong>
        {hits.map((hit) => <button className={hit.chapter.id === active?.chapter.id ? 'active' : ''} key={hit.chapter.id} onClick={() => setActiveId(hit.chapter.id)}>
          <span><Highlight text={hit.chapter.title} query={query} /></span>
          <small><Highlight text={hit.chapter.summary} query={query} /></small>
          {searching && hit.matchedSections.length > 0 && <em className="help-hit-sections">{hit.matchedSections.map((section) => section.title).join(' · ')}</em>}
        </button>)}
        {hits.length === 0 && <p>没有找到相关内容，请尝试更短的关键词。</p>}
      </nav>
      <main className="help-document">
        {active && <>
          <div className="help-document-title"><Tag color="green">内置文档</Tag><h1><Highlight text={active.chapter.title} query={query} /></h1><p><Highlight text={active.chapter.summary} query={query} /></p></div>
          {sections.map((section) => <section id={section.id} key={section.id}><h2><Highlight text={section.title} query={query} /></h2>{section.content.map((paragraph) => <p key={paragraph}><Highlight text={paragraph} query={query} /></p>)}</section>)}
        </>}
      </main>
      <aside className="help-toc"><strong>本章内容</strong>{sections.map((section) => <a key={section.id} href={`#${section.id}`}>{section.title}</a>)}</aside>
    </div>
  </div>
}
