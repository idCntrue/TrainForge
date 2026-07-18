import { Descriptions, Tag } from 'antd'
import type { DatasetQualityReport } from '../../../api'

export function TrainingEvidencePanel({ report }: { report: DatasetQualityReport }) {
  return <section className="training-evidence-panel">
    <h3>评估数据证据</h3>
    <Descriptions size="small" column={3} items={[
      { key: 'train', label: '训练集', children: `${report.split_images.train ?? 0} 张` },
      { key: 'val', label: '验证集', children: `${report.split_images.val ?? 0} 张` },
      { key: 'test', label: '独立测试集', children: `${report.split_images.test ?? 0} 张` },
    ]} />
    {report.warnings.map((warning) => <Tag key={warning} color="warning">{warning}</Tag>)}
  </section>
}
