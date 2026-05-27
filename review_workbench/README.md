# M10 复核工作台

Flask 单页应用，为 M10 候选人复核提供质量看板、复核列表、证据查看和决策编辑功能。

## 启动

```bash
cd review_workbench
python3 app.py
# 访问 http://127.0.0.1:5000
```

或使用 Flask CLI：

```bash
export FLASK_APP=app.py
flask run --reload
```

## 功能覆盖

| 需求 | 路径 |
|------|------|
| 复核列表（姓名、机构、院系、title、email、homepage、source_url、priority、confidence、open issue、decision） | `/queue` |
| 筛选：未决策 / needs_review / approved / rejected，质量问题类型，优先级，search | `/queue?decision=undecided&gap=missing_school&search=...` |
| 排序：priority_score 等字段，升降序 | `/queue?sort=priority_score&dir=desc` |
| 看板：质量问题分布 + gap report | `/` |
| 证据查看：source_url、homepage、paper_links、open issues | `/record/<person_id>` |
| 决策编辑：decision / note / resolved_issue_types | `/record/<person_id>/edit`（POST 保存到 CSV） |
| 导出 CSV | `/export` |
| 刷新统计 | POST `/refresh` |
| 批量保存 CSV | POST `/save` |

## 数据源

- 复核列表：`data/review/wave1_review_queue.csv`（由 `export_wave1_review_queue` 生成，字段与 `WAVE1_REVIEW_FIELDS` 一致）
- 质量 gap 报告：`data/review/wave1_quality_gap_report.csv`（由 `export_wave1_quality_gap_report` 生成）
- Open issues：`data/review/issues.csv`

所有决策写入 `wave1_review_queue.csv` 的 `review_decision`、`review_decision_note`、`resolved_issue_types` 列，可被 `import_review_decisions()` 导入。

## 错误处理

- 非法 decision 值返回 400 + 具体错误
- 文件不存在时显示空队列（不崩溃）
- CSV 保存失败返回 500 + 错误信息
- 编辑 POST 后 redirect 到查看页，不吞掉用户输入

## 依赖

Flask（已在 `requirements.txt` 外系统安装）。如需隔离：

```bash
pip install flask
```