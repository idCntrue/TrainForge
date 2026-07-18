export interface HelpSection {
  id: string
  title: string
  content: string[]
}

export interface HelpChapter {
  id: string
  title: string
  summary: string
  sections: HelpSection[]
}

export const helpChapters: HelpChapter[] = [
  { id: 'quick-start', title: '快速开始', summary: '从零完成第一个可推理的 YOLO 模型。', sections: [
    { id: 'first-project', title: '推荐操作顺序', content: ['进入任务管理创建检测或分割任务，并定义 class。', '在数据导入中上传图片，或导入视频并创建抽帧批次。', '在数据筛选中排除模糊、重复和无效帧，然后进入原生标注。', '完成标注后发布数据集版本，创建训练，注册并发布模型，最后运行推理。'] },
    { id: 'before-start', title: '开始前检查', content: ['系统状态应显示 API 与存储目录正常。训练前确认 NVIDIA 驱动、CUDA 和 Ultralytics 环境可用。', '任务类别一旦用于正式数据集，应谨慎修改；类别顺序会影响 YOLO 标签中的 class id。'] },
  ] },
  { id: 'workflow', title: '完整工作流', summary: '数据导入、视频抽帧、筛选、标注、发布、训练和推理。', sections: [
    { id: 'prepare-data', title: '数据准备', content: ['图片上传会创建可筛选的帧记录。任意活动批次都可在“数据筛选”中点击“追加图片”继续补充素材，内容完全相同的图片会自动跳过。追加到视频批次的图片会记录为独立“手动上传”来源，不继承视频时间戳，也不会改变原视频帧、抽帧参数或来源分组。', '已有批次也可以点击“追加视频抽帧”继续上传视频。系统只处理本次上传且内容不重复的视频，新抽取图片进入待筛选状态；已有图片、筛选状态、原生标注和已经发布的数据集版本保持不变。视频文件与抽帧图片统一写入云端受管存储，页面不会保存你电脑上的本地路径。', '数据筛选用于保留有效帧、拒绝低质量帧并处理重复组。抽帧间隔越小，图片数量越多；筛选结果是标注和发布的输入。'] },
    { id: 'annotate-release', title: '标注与发布', content: ['检测任务使用矩形框，分割任务使用多边形。先选择绘制工具，再在右侧“新建对象类别”中确认类别；创建完成后系统会自动回到选择模式并选中新对象。画布轮廓和对象列表使用一致的 #编号与类别颜色，点击任一已有对象都会进入选择模式。', '修改已有对象类别时，先选中对象，再点击“修改类别”。下拉变化只保存在本地草稿中，必须点击“保存到对象 #N”才会同步服务端；“取消修改”或 Escape 会丢弃草稿。删除入口位于选中对象卡片中，确认框会显示对象编号和类别，避免删错对象。', '审核通过后图片进入显著只读状态，可以检查对象但不能绘制、拖动、改类或删除；需要继续编辑时先点击“退回修改”。Escape 会依次取消类别草稿、SAM2/绘制草稿和对象选择。保存、删除或修改标注时系统使用 revision 防止覆盖并发修改，冲突时会刷新最新对象。', '左侧队列由服务端分页，每页 30 张；切换任务、状态、页面或图片会清空旧选择和工具草稿。队列缩略图使用服务端缓存，只有选中图片时才加载完整标注和原始图片。队列标题显示筛选后的总数，不是当前页数量；导出会读取该任务全部已审核记录，不受当前页和页面筛选影响。', '发布时“数据集名称”是面向用户的业务名称，会显示在版本列表、图片浏览和训练选择中；“导出名称”只用于标注产物归档，两者互不替代。名称相同的不同版本通过版本号区分，发布 ID 和下游引用保持稳定。回导 Roboflow 时直接选择导出的 ZIP 文件，系统上传、校验并归档；不要填写 Windows 或服务器绝对路径。数据集版本是不可变训练输入。'] },
    { id: 'train-deploy', title: '训练到推理', content: ['训练运行选择数据集版本、官方基础权重或上传的自定义 .pt、epoch、batch、图像尺寸和设备。训练结束后注册候选模型。', '候选模型通过门禁后才能发布。推理工作台只使用已发布模型，并通过浏览器上传单图、批量图片或视频。'] },
  ] },
  { id: 'pages', title: '页面使用说明', summary: '每个菜单的职责、输入、输出和常用操作。', sections: [
    { id: 'data-pages', title: '数据页面', content: ['任务管理：维护任务类型和类别。已有任务可点击操作列的铅笔按钮编辑中文显示名称；Class ID、英文标识和顺序保持锁定，避免已有 YOLO 标注发生类别错位。更多菜单提供安全删除和级联删除。', '数据导入：管理图片、视频和抽帧批次。数据筛选：查看全部帧并决定去留。原生标注：绘制、编辑和审核标注。数据集版本：浏览发布版本中的所有图片，并管理版本生命周期。'] },
    { id: 'model-pages', title: '模型页面', content: ['训练运行：创建、观察、取消和删除训练；官方模型直接选择，自定义权重通过 .pt 文件上传。模型中心：注册制品、执行门禁、发布、归档和删除模型。', '推理工作台：选择模型、运行时和置信度，上传输入素材，并查看输出媒体与检测结果。上传完成前不要关闭页面。'] },
    { id: 'delete-rules', title: '删除与回收站', content: ['图片可单张、当前页多选或“选择全部匹配”后移入回收站。图片和原标注保留 7 天；回收站中可恢复到原批次，也可主动永久删除。API 启动后会立即清理一次过期项，之后每 24 小时清理一次。', '永久删除只清理活动批次中的源图片、帧记录和原标注，不会改写已经发布的不可变数据集版本。普通资源删除仍保护下游依赖；级联删除属于不可恢复操作，执行前应确认影响范围。'] },
  ] },
  { id: 'models', title: '模型与训练', summary: '任务类型、基础模型、参数与制品选择。', sections: [
    { id: 'task-model', title: '选择任务与模型', content: ['detect 用于矩形框目标检测，segment 用于像素级实例轮廓。基础权重必须与任务类型兼容。', '小模型训练和推理更快，适合验证流程；更大模型通常需要更多显存和更长训练时间。'] },
    { id: 'training-params', title: '训练参数', content: ['epoch 决定完整遍历数据集的次数；batch 受显存限制；image size 越大越有利于小目标，但训练成本更高。新建训练默认使用 CPU，官方基础模型必须主动选择；确认服务器 GPU 可用后才能切换到 CUDA 0。', '类别别名是可选的模型展示名称。例如 `emergency-stop-sign` 可设置为“急停标识”。别名会写入训练配置并成为模型和推理结果的类别名称，但不会修改原数据集标签数字、Class ID 或类别顺序；内部实验可全部留空。', '首次训练建议使用保守 batch，并先跑少量 epoch 验证数据、类别和输出目录是否正确。'] },
  ] },
  { id: 'data', title: '数据与标注规范', summary: '图片、视频、类别和 YOLO 标签的质量要求。', sections: [
    { id: 'media', title: '媒体要求', content: ['优先使用清晰、曝光稳定且覆盖真实场景变化的图片。训练集不应大量包含相邻近似视频帧。', '视频抽帧后先做重复检测和人工筛选，避免训练集、验证集出现高度相似画面导致指标虚高。'] },
    { id: 'classes', title: '类别规范', content: ['类别名称应稳定、互斥且可由标注人员一致判断。避免同时使用含义重叠的上位类和下位类。', 'class id 从 0 开始并依赖类别顺序。数据集发布后，类别映射会随版本固定。'] },
  ] },
  { id: 'troubleshooting', title: '故障排查', summary: '删除失败、请求失败、训练失败和数据为空的处理方式。', sections: [
    { id: 'request-errors', title: '页面无响应或请求失败', content: ['先查看系统状态。开发环境页面通过同源 /api 代理访问后端，若出现 Failed to fetch，应确认前端与 API 进程都在运行。', '修改 Vite 代理配置后必须完全重启前端开发服务，浏览器刷新不能重新加载代理配置。'] },
    { id: 'delete-errors', title: '删除失败', content: ['HTTP 409 表示资源仍被下游引用，不是按钮失效。按提示先删除下游资源，或在明确影响后使用级联删除。', '永久删除会清理 D:\\YOLO_DATA 下对应制品，操作不可恢复。'] },
    { id: 'training-errors', title: '训练失败', content: ['检查数据集 YAML、图片与标签路径、类别数量、基础权重任务类型和 GPU 显存。', '中断运行可刷新状态并查看日志；平台保留运行目录和状态，便于恢复或重新创建训练。'] },
  ] },
  { id: 'deployment', title: '部署与运维', summary: '本地运行、存储、备份和后续云端部署接口。', sections: [
    { id: 'bounded-training', title: 'CPU 安全模式与资源保底', content: ['无 GPU 云服务器默认启用 CPU 安全模式：检测任务默认 Batch 2、上限 4；分割任务默认 Batch 1、上限 1；图像尺寸默认 320、上限 640；训练 worker 为 0，CPU 线程数为 4。超过上限的请求会在创建训练记录前被拒绝。', 'API 容器默认使用 API_MEMORY_LIMIT=10g、API_CPU_LIMIT=6、API_SHM_SIZE=2gb、API_PIDS_LIMIT=256。资源耗尽导致进程退出时，训练任务会显示容器内存或进程资源达到限制，而不是拖垮整台服务器。', '训练开始前会先清理可再生成缓存和过期暂存文件，再检查是否同时保留至少 8 GiB 和 10% 可用磁盘；仍建议保持 10-12 GiB 以上。数据库、数据集和模型权重不会被自动清理。'] },
    { id: 'recycle-storage', title: '回收站与对象存储边界', content: ['回收站元数据保存在现有 SQLite，图片仍位于 /data。过期清理由 API 内的轻量线程执行，不需要 Redis 或 Celery；当前部署必须保持单 API 实例、单 worker，多实例互斥尚未实现。', '文件读写已通过本地对象存储接口隔离，并预留 storage_provider 与 storage_key。未来接入阿里云 OSS 时应实现同一 put/open/exists/delete/size 契约，并将 SQLite 迁移到 PostgreSQL 后再扩展多实例；当前版本不会自动把历史文件上传到 OSS。'] },
    { id: 'package-update', title: '部署包一键安全更新', content: ['旧版本首次升级执行：tar -xOf /tmp/yolo-model-factory-deploy.tar.gz yolo_model_factory/docker/update-from-package.sh | sh -s -- /tmp/yolo-model-factory-deploy.tar.gz。它直接读取包内脚本，不需要先覆盖线上源码；首次成功后也可运行 sh /opt/yolo_model_factory/docker/update-from-package.sh /tmp/yolo-model-factory-deploy.tar.gz。', '脚本会在临时目录校验并构建，复用线上 .env，自动备份 SQLite，健康检查成功后才切换源码。更新包不会替换 DATA_DIR、MODEL_DIR、/data、/models 或线上 factory.db。失败时保留原源码并由 deploy.sh 回滚旧镜像；成功后旧源码目录也会作为带时间戳的备份保留。'] },
    { id: 'local', title: '本地部署', content: ['前端默认运行在 127.0.0.1:53257，API 默认运行在 127.0.0.1:8000，浏览器统一通过 /api 访问。', '默认存储根目录为 D:\\YOLO_DATA。备份时应同时保存数据库、配置、数据集版本和模型制品。'] },
    { id: 'cloud-requirements', title: '云服务器要求', content: ['推荐 Ubuntu 22.04、8 核 CPU、32 GB 内存、100 GB 系统盘，并为 /srv/yolo-factory/data 单独准备容量大于现有 D:\\YOLO_DATA 两倍的数据盘。无 GPU 也能运行数据管理、CPU 训练、ONNX/CPU 推理和 SAM2，但训练与分割速度会明显降低。', '有 NVIDIA GPU 时显存建议至少 8 GB，并安装驱动、Docker Engine、Docker Compose 插件和 NVIDIA Container Toolkit。执行 nvidia-smi 与 docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi，两个命令都成功后再启用 GPU 编排。'] },
    { id: 'cloud-security', title: '安全边界', content: ['当前版本是单用户系统，没有登录、租户隔离和权限控制。只能部署在私有网络，或通过云安全组仅允许固定办公 IP 访问；在补齐身份认证和 HTTPS 前不要直接暴露到公网。', 'SQLite、进程内重任务锁和本地子进程恢复要求 API 保持单实例、单 worker。不要通过增加容器副本扩容；后续应先迁移 PostgreSQL、任务队列和对象存储。'] },
    { id: 'compose', title: 'Docker Compose 部署', content: ['宿主机创建 /srv/yolo-factory/data 和 /srv/yolo-factory/models，将项目放在 /opt/yolo-model-factory，并从 .env.docker.example 生成 .env。DATA_DIR 指向数据目录，MODEL_DIR 指向权重目录，WEB_PORT 控制访问端口。', '无 GPU 主机执行 docker compose build 和 docker compose up -d；训练任务选择 cpu，推理选择 ONNX / CPU。有 GPU 主机执行 docker compose -f compose.yaml -f compose.gpu.yaml up -d --build，额外编排文件才会申请 NVIDIA 设备。', '使用 docker compose ps 查看健康状态，docker compose logs -f api 查看 API、训练和推理启动错误。浏览器只访问 Web 端口，Nginx 会同源代理 /api。'] },
    { id: 'cloud-upload', title: '云端文件上传', content: ['云端浏览器无法把 C:\\、D:\\ 或 macOS 本地路径交给容器读取。图片、视频、标注 ZIP、推理素材和自定义 .pt 都必须使用页面的浏览器上传控件。', 'Nginx 当前允许最大 20 GB 请求并关闭请求缓冲；超大视频仍受带宽、浏览器、云负载均衡超时和磁盘剩余空间限制。高级服务器目录接口只允许 /data/imports 下的文件。'] },
    { id: 'cicd', title: 'CI/CD 一键 Docker 部署', content: ['仓库包含 .github/workflows/deploy.yml。配置 GitHub Environment production，并添加 DEPLOY_HOST、DEPLOY_USER、DEPLOY_SSH_KEY 三个 Secrets；私钥不得写入仓库。推送 main 或手动运行 workflow_dispatch 后，会先运行后端测试、前端测试和构建，再上传源码并通过 SSH 部署。', '服务器端 docker/deploy.sh 使用提交 SHA 构建独立镜像标签，切换前备份 factory.db，启动后检查 /api/health；健康检查失败会 rollback 到旧镜像。首次启用前必须保留 /opt/yolo_model_factory/.env。Gitee 流水线也可通过 SSH 调用同一脚本。'] },
    { id: 'migration', title: 'Windows 历史数据迁移', content: ['先停止本机 API，完整备份 D:\\YOLO_DATA，然后用 robocopy、压缩包或 rsync 将内容复制到云端 /srv/yolo-factory/data。迁移期间禁止本机和云端同时写入数据库。', '首次启动 API 前执行 docker compose run --rm api yolo-factory migrate-storage-paths --database /data/registry/factory.db --old-root "D:\\YOLO_DATA" --new-root /data。默认是 dry-run，只报告待更新、缺失和存储根目录外路径。确认报告后追加 --apply；工具会先创建数据库时间戳备份，再在事务中转换路径。', 'D:\\videoTmp 等存储根目录外路径不会自动改写，必须先把对应文件复制到 /data/imports，再人工重新导入或创建推理。迁移完成后再次运行 dry-run，待更新数应为 0。'] },
    { id: 'backup-restore', title: '备份恢复与升级', content: ['备份恢复必须同时覆盖 /data、/data/task-configs 和 /models。备份前执行 docker compose stop api，复制数据后再启动，避免 SQLite、WAL 和制品文件处于不一致状态。', '日常升级优先使用 CI/CD 或在服务器执行 ./docker/deploy.sh <镜像标签>。脚本自动做数据库快照和健康回滚，但不能代替定期完整数据备份；不要只恢复 factory.db 而遗漏对应制品。'] },
    { id: 'cloud-troubleshooting', title: '容器故障排查', content: ['GPU 不可见时在宿主机和 API 容器内分别运行 nvidia-smi，并检查 Compose 的 GPU 设备声明和 NVIDIA Container Toolkit。出现 CUDA out of memory 时减小 batch 或 image size。', 'Permission denied 表示 /data 或 /models 的宿主目录权限不允许容器用户访问；No space left on device 要同时检查数据盘、Docker 镜像层和训练临时目录。', '页面 502 或健康检查失败时查看 docker compose logs api；大视频上传出现 413 或超时时检查 Nginx client_max_body_size、proxy_read_timeout 和云负载均衡超时。记录仍显示 Windows 路径时重新运行迁移 dry-run 并处理外部路径报告。'] },
  ] },
  { id: 'training-quality', title: '训练质量与失败恢复', summary: '预设、诊断、独立测试和质量结论。', sections: [
    { id: 'training-presets', title: '训练方案', content: ['流程验证：10 Epoch、320px、Batch 1，只用于验证数据到模型的完整流程。CPU 均衡训练：150 Epoch，检测 Batch 2、分割 Batch 1，并启用保守增强与早停。GPU 高质量训练：200 Epoch、Batch 8，需要 CUDA。自定义参数仍受服务器资源上限约束。'] },
    { id: 'failure-recovery', title: '训练失败与恢复', content: ['resource_limit 表示进程被外部强制终止，通常与内存或容器资源限制有关，但不等于已确认 OOM。disk_full、device_unavailable、base_model_unavailable、dataset_invalid 和 dependency_import 需要先解决对应前置问题。', '失败详情会显示最后成功 Epoch、真实指标、保留产物和技术诊断。安全重试会创建参数更保守的子任务；评估已有最佳权重只运行独立测试，不会继续优化器状态或修改原失败任务。'] },
    { id: 'quality-verdicts', title: '如何理解模型质量', content: ['Precision 表示模型报出的结果中有多少正确；Recall 表示真实目标中有多少被找到。mAP50 是宽松综合精度，mAP50-95 是更严格、更适合作为质量判断的综合精度。', 'validation 用于训练过程选参，test 是训练完成后只评估一次的独立证据。少于 30 张测试图片或任一类别少于 10 个测试实例时，系统只能给出“证据不足”，不会因为 mAP 偶然很高就建议发布。当前阈值是初始工程建议，不等同于所有业务的验收标准。'] },
  ] },
  { id: 'glossary', title: '术语表', summary: '平台内核心对象和状态的统一定义。', sections: [
    { id: 'terms', title: '核心术语', content: ['任务：任务类型与类别定义。数据来源：上传图片或导入视频。抽帧批次：一次视频抽帧配置及其结果。', '数据集版本：不可变的训练输入。训练运行：一次可追踪训练过程。候选模型：尚未发布的训练制品。已发布模型：通过门禁、可用于推理的模型。'] },
  ] },
]

export function searchHelp(query: string): HelpChapter[] {
  const keyword = query.trim().toLocaleLowerCase()
  if (!keyword) return helpChapters
  return helpChapters.filter((chapter) => [chapter.title, chapter.summary, ...chapter.sections.flatMap((section) => [section.title, ...section.content])].join('\n').toLocaleLowerCase().includes(keyword))
}
