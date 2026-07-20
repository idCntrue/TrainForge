import { renderToStaticMarkup } from 'react-dom/server'
import { Form } from 'antd'
import { describe, expect, it } from 'vitest'
import { collectTrainingFormValues, TrainingCreationWizardContent } from './TrainingCreationDrawer'

const props = {
  releases: [{ id: 'release-1', label: '数据集 A' }],
  tasks: [{ id: 'task-1', task_type: 'segment' as const, classes: ['door'], class_display_names: { door: '门' } }],
  selectedClasses: [], activeTask: 'segment' as const, activeDevice: 'cpu', activePreset: 'custom' as const,
  useCustomWeight: false, customWeightFile: null, weightUploadProgress: 0,
  onDatasetChange: () => undefined, onWeightModeChange: () => undefined,
  onWeightFileChange: () => undefined, onStorageFailureClose: () => undefined,
}

function Harness({ step, initialValues }: { step: number; initialValues?: Record<string, unknown> }) {
  const [form] = Form.useForm()
  return <Form form={form} initialValues={initialValues}><TrainingCreationWizardContent {...props} form={form} step={step} /></Form>
}

describe('TrainingCreationDrawer', () => {
  it('submits the complete preserved form store after validation', async () => {
    const complete = { name: 'run', task: 'segment', datasetReleaseId: 'release-1' }
    const form = { validateFields: async () => ({ optimizer: 'auto' }), getFieldsValue: (all?: boolean) => all ? complete : {} }
    await expect(collectTrainingFormValues(form as never)).resolves.toEqual(complete)
  })

  it('renders the four-step navigation and only the active basic fields', () => {
    const html = renderToStaticMarkup(<Harness step={0} />)
    for (const label of ['基础设置', '训练策略', '数据增强', '确认启动']) expect(html).toContain(label)
    expect(html).toContain('运行名称')
    expect(html).not.toContain('提前停止耐心值')
  })

  it('shows patience, optimizer and close mosaic on strategy step', () => {
    const html = renderToStaticMarkup(<Harness step={1} />)
    expect(html).toContain('提前停止耐心值')
    expect(html).toContain('优化器')
    expect(html).toContain('关闭 Mosaic')
  })

  it('uses stable body and footer classes for responsive layout', () => {
    const html = renderToStaticMarkup(<Harness step={3} />)
    expect(html).toContain('training-wizard-body')
    expect(html).toContain('启动前确认')
  })

  it('summarizes preserved values from fields that are no longer mounted', () => {
    const html = renderToStaticMarkup(<Harness step={3} initialValues={{ name: '已填写训练', task: 'segment', datasetReleaseId: 'release-1', baseModel: 'yolo11n-seg.pt', epochs: 150, batch: 1, imageSize: 640, device: 'cpu', patience: 25, optimizer: 'AdamW', closeMosaic: 10 }} />)
    expect(html).toContain('已填写训练')
    expect(html).toContain('release-1')
    expect(html).toContain('AdamW')
  })
})
