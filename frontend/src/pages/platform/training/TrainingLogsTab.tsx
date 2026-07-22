import { Button, Empty, Input, Segmented, Select, Switch, Tooltip, message } from 'antd'
import { ArrowDownToLine, Copy, Download, Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type TrainingRunDetailsApiResponse } from '../../../api'
import { filterLogLines, type TrainingLogFilter } from './trainingDashboardPresentation'

const levelOptions: Array<{ value: TrainingLogFilter['level']; label: string }> = [
  { value: 'all', label: '全部内容' },
  { value: 'epoch', label: '轮次进度' },
  { value: 'warning', label: '警告' },
  { value: 'error', label: '错误' },
]

export function TrainingLogsTab({ details }: { details: TrainingRunDetailsApiResponse }) {
  const [mode, setMode] = useState<TrainingLogFilter['mode']>('live')
  const [level, setLevel] = useState<TrainingLogFilter['level']>('all')
  const [query, setQuery] = useState('')
  const [wrap, setWrap] = useState(true)
  const [follow, setFollow] = useState(true)
  const viewportRef = useRef<HTMLDivElement>(null)
  const fullLog = details.artifacts.find((item) => item.key === 'runner_log')
  const displayed = useMemo(
    () => filterLogLines(details.logs, { mode, level, query }),
    [details.logs, level, mode, query],
  )

  useEffect(() => {
    setMode('live')
    setLevel('all')
    setQuery('')
    setFollow(true)
  }, [details.run_id])

  useEffect(() => {
    if (!follow || !viewportRef.current) return
    viewportRef.current.scrollTop = viewportRef.current.scrollHeight
  }, [details.logs, displayed, follow])

  const jumpToBottom = () => {
    if (viewportRef.current) viewportRef.current.scrollTop = viewportRef.current.scrollHeight
    setFollow(true)
  }

  const copyVisibleLogs = async () => {
    try {
      if (!navigator.clipboard) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(displayed.map((line) => line.text).join('\n'))
      message.success(`已复制 ${displayed.length} 行日志`)
    } catch {
      message.error('复制失败，请下载完整日志')
    }
  }

  return <section className="training-log-workspace" aria-label="训练运行日志">
    <div className="training-log-notice">
      <div><strong>运行日志</strong><span>页面展示最近 200 行；排查完整过程请下载完整日志。</span></div>
      {fullLog && <Button className="training-full-log-download" href={api.getArtifactUrl(fullLog.path)} target="_blank" icon={<Download size={15} />}>下载完整日志</Button>}
    </div>

    <div className="training-log-toolbar">
      <Segmented<TrainingLogFilter['mode']> value={mode} onChange={setMode} options={[{ value: 'live', label: '实时日志' }, { value: 'diagnostic', label: '故障诊断' }]} />
      <Input aria-label="搜索日志" value={query} onChange={(event) => setQuery(event.target.value)} allowClear prefix={<Search size={14} />} placeholder="搜索日志" />
      <Select aria-label="日志级别" value={level} onChange={setLevel} options={levelOptions} />
      <label className="training-log-switch"><span>自动跟随</span><Switch size="small" checked={follow} onChange={setFollow} /></label>
      <label className="training-log-switch"><span>自动换行</span><Switch size="small" checked={wrap} onChange={setWrap} /></label>
      <div className="training-log-actions">
        <Tooltip title="复制当前筛选结果"><Button aria-label="复制当前筛选结果" icon={<Copy size={15} />} onClick={() => void copyVisibleLogs()} /></Tooltip>
        <Tooltip title="跳到最新日志"><Button aria-label="跳到最新日志" icon={<ArrowDownToLine size={15} />} onClick={jumpToBottom} /></Tooltip>
      </div>
    </div>

    <div
      ref={viewportRef}
      className={`training-log-viewport${wrap ? ' wrap' : ''}`}
      onScroll={(event) => {
        const element = event.currentTarget
        if (element.scrollHeight - element.scrollTop - element.clientHeight > 24) setFollow(false)
      }}
    >
      {displayed.length ? displayed.map((line) => <div className={`training-log-line training-log-line-${line.level}`} key={line.number}>
        <span className="training-log-number">{line.number}</span>
        <code>{line.text || ' '}</code>
      </div>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={details.logs.length ? '当前筛选条件下没有匹配日志' : '训练启动并输出日志后显示'} />}
    </div>
    <div className="training-log-footer"><span>当前显示 {displayed.length} / {details.logs.length} 行</span><span>{follow ? '正在跟随最新日志' : '已暂停自动跟随'}</span></div>
  </section>
}
