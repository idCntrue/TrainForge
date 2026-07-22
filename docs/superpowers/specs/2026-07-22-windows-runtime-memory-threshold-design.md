# Windows 训练运行时内存阈值设计

## 问题

Windows 训练启动门禁与逐轮运行门禁共用 `TRAINING_MIN_AVAILABLE_COMMIT_GB=8`。模型加载和训练开始后，系统提交内存会正常下降；当剩余提交内存从 8 GiB 附近轻微波动到 7.96 GiB 时，运行门禁会主动停止训练，即使距离原生内存分配失败仍有较大空间。

当前运行门禁已经不检查可用物理内存，因此本次停止的直接原因仅是 7.96 GiB 小于共用的 8 GiB 提交内存阈值。根因是启动阶段和运行阶段采用了相同的安全余量，而两个阶段的风险模型不同。

## 目标

- 保持训练启动前的保守检查，避免在资源已经不足时创建训练进程。
- 训练运行中允许模型正常占用更多提交内存，减少接近 8 GiB 时的误停止。
- 在提交内存接近耗尽前仍保留轮次间安全停止，避免重新出现 OpenCV 原生崩溃和不完整训练产物。
- 保持 Linux 云端行为不变。

## 设计

`TrainingResourcePolicy` 增加独立字段：

```text
runtime_min_available_commit_gb = 4
```

环境变量：

```text
TRAINING_RUNTIME_MIN_AVAILABLE_COMMIT_GB=4
```

门禁规则：

- 启动前 `validate_memory_snapshot()`：
  - 剩余提交内存至少 `min_available_commit_gb`，默认 8 GiB。
  - 可用物理内存至少 `min_available_memory_gb`，默认 4 GiB。
- 训练运行中 `validate_runtime_memory_snapshot()`：
  - 剩余提交内存至少 `runtime_min_available_commit_gb`，默认 4 GiB。
  - 可用物理内存只作为诊断信息，不触发停止。
- Windows 指标不可用或 Linux 仅提供 cgroup 指标时，不执行 Windows 提交内存门禁。

因此，7.96 GiB 提交内存和 2.15 GiB 物理内存会继续训练；3.99 GiB 提交内存会在下一轮开始前安全停止。

## 配置校验

- `TRAINING_RUNTIME_MIN_AVAILABLE_COMMIT_GB` 必须是正整数。
- 运行阈值必须小于或等于启动提交内存阈值，避免配置语义倒置。
- 默认值为 4 GiB，不需要用户修改本地环境即可生效。

## 错误信息

运行时停止信息继续显示实际剩余提交内存和可用物理内存。底层 `InsufficientTrainingMemory` 记录本次实际采用的运行阈值，使诊断详情能够说明“至少 4 GiB”，而不是错误显示启动阈值 8 GiB。

## 文档

README 配置表新增运行时阈值，并明确：

- `TRAINING_MIN_AVAILABLE_COMMIT_GB` 用于启动前检查。
- `TRAINING_RUNTIME_MIN_AVAILABLE_COMMIT_GB` 用于训练逐轮检查。
- 不建议设置低于 4 GiB；完全关闭门禁不在本次支持范围内。

## 测试

- 默认策略的启动阈值为 8 GiB，运行阈值为 4 GiB。
- 环境变量可覆盖运行阈值。
- 非正整数被拒绝。
- 运行阈值高于启动阈值被拒绝。
- 启动门禁仍拒绝 7.96 GiB 提交内存。
- 运行门禁接受 7.96 GiB 提交内存和 2.15 GiB 物理内存。
- 运行门禁拒绝低于 4 GiB 的提交内存，并在异常详情中记录 4 GiB 要求。
- 现有训练执行器和适配器测试全部通过。

## 非目标

- 不关闭 Windows 内存保护。
- 不主动结束其他 Windows 进程。
- 不修改 Batch、Workers、Cache 或数据增强参数。
- 不修改 Linux 云端的磁盘、cgroup 或训练资源策略。
