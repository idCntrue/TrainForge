# Model Gate Diagnostics Design

**Date:** 2026-07-20

## Goal

Make a completed model-gate run understandable to a non-specialist. The model detail drawer must distinguish checks that block publication from advisory quality checks, summarize failures in Chinese, and expose sample-level technical evidence on demand.

## Scope

- Keep the existing gate calculations, thresholds, model lifecycle, and SQLite schema unchanged.
- Add a read-only API for the latest persisted gate report referenced by a model version.
- Present gate names, meaning, status, failure summary, thresholds, and recommendations in Chinese.
- Default to a concise summary. Allow users to expand failed checks to inspect sample-level evidence.
- Support the existing desktop drawer and mobile full-screen drawer.
- Improve the completion message so a successful HTTP request is not confused with all checks passing.

The feature does not rerun gates automatically, modify model artifacts, or store the full report in SQLite.

## User Experience

### Overall result

After a gate run, the drawer displays a summary such as:

> 4 checks passed, 1 check blocks publication, and 1 quality recommendation was not met.

Hard failures and advisory failures are visually and textually distinct. `quality_recommended` is explicitly described as advisory and does not count as a publication-blocking failure.

### Gate presentation

Internal keys are mapped to user-facing labels:

| Key | Chinese label | Role |
| --- | --- | --- |
| `training` | 训练已完成 | Hard gate |
| `pt` | PT 模型文件 | Hard gate |
| `onnx` | ONNX 模型文件 | Hard gate |
| `consistency` | PT 与 ONNX 推理一致性 | Hard gate |
| `independent_test_available` | 独立测试结果 | Hard gate |
| `quality_recommended` | 推荐发布质量 | Advisory |

Each row shows a short Chinese explanation. Failed rows can be expanded. Passed rows remain compact by default.

### Consistency failure details

The summary states how many validation samples failed, how many have different PT/ONNX detection counts, and whether box, confidence, or segmentation-mask thresholds failed.

Expanded sample rows show:

- image filename, without exposing an unnecessary absolute path;
- PT and ONNX prediction counts;
- failed prediction-pair count;
- actual box IoU against the `0.80` minimum;
- actual confidence delta against the `0.15` maximum;
- for segmentation, actual mask IoU against the `0.75` minimum;
- a concrete next action based on the failed dimension.

### Quality recommendation details

The UI uses the existing quality report to show its verdict, reasons, recommendations, weakest classes, and thresholds. It explains whether the issue is insufficient independent-test evidence or metrics below the recommended line. Mojibake or missing reason text falls back to a stable Chinese explanation derived from the structured verdict and thresholds.

### Completion feedback

- All hard gates pass: `门禁检查完成，可以发布。`
- A hard gate fails: `门禁检查完成，发现 N 项阻止发布的问题。`
- Only advisory quality is below recommendation: `硬门禁已通过，但模型质量尚未达到推荐线。`

## API Design

Add:

```http
GET /api/model-versions/{model_id}/gate-report
```

The endpoint:

1. Loads the model from the repository.
2. Returns `404` when the model does not exist.
3. Returns a structured `available: false` response when no report has been generated or a historical report file no longer exists.
4. Resolves `gate_report_path` and requires it to remain under the configured storage root.
5. Rejects paths outside the storage root and malformed/non-object JSON without exposing file contents or arbitrary paths.
6. Returns the parsed report with `available: true` when valid.

The response preserves numeric evidence from `result.json`; presentation text remains a frontend concern.

## Frontend Design

- Extend the API client and model view types with an optional gate diagnostic report.
- Load the report when a model drawer opens and reload it after running gates.
- Keep report-loading failure separate from the model list so the drawer remains usable.
- Add a focused presentation module that maps gate keys and structured report values to Chinese summaries and recommendations.
- Render a compact overall summary, gate rows, and collapsible failure detail panels in the existing model drawer.
- On mobile, keep controls and summaries full width and avoid horizontal tables; render sample evidence as stacked records.

## Error Handling

- Missing historical report: show `暂无诊断详情，请重新运行门禁。`
- Report still being generated: the existing operation loading state remains active until the synchronous request completes.
- Malformed or unsafe report: show a generic unavailable message; log/return a controlled API error without exposing server paths.
- Duplicate operation: retain the existing concurrency guard and explain that another gate run is still active.

## Testing

Backend tests cover:

- valid report retrieval;
- missing model;
- model with no report;
- missing report file;
- path outside storage root;
- malformed JSON and non-object JSON.

Frontend tests cover:

- Chinese gate labels and hard/advisory classification;
- consistency summaries for count, box, confidence, and mask failures;
- quality verdict explanations;
- report-unavailable fallback;
- completion message selection;
- compact and expanded rendering behavior.

## Acceptance Criteria

- A user can tell why a completed gate run did not pass without reading server logs or opening JSON files.
- A user can distinguish a publication blocker from a quality recommendation.
- For consistency failures, the UI identifies the failing sample and metric with the actual and required values.
- Existing model records and historical reports continue to work without a database migration.
- No absolute storage path is shown in the UI.
- Backend and frontend automated tests pass.
