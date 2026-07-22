# TrainForge 桌面启动与关闭脚本设计

## 目标

在 Windows 桌面提供两个可双击脚本，让用户无需重复输入 PowerShell 命令即可启动或关闭本地 TrainForge 服务。

## 文件

- `C:\Users\chenNuo\Desktop\启动 TrainForge.cmd`
- `C:\Users\chenNuo\Desktop\关闭 TrainForge.cmd`

脚本本身不放入部署包，不会影响云端运行环境。

## 启动脚本

启动脚本调用同目录生成的 PowerShell 辅助脚本，以可靠处理中文路径、环境变量、健康检查和日志输出。

行为顺序：

1. 固定使用代码目录 `C:\Users\chenNuo\Desktop\YOLO识别\yolo_model_factory\.worktrees\windows-training-memory-guard`。
2. 固定读取主项目配置 `C:\Users\chenNuo\Desktop\YOLO识别\yolo_model_factory\configs\system.yaml`，该配置继续指向 `D:\YOLO_DATA`。
3. 检查 Python、npm、代码目录和配置文件是否存在；任一缺失时显示明确错误并暂停窗口。
4. 检查端口 8000：已有监听时不重复启动 API；无监听时设置 `PYTHONPATH` 和 `YOLO_FACTORY_SYSTEM_CONFIG` 后隐藏启动 Uvicorn。
5. 轮询 `/api/health`，最长等待 30 秒；失败时显示 `%TEMP%\trainforge-api.err.log` 末尾内容。
6. 检查端口 53257：已有监听时不重复启动前端；无监听时隐藏启动 Vite。
7. 轮询训练页面，最长等待 30 秒；失败时显示 `%TEMP%\trainforge-web.err.log` 末尾内容。
8. 两个服务均可访问后，使用默认浏览器打开 `http://127.0.0.1:53257/training`。
9. 成功后窗口显示 API、前端、数据目录和日志路径，等待用户按键关闭窗口。

启动脚本不会结束现有进程，不会重启正在运行的 API，也不会中断训练。

## 关闭脚本

行为顺序：

1. 显示警告：训练运行中关闭 API 可能中断训练。
2. 要求用户输入明确确认字符；其他输入直接取消。
3. 查找监听本机端口 8000 和 53257 的进程。
4. 仅结束这些监听进程，不按进程名称批量结束 Python、Node 或系统服务。
5. 输出实际停止的 PID 和端口；没有监听时显示服务未运行。
6. 不删除日志、数据库、数据集、模型或训练产物。

## 日志

- API 标准输出：`%TEMP%\trainforge-api.out.log`
- API 错误输出：`%TEMP%\trainforge-api.err.log`
- 前端标准输出：`%TEMP%\trainforge-web.out.log`
- 前端错误输出：`%TEMP%\trainforge-web.err.log`

每次启动前清空旧日志，避免历史错误干扰本次诊断。

## 验证

- 服务均未运行时，双击启动脚本后两个端口进入监听且健康检查通过。
- 服务已经运行时，重复双击不会创建重复监听进程。
- 启动成功后自动打开训练页面。
- 配置缺失时不启动 API，并显示缺失的绝对路径。
- 关闭脚本在未确认时不停止任何进程。
- 确认关闭后只释放 8000 和 53257，不影响其他 Python、Node 或 Windows 进程。
