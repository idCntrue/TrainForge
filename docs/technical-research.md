# 开源组件与技术选型调研

## 1. 调研目标

本调研寻找可复用的开源项目，以减少视频处理、图片筛选、标注交换、数据集校验和版本管理方面的自研工作。目标工作流为：

```text
视频复制归档
→ 抽帧和去重
→ 人工筛选
→ Roboflow手动标注
→ YOLO数据导回
→ 检测/分割校验
→ 固定测试集
→ 不可变数据集版本
```

项目还需为后续YOLOv8、YOLO26的detect、segment训练及ONNX导出预留接口。

## 2. 调研结论

没有单一开源项目完整覆盖当前流程。推荐采用成熟组件组合，并自行实现轻量编排层：

```text
DVC + Datumaro + FFmpeg/OpenCV + ImageHash + SQLite/YAML + Roboflow
```

FiftyOne作为后续可选的数据审查界面，不作为主版本数据库。CVAT和Label Studio暂不引入。

## 3. 候选项目对比

| 项目 | 主要能力 | 许可证 | 当前定位 |
|---|---|---|---|
| FiftyOne | 视频/图片浏览、标签与预测分析、交互筛选 | Apache-2.0 | 后续可选工作台 |
| DVC | 大文件版本、流水线、实验和远程存储 | Apache-2.0 | 核心组件 |
| Datumaro | 视觉数据集导入、转换、分析和导出 | MIT | 核心组件 |
| CVAT | 图片、视频和3D标注平台 | MIT | 不采用，避免替代Roboflow |
| Label Studio | 通用数据标注平台 | Apache-2.0 | 不采用，功能重叠 |
| Supervision | 视频分析、检测结果处理和可视化 | MIT | 后续辅助库 |

项目地址：

- FiftyOne：https://github.com/voxel51/fiftyone
- DVC：https://github.com/iterative/dvc
- Datumaro：https://github.com/open-edge-platform/datumaro
- CVAT：https://github.com/cvat-ai/cvat
- Label Studio：https://github.com/HumanSignal/label-studio
- Supervision：https://github.com/roboflow/supervision

## 4. FiftyOne

FiftyOne是开源计算机视觉数据集管理和可视化工具，适合浏览视频、帧、标签、模型预测及困难样本。它可以明显改善数万张图片下的人工筛选体验。

优点：

- 有成熟的本地可视化界面。
- 适合筛选、过滤、标签审查和错误分析。
- 后续可加载模型预测，建立主动学习和困难样本流程。
- 支持图片、视频及多种视觉标签。

限制：

- 自身带有数据集和数据库概念。
- 如果同时把它作为主索引，会与SQLite和DVC形成多套事实来源。
- 对第一阶段的文件夹筛选而言依赖偏重。
- 建议使用独立环境，避免污染共享YOLO训练环境。

决策：第一阶段不强制安装。预留`FiftyOneAdapter`，后续只将其作为审查视图，正式版本仍由DVC、YAML和SQLite管理。

## 5. DVC

DVC面向机器学习大文件版本和可复现流水线。Git保存`.dvc`指针、参数和代码，实际视频及图片存放在DVC缓存或远程存储中。

优点：

- 文件按内容哈希存储，相同图片可以复用。
- 适合当前“完整累积数据集版本”策略。
- 可以追踪视频、抽帧结果、标注导出包和数据集发布。
- 后续可以把数据缓存迁移到NAS、对象存储或共享磁盘。
- 与Git提交形成清晰的数据版本历史。

限制：

- 新项目必须初始化Git和DVC。
- DVC不是业务数据库，不适合单独承担审批和状态流转。
- 使用者不应绕过发布命令手工修改冻结数据。

决策：作为核心版本组件。SQLite负责业务状态，DVC负责大文件内容，YAML负责独立版本快照。

## 6. Datumaro

Datumaro是计算机视觉数据集管理框架和CLI工具，可构建、转换和分析不同格式的数据集。

优点：

- 避免自行编写大量YOLO格式解析器。
- 适合导入Roboflow下载的标准视觉数据。
- 支持数据转换、过滤、合并和统计。
- MIT许可证便于二次集成。

限制：

- 不负责原始视频归档和业务版本命名。
- 通用校验不能覆盖固定测试集、视频来源和发布准入等业务规则。
- 不应把不同任务格式自动合并为同一数据集。

决策：作为Roboflow检测数据导入和格式复核核心库，外层增加本项目的来源、版本和跨集合校验。Datumaro 1.12的Roboflow YOLO导入器不解析Ultralytics分割多边形，因此segment标签由本项目的严格多边形解析器校验，不能假设检测和分割共用同一个Datumaro导入器。

## 7. CVAT

CVAT是成熟的自托管视觉标注平台，支持图片、视频、跟踪、质量控制、团队协作和多种数据格式。

优点：

- 可以直接上传视频进行逐帧标注。
- 视频跟踪和团队审核能力强。
- YOLO等格式导入导出成熟。

限制：

- 引入后会与Roboflow功能重叠。
- 自托管通常需要Docker和额外运维。
- 仍不能取代正式数据版本和训练制品治理。

决策：当前不采用。如果未来停止使用Roboflow，CVAT是首选替代标注平台。

## 8. Label Studio

Label Studio适合多类型数据标注，但当前目标是标准视觉检测与分割，且已选择Roboflow。继续引入会增加部署、权限和数据同步成本。

决策：当前不采用。

## 9. Supervision

Supervision提供视频处理、检测结果、跟踪、标注绘制等实用能力。它适合后续模型推理分析和样本自动预筛选，但不是数据版本管理工具。

决策：第一阶段不作为核心依赖，后续评估用于模型辅助抽帧和结果可视化。

## 10. YOLO模型兼容性

数据链路不应绑定到单一YOLO版本。正式任务配置同时记录：

```yaml
task_type: segment

model:
  framework: ultralytics
  family: yolo26
  weights: yolo26n-seg.pt

dataset:
  annotation_format: yolo-seg
```

第一阶段数据验收矩阵：

| 模型系列 | detect数据 | segment数据 |
|---|---:|---:|
| YOLOv8 | 支持 | 支持 |
| YOLO26 | 支持 | 支持 |

数据阶段只负责保证标签格式和任务类型正确。后续训练阶段由Ultralytics适配器加载实际权重。若未来某模型系列需要不兼容的Ultralytics或PyTorch版本，应创建独立运行环境适配器，不修改已冻结数据集。

## 11. 检测与分割的差异

检测标签表示矩形框，分割标签表示多边形。两类数据不能混合：

```text
detect  -> Roboflow Object Detection -> YOLO Detection
segment -> Roboflow Instance Segmentation -> YOLO Segmentation
```

后续ONNX验证同样必须按任务拆分。检测验证边界框和类别输出；分割还需验证mask系数、prototype mask及最终掩膜还原。

## 12. 推荐落地架构

```text
自研编排层
├── VideoRegistry
├── FrameExtractor
├── DuplicateDetector
├── SelectionManifest
├── RoboflowPackageImporter
├── DatasetValidator
└── DatasetReleaseService

成熟组件层
├── FFmpeg/OpenCV
├── ImageHash
├── Datumaro
├── DVC
└── SQLite
```

自研部分只处理业务身份、状态和发布规则，不重复开发通用视频解码、视觉数据格式解析和内容寻址存储。

## 13. 环境建议

不要把所有工具塞入当前7.6GB的共享YOLO训练环境。数据流水线锁定Datumaro 1.12.0，以兼容Python 3.10、Pillow 11和OpenCV 4。建议分为：

```text
yolo-data-pipeline-py310：Python 3.10、OpenCV、Datumaro、DVC、ImageHash
yolo-training-py39：PyTorch CUDA、Ultralytics、ONNX
fiftyone-workbench：后续需要FiftyOne时单独建立
```

数据准备通常不需要CUDA。将其与训练环境分离可以减少依赖冲突，并使视频和数据集工具在没有GPU的机器上运行。

## 14. 风险与控制

| 风险 | 控制措施 |
|---|---|
| DVC缓存本身增长 | 配置独立缓存盘和定期垃圾回收策略 |
| SQLite与YAML不一致 | 正式发布由单一事务式服务生成 |
| Roboflow类别顺序变化 | 导入时与任务配置强校验 |
| 检测和分割误混 | task_type、annotation_format、项目类型三重检查 |
| 测试集随版本漂移 | 固定测试基线，变化时发布新基线 |
| FiftyOne成为第二事实源 | 只做视图，不承担正式版本身份 |
| 不同YOLO环境不兼容 | 记录运行时并通过适配器隔离 |

## 15. 最终选型

核心采用DVC、Datumaro、FFmpeg/OpenCV、ImageHash和SQLite/YAML；继续使用Roboflow进行人工标注；FiftyOne延后作为可选审查工具；暂不使用CVAT和Label Studio。

这一组合能够复用成熟开源能力，同时保留对YOLOv8、YOLO26、detect和segment的独立控制，不会把数据资产绑定到某一个训练框架或标注平台。
