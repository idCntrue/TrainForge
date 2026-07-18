import { Table, Tag } from 'antd'
import type { TestMetricsReport } from '../../../api'
import { metricText } from './trainingDetails'

export function ClassMetricsTable({ rows }: { rows: TestMetricsReport['per_class'] }) {
  const weakest = [...rows].filter((row) => row.map50_95 != null).sort((a, b) => (a.map50_95 ?? 0) - (b.map50_95 ?? 0))[0]?.class_id
  return <Table size="small" pagination={false} rowKey="class_id" dataSource={rows} columns={[
    { title: '类别', dataIndex: 'class_name', render: (value, row) => <span>{value} {row.class_id === weakest && <Tag color="warning">需关注</Tag>}</span> },
    { title: 'Precision', dataIndex: 'precision', render: metricText },
    { title: 'Recall', dataIndex: 'recall', render: metricText },
    { title: 'mAP50', dataIndex: 'map50', render: metricText },
    { title: '严格 mAP50-95', dataIndex: 'map50_95', render: metricText },
  ]} />
}
