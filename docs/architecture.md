# 多模型训练中心整体架构设计

> 实施状态：数据准备、原生标注、不可变数据集、YOLO 训练、模型门禁和异步推理已形成单机闭环。以 [当前项目状态](current-status.md) 为准。

## 1. 建设目标

本项目用于管理不同业务类型的 YOLO 模型，例如信号灯、烟雾、电梯部件、扶梯区域等。系统覆盖以下完整流程：

```text
原始视频归档
  -> 视频登记
  -> 抽帧生成候选图片
  -> 图片筛选和去重
  -> Roboflow 标注
  -> 标注数据导出
  -> 数据集版本冻结
  -> GPU 训练
  -> 指标评估
  -> ONNX 导出和验证
  -> 模型版本发布
```

系统必须保证任意一个正式模型都可以追溯到：原始视频、抽帧参数、Roboflow 项目版本、训练数据集、训练配置、基础权重和运行环境。

## 2. 核心设计原则

1. 不同识别内容使用不同任务目录，不混合类别定义和数据生命周期。
2. 原始视频只追加、不覆盖、不直接修改。
3. 抽帧结果按批次保存，同一视频允许使用不同策略重新抽帧。
4. Roboflow 是标注平台，不作为本地唯一数据源；每个正式标注版本必须导回本地归档。
5. 训练只能引用冻结的数据集版本，不能直接读取持续变化的临时标注目录。
6. 数据集版本、训练运行版本和模型发布版本相互独立。
7. `best.pt` 只有通过评估和 ONNX 验证后才能成为正式模型版本。
8. 正式版本禁止覆盖；修改后必须产生新版本。

## 3. 目录架构

```text
yolo_model_factory/
├── README.md
├── configs/
│   ├── system.yaml
│   ├── presets/
│   │   ├── detect-default.yaml
│   │   ├── segment-default.yaml
│   │   ├── gpu-8gb.yaml
│   │   └── small-object.yaml
│   └── tasks/
│       ├── example-segmentation.yaml
│       └── smoke.yaml
├── storage/
│   ├── raw-videos/               # 原始视频，可配置到其他磁盘
│   ├── frame-batches/            # 每次抽帧产生的批次
│   ├── annotation-exports/       # Roboflow 导出的原始压缩包和解压内容
│   └── dataset-releases/         # 冻结、可训练的数据集版本
├── workspaces/
│   ├── training-runs/            # Ultralytics 训练过程文件
│   ├── evaluations/
│   └── export-staging/
├── artifacts/                    # 正式模型制品
├── registry/
│   ├── videos.jsonl
│   ├── frame-batches.jsonl
│   ├── datasets.jsonl
│   ├── training-runs.jsonl
│   └── models.jsonl
├── src/
│   ├── video/
│   ├── datasets/
│   ├── training/
│   ├── evaluation/
│   ├── export/
│   └── registry/
├── scripts/
├── tests/
└── docs/
```

大体积数据应放在代码仓库之外的受管目录。项目通过系统配置指定 `storage_root`，不应把视频、图片、数据库或权重复制到 Git 工作区。

### 3.1 标准工程目录

正式实施采用Python标准`src`布局，并按业务能力而不是技术类型拆包。以下结构取代前面的概念性目录，作为代码阶段的权威目录规范：

```text
yolo_model_factory/
├── .github/
│   └── workflows/                 # CI检查、单元测试、安全扫描
├── configs/
│   ├── environments/              # 开发、测试环境配置
│   ├── presets/                   # detect/segment等公共预设
│   ├── schemas/                   # 配置和manifest JSON Schema
│   ├── tasks/                     # 每个业务任务独立配置
│   └── system.yaml
├── docs/
│   ├── adr/                       # Architecture Decision Records
│   ├── architecture/              # 系统和数据架构
│   ├── operations/                # 安装、备份、恢复、故障处理
│   ├── superpowers/
│   │   ├── plans/
│   │   └── specs/
│   ├── architecture.md
│   ├── technical-research.md
│   └── workflow-tutorial.md
├── migrations/                    # Alembic数据库迁移
├── scripts/                       # 面向运维人员的PowerShell入口
├── src/
│   └── yolo_factory/
│       ├── cli/                   # Typer命令和输出格式
│       ├── config/                # 配置模型、加载和校验
│       ├── registry/              # SQLite模型、仓储和事务
│       ├── video/                 # 视频入库、探测和哈希
│       ├── frames/                # 抽帧、去重、人工筛选状态
│       ├── annotations/           # Roboflow包导出和导入
│       ├── datasets/              # 校验、划分和版本发布
│       ├── integrations/          # Datumaro、DVC、OpenCV适配器
│       ├── manifests/             # YAML和校验和清单
│       ├── observability/         # 结构化日志和运行上下文
│       └── common/                # 少量跨模块基础类型和异常
├── tests/
│   ├── unit/                      # 单模块快速测试
│   ├── integration/               # SQLite、文件系统、Datumaro、DVC
│   ├── e2e/                       # detect/segment完整流程
│   ├── fixtures/                  # 小型视频和标注测试数据
│   └── conftest.py
├── tools/                         # 开发期检查工具，不作为产品CLI
├── .editorconfig
├── .gitignore
├── .pre-commit-config.yaml
├── CHANGELOG.md
├── LICENSE
├── README.md
├── SECURITY.md
└── pyproject.toml
```

目录约束：

- `src/yolo_factory`是唯一产品代码根目录，禁止在项目根目录散落Python业务脚本。
- `scripts`只做环境安装、备份和运维封装，业务逻辑必须调用产品CLI。
- `integrations`隔离第三方库，领域模块不得直接散落Datumaro、DVC和OpenCV调用。
- `tests`镜像业务模块，并明确区分单元、集成和端到端测试。
- 数据库结构变化必须通过`migrations`，禁止运行时隐式修改生产表。
- 关键架构决定写入`docs/adr`，避免后续只依赖聊天记录理解设计原因。
- 日志、临时文件、SQLite数据库和数据制品属于运行数据，不进入Git。

### 3.2 外部数据仓库目录

代码仓库与数据仓库完全分离：

```text
<storage-root>/
├── raw-videos/
├── frame-batches/
├── annotation-packages/
├── annotation-exports/
├── dataset-releases/
├── dvc-cache/
├── registry/
│   ├── model-factory.db
│   └── backups/
├── staging/
├── quarantine/
└── logs/
```

`staging`用于未完成的原子操作，`quarantine`保存损坏或校验失败的输入，正式目录只接收已经完成验证和原子重命名的内容。

## 4. 业务任务隔离

每种识别内容定义一个稳定的 `task_id`：

```text
signal-light-detection
smoke-detection
elevator-part-detection
walkway-segmentation
```

任务 ID 一旦产生正式数据或模型后不再修改。类别名称变化、任务类型变化或类别语义发生重大变化时，应新建任务，而不是覆盖旧任务。

信号灯任务示例：

```yaml
task_id: signal-light-detection
display_name: 信号灯识别
task_type: detect
classes:
  - red
  - yellow
  - green

base_model: yolo26n.pt
storage_namespace: signal-light
```

### 4.1 模型系列与任务类型

系统必须将模型系列和视觉任务分开描述：

```text
模型系列：YOLOv8、YOLO11、YOLO26及后续兼容系列
任务类型：detect、segment、classify、pose、obb
```

第一阶段数据链路正式支持`detect`和`segment`，并为其他任务保留扩展接口。配置示例：

```yaml
task_id: walkway-segmentation
task_type: segment

model:
  framework: ultralytics
  family: yolo26
  weights: yolo26n-seg.pt

dataset:
  annotation_format: yolo-seg
```

YOLOv8分割任务只需替换模型系列和权重：

```yaml
model:
  framework: ultralytics
  family: yolov8
  weights: yolov8n-seg.pt
```

系统在训练前必须保证以下三者一致：

```text
任务配置 task_type
= 数据集 annotation_format
= 基础权重实际任务类型
```

检测标签和分割标签不能放入同一个正式数据集版本。即使来源图片相同，也应建立独立任务、Roboflow Project和数据集版本。

### 4.2 训练适配器边界

后续训练阶段采用适配器，而不是为不同YOLO版本复制训练脚本：

```text
TrainingAdapter
└── UltralyticsAdapter
    ├── detect
    ├── segment
    ├── classify
    ├── pose
    └── obb
```

模型权重路径是实际加载依据，`family`用于版本治理、兼容性检查和报告。每次运行必须记录Python、PyTorch、CUDA、Ultralytics、权重SHA-256及任务类型。

## 5. 版本模型

### 5.1 视频批次版本

原始视频按采集批次管理：

```text
storage/raw-videos/signal-light/
├── collection-20260713-a/
│   ├── videos/
│   └── manifest.yaml
└── collection-20260820-a/
```

`manifest.yaml`记录来源、采集时间、场景、设备、负责人、文件哈希和备注。原始视频文件名可以调整，但登记后必须通过哈希保持身份可追踪。

### 5.2 抽帧批次版本

抽帧不是数据集版本，而是从视频产生候选图片的一次处理记录：

```text
storage/frame-batches/signal-light/frames-20260713-001/
├── images/
├── contact-sheets/
├── rejected/
└── manifest.yaml
```

批次清单记录：

- 输入视频批次和文件哈希
- 抽帧模式和间隔
- 场景变化阈值
- 图片尺寸和压缩质量
- 去重算法及阈值
- 生成、保留和剔除数量
- 脚本版本及执行时间

### 5.3 数据集版本

从 Roboflow 导回并通过本地检查的数据，冻结为不可变数据集版本：

```text
signal-light-detection/dataset-v1.0.0
signal-light-detection/dataset-v1.1.0
signal-light-detection/dataset-v2.0.0
```

版本建议：

- `PATCH`：修正少量错误标签或损坏文件，不改变类别定义。
- `MINOR`：增加新视频、新场景或新标注图片，不改变类别语义。
- `MAJOR`：类别集合、类别含义、任务类型或数据规范发生不兼容变化。

例如新增一批夜间信号灯视频并完成标注，应由 `dataset-v1.0.0`升级到`dataset-v1.1.0`。

### 5.4 训练运行版本

一次训练是一个不可变运行记录：

```text
train-20260713-001
train-20260713-002
```

同一数据集可能因为基础模型、分辨率、增强策略或随机种子不同而产生多次训练。训练编号不等于正式模型版本。

### 5.5 模型发布版本

通过准入检查的训练结果发布为：

```text
signal-light-detection/model-v1.0.0
signal-light-detection/model-v1.1.0
```

建议规则：

- `PATCH`：训练或导出修复，输入输出契约和数据主体不变。
- `MINOR`：增加数据后重新训练，类别和推理接口保持兼容。
- `MAJOR`：类别、输出结构、任务类型或预处理方式发生不兼容变化。

数据集版本和模型版本不要求数字一致，模型元数据必须明确引用数据集版本。

## 6. 数据流和追溯关系

```text
collection-20260713-a
  -> frames-20260713-001
  -> roboflow project signal-light / version 1
  -> dataset-v1.0.0
  -> train-20260713-001
  -> model-v1.0.0

collection-20260820-a
  -> frames-20260820-001
  -> roboflow project signal-light / version 2
  -> dataset-v1.1.0
  -> train-20260821-001
  -> model-v1.1.0
```

`dataset-v1.1.0`可以包含`dataset-v1.0.0`的全部数据再加入新数据，也可以重新划分训练集。两种情况都必须在数据集清单中说明父版本和差异。

## 7. 视频抽帧架构

抽帧工具应支持三种模式：

1. 固定时间间隔：例如每2秒抽取一帧，适合快速建立首批数据。
2. 固定帧间隔：例如每60帧抽取一帧，适合帧率稳定的视频。
3. 场景变化抽帧：画面变化达到阈值才保留，减少连续重复图片。

推荐默认组合：先按时间间隔抽帧，再使用感知哈希去重。视频必须保留，抽出的图片可以重建，但进入标注流程的批次不得随意覆盖。

图片命名必须包含来源信息：

```text
collection-20260713-a__video-003__t-000123400ms__f-003702.jpg
```

同时生成图片到视频时间点的映射，避免标注异常时无法回看原始上下文。

## 8. Roboflow 对接

建议每个 `task_id`对应一个 Roboflow Project，不同数据迭代使用 Roboflow Dataset Version。

上传到 Roboflow 的对象是经过筛选的抽帧图片，不上传整个训练输出目录。完成标注后，创建固定 Roboflow Version，并以 YOLO 对应任务格式导出。

本地必须归档：

- Roboflow workspace、project 和 version
- 导出时间与导出格式
- 原始下载压缩包
- 解压后的数据
- 类别映射
- 下载文件 SHA-256

训练不能直接依赖会变化的 Roboflow 在线状态，应依赖本地冻结的数据集发布版本。

检测任务在Roboflow中建立Object Detection Project，分割任务建立Instance Segmentation Project。一个Project不得同时承担检测和分割标签。每个新的Roboflow Dataset Version采用完整累积快照，包含需要保留的旧数据和新增数据。

第一阶段采用手动上传和下载ZIP，不保存Roboflow API密钥。系统只负责生成上传包、登记Roboflow身份、导入下载包以及执行本地校验。

## 9. 数据集发布结构

```text
storage/dataset-releases/signal-light-detection/dataset-v1.1.0/
├── data.yaml
├── images/
│   ├── train/
│   ├── val/
│   └── test/
├── labels/
│   ├── train/
│   ├── val/
│   └── test/
├── dataset-manifest.yaml
├── validation-report.json
├── class-statistics.csv
└── checksums.sha256
```

数据集发布前必须检查图片损坏、标签缺失、类别越界、非法坐标、重复图片、跨集合重复和类别分布。

首个正式数据集由本地工具建立固定测试基线。后续版本继承该测试集，新数据主要进入训练集和验证集。测试集确需扩充时，必须发布新的测试基线并记录差异，避免不同模型版本因测试样本变化而失去可比性。

### 9.1 DVC与本地清单

大型视频、抽帧图片、Roboflow导出包和数据集快照由DVC管理。DVC按内容哈希复用相同文件，避免累积完整数据集版本重复占用全部磁盘空间。

SQLite保存全局索引和工作状态，每个冻结目录同时生成独立YAML清单及SHA-256文件：

```text
SQLite：查询、查重、状态流转、编号分配
YAML：批次和版本的可迁移快照
DVC：大文件内容与版本指针
Git：代码、配置、DVC指针和文档
```

正式版本只能通过发布命令生成，禁止手工复制目录后登记为新版本。

### 9.2 开源组件分工

```text
FFmpeg/OpenCV：视频探测、解码和抽帧
ImageHash/OpenCV：近似重复图片检测
Datumaro：Roboflow/YOLO数据解析、转换和通用统计
DVC：视频、图片和数据集的大文件版本管理
SQLite：工作流状态与全局索引
FiftyOne：后续可选的数据浏览和筛选工作台
Roboflow：人工标注和标注审核
```

CVAT与Label Studio不在当前实施范围，因为它们会与已确定的Roboflow标注流程重叠。

## 10. GPU训练架构

训练使用项目声明的 Python/PyTorch/Ultralytics 环境；容器版本由 CPU 或 GPU Dockerfile 固定。设备策略：

- 正式训练默认要求GPU可用，不静默回退CPU。
- 同一时间只允许一个训练任务占用GPU 0。
- 默认开启AMP混合精度。
- batch优先使用自动探测，也可以由8GB显存预设限制。
- 显存不足时允许降低batch重试一次，并记录配置变化。
- 每次训练记录GPU、驱动、CUDA、PyTorch和Ultralytics版本。

训练输出只进入`workspaces/training-runs`，不能直接作为正式模型交付。

## 11. 评估和发布准入

每个任务独立定义准入指标，例如：

```yaml
acceptance:
  map50_min: 0.85
  map50_95_min: 0.55
  recall_min: 0.80
  required_test_set: true
```

除整体指标外，还应检查每个类别的精确率和召回率。新增数据训练出的模型不一定优于旧版本，因此必须在固定回归测试集上与当前生产模型比较。

## 12. ONNX导出与验证

只有通过评估的`best.pt`才能导出。找不到权重时必须失败，禁止回退到基础预训练模型。

推荐默认参数：

```yaml
format: onnx
imgsz: 640
batch: 1
opset: 17
dynamic: false
simplify: true
half: false
nms: false
```

导出完成后依次执行：ONNX结构检查、ONNX Runtime加载、假数据推理、真实样本推理、PT和ONNX输出对比、耗时测试及SHA-256计算。

检测和分割模型的ONNX输出结构不同，必须使用独立验证器：

```text
detect_validator：边界框、类别、置信度和NMS前输出
segment_validator：检测输出、mask系数、prototype mask和还原结果
```

YOLOv8和YOLO26在同一Ultralytics适配器下导出，但验证逻辑按`task_type`选择，不能只按模型系列选择。

## 13. 正式模型制品

```text
artifacts/example-segmentation/model-v1.1.0/
├── best.pt
├── model.onnx
├── metadata.yaml
├── task-config.yaml
├── dataset-manifest.yaml
├── metrics.json
├── regression-report.json
├── onnx-validation.json
├── sample-results/
└── checksums.sha256
```

业务项目只读取`artifacts`中的模型，不读取训练临时目录。发布目录不可覆盖；需要回滚时直接切换到旧模型版本。

## 14. 当前实现边界

当前单机版本已经覆盖浏览器上传、视频抽帧、分页筛选、原生检测/分割标注、SAM2 辅助分割、不可变数据集发布、CPU/GPU Ultralytics 训练、测试集评估、PT/ONNX 门禁和异步推理。SQLite、文件系统存储和本地子进程适合单节点或小团队部署；远程 Worker、多实例调度、对象存储正式实现和多租户能力仍属于后续范围。

## 15. 训练资源保护与证据链

训练资源保护分为三个边界：

1. API 在创建训练、安全重试和独立评估前执行同一套存储预检。
2. 清理器只允许删除缩略图缓存、超过保留期的上传暂存目录和原子写入遗留的 `.tmp` 文件；数据库、数据集、帧批次、权重和正式训练目录不属于可写根。
3. 清理完成后重新读取磁盘，默认要求同时满足 `8 GiB` 和 `10%` 空闲；部署脚本负责 Docker 构建缓存和旧项目镜像，不向 API 容器开放 Docker Socket。

训练 Runner 启动前记录 cgroup OOM 基线，失败时再次读取 `memory.current`、`memory.peak`、`memory.max` 和 `memory.events`。`exit -9`/`137` 只证明外部 `SIGKILL`；只有本次运行的 `oom_kill` 增量大于零，诊断才标记为已确认 OOM。该证据随 `failure.json` 持久化，供页面恢复建议和后续容量规划使用。
