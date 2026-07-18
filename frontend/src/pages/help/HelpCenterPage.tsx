import { useMemo, useState } from 'react'
import { Input, Tag } from 'antd'
import { BookOpen, Search } from 'lucide-react'

import { helpChapters, searchHelp } from './helpContent'

export default function HelpCenterPage() {
  const [query, setQuery] = useState('')
  const [activeId, setActiveId] = useState(helpChapters[0].id)
  const results = useMemo(() => searchHelp(query), [query])
  const active = results.find((chapter) => chapter.id === activeId) ?? results[0]

  return <div className="help-center">
    <header className="help-header">
      <div><span className="help-eyebrow"><BookOpen size={15} /> 离线用户手册</span><h2>帮助中心</h2><p>从数据准备到云端部署的完整 TrainForge 操作手册。</p></div>
      <Input allowClear prefix={<Search size={15} />} placeholder="搜索操作、错误或术语" value={query} onChange={(event) => setQuery(event.target.value)} />
    </header>
    <div className="help-layout">
      <nav className="help-nav" aria-label="帮助章节">
        <strong>文档目录</strong>
        {results.map((chapter) => <button className={chapter.id === active?.id ? 'active' : ''} key={chapter.id} onClick={() => setActiveId(chapter.id)}><span>{chapter.title}</span><small>{chapter.summary}</small></button>)}
        {results.length === 0 && <p>没有找到相关内容，请尝试更短的关键词。</p>}
      </nav>
      <main className="help-document">
        {active && <>
          <div className="help-document-title"><Tag color="green">内置文档</Tag><h1>{active.title}</h1><p>{active.summary}</p></div>
          {active.sections.map((section) => <section id={section.id} key={section.id}><h2>{section.title}</h2>{section.content.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}</section>)}
        </>}
      </main>
      <aside className="help-toc"><strong>本章内容</strong>{active?.sections.map((section) => <a key={section.id} href={`#${section.id}`}>{section.title}</a>)}</aside>
    </div>
  </div>
}
