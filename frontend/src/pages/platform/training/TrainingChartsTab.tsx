import { Alert, Empty, Segmented } from 'antd'
import { useEffect, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TrainingRunDetailsApiResponse } from '../../../api'
import { defaultMetricMode, type MetricMode } from './trainingDashboardPresentation'

type Series = { key: string; label: string; color: string }

const lossSeries: Record<MetricMode, Series[]> = {
  box: [
    { key: 'train_box_loss', label: '训练 Box Loss', color: '#1677ff' },
    { key: 'val_box_loss', label: '验证 Box Loss', color: '#d46b08' },
  ],
  mask: [
    { key: 'train_seg_loss', label: '训练 Mask Loss', color: '#0f8f83' },
    { key: 'val_seg_loss', label: '验证 Mask Loss', color: '#c46b12' },
  ],
}

const qualitySeries: Record<MetricMode, Series[]> = {
  box: [
    { key: 'map50_box', label: 'Box mAP50', color: '#1677ff' },
    { key: 'map50_95_box', label: 'Box mAP50-95', color: '#69b1ff' },
  ],
  mask: [
    { key: 'map50_mask', label: 'Mask mAP50', color: '#0f8f83' },
    { key: 'map50_95_mask', label: 'Mask mAP50-95', color: '#5bc2b8' },
    { key: 'precision_mask', label: '精确率', color: '#6f42c1' },
    { key: 'recall_mask', label: '召回率', color: '#c43d7b' },
  ],
}

function Chart({ title, data, lines }: { title: string; data: TrainingRunDetailsApiResponse['epoch_history']; lines: Series[] }) {
  return <section className="training-chart"><h3>{title}</h3><ResponsiveContainer width="100%" height={280}><LineChart data={data}><CartesianGrid strokeDasharray="3 3" stroke="#e7ecea" /><XAxis dataKey="epoch" label={{ value: '训练轮次', position: 'insideBottomRight', offset: -4 }} /><YAxis /><Tooltip /><Legend />{lines.map((line) => <Line key={line.key} type="monotone" dataKey={line.key} name={line.label} stroke={line.color} strokeWidth={2} dot={false} connectNulls />)}</LineChart></ResponsiveContainer></section>
}

export function TrainingChartsTab({ details }: { details: TrainingRunDetailsApiResponse }) {
  const supportsMask = details.configuration.task_type === 'segment'
  const [mode, setMode] = useState<MetricMode>(() => defaultMetricMode(details.configuration.task_type))
  useEffect(() => setMode(defaultMetricMode(details.configuration.task_type)), [details.run_id, details.configuration.task_type])
  if (!details.epoch_history.length) return <Empty description="产生首轮训练指标后，这里会自动绘制趋势曲线" />
  const activeMode = supportsMask ? mode : 'box'
  return <div className="training-detail-stack">
    {supportsMask && <Segmented<MetricMode> value={activeMode} onChange={setMode} options={[{ value: 'mask', label: '实例分割 Mask' }, { value: 'box', label: '目标定位 Box' }]} />}
    <div className="training-chart-grid">
      <Chart title={`${activeMode === 'mask' ? '分割' : '定位'}损耗趋势`} data={details.epoch_history} lines={lossSeries[activeMode]} />
      <Chart title={`${activeMode === 'mask' ? '分割' : '定位'}质量指标`} data={details.epoch_history} lines={qualitySeries[activeMode]} />
    </div>
    <div className="training-chart-guide">
      <Alert type="info" showIcon message="质量指标怎么看" description="mAP、精确率和召回率通常越高越好。请观察整体趋势和最终稳定区间，不要只看某一轮的峰值。" />
      <Alert type="warning" showIcon message="Loss 怎么看" description="训练 Loss 与验证 Loss 应整体下降并逐渐稳定。如果训练 Loss 继续下降，而验证 Loss 持续上升，模型可能正在过拟合。" />
    </div>
  </div>
}
