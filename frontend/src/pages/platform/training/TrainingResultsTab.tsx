import { Alert, Empty, Image } from 'antd'
import { api, type TrainingArtifactApiResponse, type TrainingRunDetailsApiResponse } from '../../../api'
import { artifactLabel } from './trainingDetails'
import { resultImageGroups } from './trainingDashboardPresentation'

function ImageGroup({ title, description, images }: { title: string; description: string; images: TrainingArtifactApiResponse[] }) {
  if (!images.length) return null
  return <section className="training-result-group">
    <div><h3>{title}</h3><p>{description}</p></div>
    <div className="training-result-grid">{images.map((artifact) => <figure key={artifact.path}>
      <Image src={api.getArtifactUrl(artifact.path)} alt={artifactLabel(artifact.key)} />
      <figcaption><strong>{artifactLabel(artifact.key)}</strong><span>{artifact.name}</span></figcaption>
    </figure>)}</div>
  </section>
}

export function TrainingResultsTab({ details }: { details: TrainingRunDetailsApiResponse }) {
  const groups = resultImageGroups(details.artifacts)
  const imageCount = Object.values(groups).reduce((sum, items) => sum + items.length, 0)
  if (!imageCount) return <Empty description="训练产生预测样例和评估图后，将在这里自动分类展示" />
  return <Image.PreviewGroup><div className="training-result-groups">
    <Alert type="info" showIcon message="先看预测样例，再看诊断图" description="预测样例最直观；混淆矩阵和统计曲线用于进一步定位漏检、误检与类别混淆。点击任意图片可以放大查看。" />
    <ImageGroup title="预测效果样例" description="检查目标轮廓或检测框是否贴合，有没有明显漏检、误检和类别错误。" images={groups.predictions} />
    <ImageGroup title="类别混淆诊断" description="对角线越集中通常越好；非对角线的高值表示两个类别容易被模型混淆。" images={groups.confusion} />
    <ImageGroup title="评估统计曲线" description="用于判断不同置信度下精确率、召回率与综合质量的变化。" images={groups.curves} />
    <ImageGroup title="其他训练图像" description="包含训练批次、标签分布等辅助证据，用于排查数据和训练过程。" images={groups.other} />
  </div></Image.PreviewGroup>
}
