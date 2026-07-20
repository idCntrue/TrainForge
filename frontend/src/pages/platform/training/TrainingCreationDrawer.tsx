import { useEffect, useState } from 'react'
import { Alert, AutoComplete, Button, Drawer, Form, Input, InputNumber, Progress, Segmented, Select, Space, Steps, Upload as AntUpload } from 'antd'
import type { FormInstance } from 'antd'
import { Upload } from 'lucide-react'

import type { TrainingStorageErrorDetail } from '../../../api'
import type { CreateTrainingRunInput, TaskType } from '../../../platform/types'
import { formatClassLabel } from '../../annotation/classLabels'
import { buildConfirmationRows, moveWizardStep, trainingCreationSteps } from './trainingCreationWizard'
import { isStrategyField, strategyPatchForPreset, validateCloseMosaic } from './trainingStrategyForm'
import { cpuTrainingPolicy } from './trainingResourcePolicy'
import { trainingFormInitialValues } from './trainingFormDefaults'

type PresetId = NonNullable<CreateTrainingRunInput['presetId']>
type WizardTask = { id: string; task_type: TaskType; classes: string[]; class_display_names: Record<string, string> }
type WizardRelease = { id: string; label: string }

interface ContentProps {
  form: FormInstance<CreateTrainingRunInput>
  step: number
  releases: WizardRelease[]
  tasks: WizardTask[]
  selectedClasses: string[]
  activeTask: TaskType
  activeDevice: string
  activePreset: PresetId
  useCustomWeight: boolean
  customWeightFile: File | null
  weightUploadProgress: number
  storageFailure?: TrainingStorageErrorDetail
  onDatasetChange: (releaseId: string) => void
  onWeightModeChange: (custom: boolean) => void
  onWeightFileChange: (file: File | null) => void
  onStorageFailureClose: () => void
}

const taskOptions = ['detect', 'segment'].map((value) => ({ value, label: value.toUpperCase() }))
const modelPresets = {
  detect: ['yolov8n.pt', 'yolov8s.pt', 'yolo11n.pt', 'yolo11s.pt', 'yolo26n.pt', 'yolo26s.pt'],
  segment: ['yolov8n-seg.pt', 'yolov8s-seg.pt', 'yolo11n-seg.pt', 'yolo11s-seg.pt', 'yolo26n-seg.pt', 'yolo26s-seg.pt'],
}

export function TrainingCreationWizardContent(props: ContentProps) {
  const policy = cpuTrainingPolicy(props.activeTask)
  const values = Form.useWatch([], props.form) ?? props.form.getFieldsValue()
  const applyPreset = (presetId: PresetId) => {
    try {
      props.form.setFieldsValue(strategyPatchForPreset(presetId, props.activeTask, props.activeDevice, props.form.getFieldsValue()))
    } catch {
      props.form.setFieldValue('presetId', 'custom')
    }
  }

  return <div className="training-wizard-body">
    <Steps className="training-wizard-steps" current={props.step} responsive={false} items={trainingCreationSteps.map(({ title }) => ({ title }))} />
    <div className="training-wizard-step-content">
      {props.step === 0 && <>
        <Form.Item name="name" label="运行名称" rules={[{ required: true }]}><Input placeholder="例如：门板缺陷检测 v4" /></Form.Item>
        <div className="form-grid"><Form.Item name="task" label="任务类型" rules={[{ required: true }]}><Select disabled options={taskOptions} /></Form.Item><Form.Item name="datasetReleaseId" label="数据集版本" rules={[{ required: true }]}><Select popupMatchSelectWidth={520} options={props.releases.map((item) => ({ value: item.id, label: item.label }))} onChange={props.onDatasetChange} /></Form.Item></div>
        <Form.Item name="selectedClasses" label="训练 Class" rules={[{ required: true, message: '至少选择一个已标注 class' }]}><Select mode="multiple" options={(props.tasks.find((item) => item.task_type === props.activeTask)?.classes ?? []).map((value) => ({ value, label: formatClassLabel(value, props.tasks.find((item) => item.task_type === props.activeTask)?.class_display_names) }))} /></Form.Item>
        {props.selectedClasses.length > 0 && <><Alert type="info" showIcon message="类别别名仅用于展示，不会修改数据集标签或 Class ID。" /><div className="class-alias-grid">{props.selectedClasses.map((name) => <Form.Item key={name} name={['classAliases', name]} label={`${name} 别名`}><Input placeholder="可选" /></Form.Item>)}</div></>}
        <Form.Item label="基础权重来源"><Segmented block value={props.useCustomWeight ? 'custom' : 'preset'} onChange={(value) => props.onWeightModeChange(value === 'custom')} options={[{ label: '官方 YOLO 预设', value: 'preset' }, { label: '上传自定义 .pt', value: 'custom' }]} /></Form.Item>
        {!props.useCustomWeight ? <Form.Item name="baseModel" label="官方基础模型" rules={[{ required: true, message: '请选择官方基础模型' }]}><AutoComplete allowClear options={modelPresets[props.activeTask as 'detect' | 'segment'].map((value) => ({ value }))} /></Form.Item> : <Form.Item label="自定义 PyTorch 权重" required><AntUpload.Dragger accept=".pt" maxCount={1} beforeUpload={(file) => { props.onWeightFileChange(file); return false }} onRemove={() => { props.onWeightFileChange(null); return true }} fileList={props.customWeightFile ? [props.customWeightFile as any] : []}><p><Upload size={24} /></p><p>点击或拖拽一个 .pt 权重文件</p></AntUpload.Dragger>{props.weightUploadProgress > 0 && props.weightUploadProgress < 100 && <Progress percent={props.weightUploadProgress} size="small" />}</Form.Item>}
      </>}
      {props.step === 1 && <>
        {props.activeDevice === 'cpu' && <Alert type="warning" showIcon message="CPU 安全模式" description={`当前任务 Batch 上限 ${policy.maxBatch}，图像尺寸上限 ${policy.maxImageSize}。`} />}
        {props.storageFailure && <Alert type="error" showIcon closable onClose={props.onStorageFailureClose} message="训练磁盘空间不足" description={props.storageFailure.message} />}
        <Form.Item name="presetId" label="训练方案"><Segmented block onChange={(value) => applyPreset(value as PresetId)} options={[{ label: '流程验证', value: 'smoke' }, { label: 'CPU 均衡', value: 'cpu-balanced' }, { label: 'GPU 高质量', value: 'gpu-quality', disabled: props.activeDevice === 'cpu' }, { label: '自定义', value: 'custom' }]} /></Form.Item>
        <div className="form-grid">
          <Form.Item name="epochs" label="训练轮数（Epochs）" rules={[{ required: true }]}><InputNumber min={1} max={1000} /></Form.Item>
          <Form.Item name="batch" label="每批图片数（Batch）" rules={[{ required: true }]}><InputNumber min={1} max={props.activeDevice === 'cpu' ? policy.maxBatch : 128} /></Form.Item>
          <Form.Item name="imageSize" label="输入图像尺寸" rules={[{ required: true }]}><InputNumber min={320} max={props.activeDevice === 'cpu' ? policy.maxImageSize : 2048} step={32} /></Form.Item>
          <Form.Item name="device" label="设备"><Select options={[{ value: 'cpu', label: 'CPU' }, { value: 'cuda:0', label: 'CUDA 0（GPU）' }]} /></Form.Item>
          <Form.Item name="patience" label="提前停止耐心值" extra="0 表示关闭提前停止；其他值表示指标连续多少轮未改善后停止。"><InputNumber min={0} max={300} /></Form.Item>
          <Form.Item name="optimizer" label="优化器"><Select options={['auto', 'SGD', 'Adam', 'AdamW'].map((value) => ({ value, label: value === 'auto' ? '自动选择' : value }))} /></Form.Item>
          <Form.Item name="closeMosaic" label="关闭 Mosaic" dependencies={['epochs']} rules={[({ getFieldValue }) => ({ validator(_, value) { const error = validateCloseMosaic(getFieldValue('epochs'), value); return error ? Promise.reject(new Error(error)) : Promise.resolve() } })]}><InputNumber min={0} max={values.epochs ?? 1000} /></Form.Item>
        </div>
      </>}
      {props.step === 2 && <>
        <Alert type="info" showIcon message="增强只影响训练，不会修改已发布数据集。" />
        <Form.Item name="augmentProfile" label="增强策略"><Segmented options={[{ value: 'conservative', label: '保守' }, { value: 'standard', label: '标准' }]} /></Form.Item>
        <div className="form-grid">{[
          ['mosaic', 'Mosaic', 0.1, 1], ['mixup', 'MixUp', 0.05, 1], ['copy_paste', 'Copy-Paste', 0.05, 1], ['degrees', '旋转角度', 1, 45], ['translate', '平移比例', 0.05, 0.5], ['scale', '缩放幅度', 0.05, 0.9], ['fliplr', '水平翻转概率', 0.1, 1], ['hsv_h', '色相扰动', 0.005, 0.1], ['hsv_s', '饱和度扰动', 0.05, 1], ['hsv_v', '明度扰动', 0.05, 1],
        ].map(([key, label, step, max]) => <Form.Item key={String(key)} name={['augmentation', key]} label={label}><InputNumber min={0} max={Number(max)} step={Number(step)} /></Form.Item>)}</div>
      </>}
      {props.step === 3 && <section className="training-wizard-confirm"><h3>启动前确认</h3><p>创建后将加入训练队列。提前停止属于正常完成，候选模型使用 best.pt。</p><dl>{buildConfirmationRows(values).map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl></section>}
    </div>
  </div>
}

interface DrawerProps extends Omit<ContentProps, 'step' | 'form'> {
  form: FormInstance<CreateTrainingRunInput>
  open: boolean
  mobile: boolean
  submitting?: boolean
  onClose: () => void
  onSubmit: () => void
}

export function TrainingCreationDrawer(props: DrawerProps) {
  const [step, setStep] = useState(0)
  useEffect(() => { if (props.open) setStep(0) }, [props.open])
  const next = async () => {
    await props.form.validateFields([...trainingCreationSteps[step].fields])
    setStep((current) => moveWizardStep(current, 1))
  }
  return <Drawer className="training-creation-drawer mobile-fullscreen-drawer" width={props.mobile ? '100%' : 720} title="创建训练" open={props.open} onClose={props.onClose} footer={<div className="training-wizard-footer"><Button disabled={step === 0} onClick={() => setStep((current) => moveWizardStep(current, -1))}>上一步</Button><Space>{step < 3 ? <Button type="primary" onClick={() => void next()}>下一步</Button> : <Button type="primary" loading={props.submitting} onClick={props.onSubmit}>加入队列</Button>}</Space></div>}>
    <Form form={props.form} layout="vertical" initialValues={trainingFormInitialValues} onValuesChange={(changed) => { const root = Object.keys(changed)[0]; if (root && root !== 'presetId' && isStrategyField([root]) && props.form.getFieldValue('presetId') !== 'custom') props.form.setFieldValue('presetId', 'custom') }}>
      <TrainingCreationWizardContent {...props} step={step} />
    </Form>
  </Drawer>
}
