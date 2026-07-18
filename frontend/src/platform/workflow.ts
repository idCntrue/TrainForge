import type { ViewKey } from '../navigation'

export interface WorkflowTotals {
  tasks: number
  dataSources: number
  datasetReleases: number
  trainingRuns: number
  models: number
  publishedModels: number
}

export interface WorkflowAction {
  view: ViewKey
  stage: '数据准备' | '模型开发' | '推理验证'
  title: string
  description: string
  buttonLabel: string
}

export function recommendNextAction(totals: WorkflowTotals): WorkflowAction {
  if (totals.tasks === 0) return { view: 'tasks', stage: '数据准备', title: '创建第一个任务', description: '先定义检测或分割任务以及类别，后续数据和模型都会归属到该任务。', buttonLabel: '创建任务' }
  if (totals.dataSources === 0) return { view: 'videos', stage: '数据准备', title: '导入训练素材', description: '上传图片，或导入视频后抽帧，建立待筛选的数据来源。', buttonLabel: '导入数据' }
  if (totals.datasetReleases === 0) return { view: 'review', stage: '数据准备', title: '整理并标注数据', description: '筛选有效图片、完成原生标注，然后发布不可变的数据集版本。', buttonLabel: '开始数据筛选' }
  if (totals.trainingRuns === 0) return { view: 'training', stage: '模型开发', title: '创建第一次训练', description: '选择已发布的数据集版本、基础模型和训练参数，加入本地 GPU 队列。', buttonLabel: '创建训练' }
  if (totals.models === 0) return { view: 'training', stage: '模型开发', title: '检查训练并注册模型', description: '查看训练结果与指标，将合格权重注册为候选模型。', buttonLabel: '查看训练运行' }
  if (totals.publishedModels === 0) return { view: 'models', stage: '模型开发', title: '验证并发布模型', description: '执行制品门禁与 PT/ONNX 一致性检查，通过后发布模型。', buttonLabel: '打开模型中心' }
  return { view: 'inference', stage: '推理验证', title: '使用已发布模型推理', description: '上传图片、批量图片或视频，验证模型在真实素材上的表现。', buttonLabel: '开始推理' }
}
