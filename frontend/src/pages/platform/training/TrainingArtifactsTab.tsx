import { Button, Card, Descriptions, Empty, Space, Tag } from 'antd'
import { Award, Download, FileText, RotateCcw } from 'lucide-react'
import { api, type TrainingArtifactApiResponse, type TrainingRunDetailsApiResponse } from '../../../api'
import { artifactLabel } from './trainingDetails'
import { artifactGroups } from './trainingDashboardPresentation'

const formatBytes = (value: number) => value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(value / 1024)} KB`

function DownloadButton({ artifact, primary = false }: { artifact: TrainingArtifactApiResponse; primary?: boolean }) {
  return <Button type={primary ? 'primary' : 'default'} href={api.getArtifactUrl(artifact.path)} target="_blank" icon={<Download size={14} />}>下载</Button>
}

function ArtifactList({ artifacts }: { artifacts: TrainingArtifactApiResponse[] }) {
  if (!artifacts.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无此类文件" />
  return <div className="training-artifact-list">{artifacts.map((artifact) => <div key={artifact.path}><div><strong>{artifactLabel(artifact.key)}</strong><span>{artifact.name} · {formatBytes(artifact.size_bytes)}</span></div><Space><Tag>{artifact.kind}</Tag><DownloadButton artifact={artifact} /></Space></div>)}</div>
}

export function TrainingArtifactsTab({ details }: { details: TrainingRunDetailsApiResponse }) {
  const distribution = details.split_distribution
  const groups = artifactGroups(details.artifacts)
  return <div className="training-detail-stack">
    <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }} items={[
      { key: 'dataset', label: '数据集版本', children: details.configuration.dataset_release_id },
      { key: 'ratios', label: '请求比例', children: distribution.requested_ratios ? `训练 ${distribution.requested_ratios.train}% / 验证 ${distribution.requested_ratios.val}% / 测试 ${distribution.requested_ratios.test}%` : '历史版本未记录' },
      { key: 'classes', label: '训练类别', span: 2, children: details.configuration.selected_classes.join('、') || '全部类别' },
      { key: 'seed', label: '划分随机种子', children: distribution.split_seed ?? '-' },
      { key: 'group', label: '划分策略', children: distribution.grouping_strategy ?? '历史版本' },
    ]} />

    <section className="training-artifact-section">
      <div><h3>主要模型权重</h3><p>权重文件需要结合独立测试结果和运行门禁判断是否可以发布。</p></div>
      {groups.weights.length ? <div className="training-weight-grid">{groups.weights.map((artifact) => {
        const best = artifact.key === 'best_pt'
        return <Card key={artifact.path} className={best ? 'training-weight-card recommended' : 'training-weight-card'} size="small">
          <div className="training-weight-heading">{best ? <Award size={24} /> : <RotateCcw size={24} />}<div><strong>{best ? '最佳权重 best.pt' : '最终轮权重 last.pt'}</strong>{best && <Tag color="gold">优先评估</Tag>}</div></div>
          <p>{best ? '验证过程中表现最好的权重。建议先用它运行门禁和现场样本验证，通过后再发布。' : '最后一轮保存的权重，可用于结果对照。能否继续训练还取决于完整运行状态与训练配置。'}</p>
          <div className="training-weight-footer"><span>{formatBytes(artifact.size_bytes)}</span><DownloadButton artifact={artifact} primary={best} /></div>
        </Card>
      })}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次运行尚未生成模型权重" />}
    </section>

    <section className="training-artifact-section"><div><h3><FileText size={16} />评估报表与日志文件</h3><p>用于复核逐轮指标、运行过程和训练环境。</p></div><ArtifactList artifacts={groups.reports} /></section>
    <section className="training-artifact-section"><div><h3>其他配置与文件</h3><p>保留完整配置和框架生成文件，便于复现与排查。</p></div><ArtifactList artifacts={groups.other} /></section>
    <section className="training-artifact-section"><div><h3>运行日志（最近 200 行）</h3><p>训练失败或结果异常时，优先查看错误末尾和资源相关提示。</p></div><pre className="training-log-detail">{details.logs.join('\n') || '暂无日志'}</pre></section>
  </div>
}
