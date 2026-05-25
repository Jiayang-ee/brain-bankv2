# M6 交接说明

## 0. 当前状态

M6 批量采集基础实现已完成，测试可复现性已修复。当前进入 **验证与质量控制阶段**，下一步是：
- 批量运行与断点续跑验证
- 质量门禁确认
- 复核闭环机制

## 1. 项目位置

当前工作目录：

```text
/Users/wjy/Library/Mobile Documents/com~apple~CloudDocs/study/西南财经大学/faculty spider/faculty spiderv3
```

主数据库：

```text
data/faculty_spider_v3.sqlite
```

M6 的目标是在 M5 已跑通论文入口小批量验证的基础上，实现批量采集、断点续跑和质量控制。

## 2. 当前阶段状态

M4 官网入口已经完成可用闭环：

- 学校/学院教师页入口表已建立。
- Columbia Teachers College 跑通非目标学院样本。
- Wharton 跑通目标学院样本。
- 支持入口页发现、候选链接抓取、详情页解析、去重、华人姓名筛选、学科相关性筛选。
- 官网来源人员已导出到 `people.csv`。

M5 论文入口已经完成小批量验证：

- 期刊清单已导入。
- OpenAlex 和 Crossref 双来源检索已实现。
- Crossref 优先按 ISSN 查询。
- 近 5 年窗口过滤已实现。
- 期刊名严格过滤已实现。
- 论文去重合并已实现。
- 第一作者/通讯作者候选提取已实现。
- 华人姓名筛选已实现。
- 论文入口候选可聚合并写入 `people` 表。
- 论文采集质量报告已实现。

## 3. 当前数据规模

数据库当前核心规模：

```text
school_entrypoints = 6
journals = 51
papers = 221
people = 126
```

`people` 来源分布：

```text
official_site = 44
publication = 82
```

`papers` 来源分布：

```text
openalex,crossref = 79
openalex = 71
crossref = 70
crossref,openalex = 1
```

`people.discipline_review_status` 分布：

```text
accepted = 3
needs_review = 91
rejected = 32
```

论文入口导出规模：

```text
papers.csv = 221
publication_candidates.csv = 245
publication_candidates_chinese.csv = 82
publication_people_candidates.csv = 82
publication_quality_report.csv = 30
```

论文入口聚合候选状态：

```text
strong_candidate = 34
needs_review = 48
```

## 4. 关键文件

计划与交接：

- `docs/stage1_information_collection_plan.md`
- `docs/m5_publication_entry_summary.md`
- `docs/m6_handoff.md`

种子与分组：

- `data/seeds/us_top50_schools.csv`
- `data/seeds/school_entrypoints.csv`
- `data/seeds/publication_journal_groups.csv`

导出结果：

- `data/exports/people.csv`
- `data/exports/page_audit.csv`
- `data/exports/papers.csv`
- `data/exports/publication_candidates.csv`
- `data/exports/publication_candidates_chinese.csv`
- `data/exports/publication_people_candidates.csv`
- `data/exports/publication_quality_report.csv`

复核记录：

- `data/review/issues.csv`
- `data/review/known_issues.csv`

## 5. M6 期刊分组

M6 期刊分组文件：

```text
data/seeds/publication_journal_groups.csv
```

分组数量：

```text
default_batch = 21
needs_review = 10
broad_high_impact = 8
```

M6 默认应优先实现 `default_batch` 的批量采集。

`broad_high_impact` 包括 Nature、Science、PNAS、PAMI、JMLR 等宽口径高影响力期刊，主题噪声较高，建议单独批量处理。

`needs_review` 是小批量报告中缺机构较多或元数据质量待确认的期刊，建议先保守处理。

## 6. 已验证命令

导入期刊：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications import-journals 管理科学与工程相关期刊筛选清单.csv
```

论文小批量检索：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications search \
  --journals-limit 39 \
  --works-per-journal 5 \
  --from-year 2022
```

导出论文：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-papers \
  --csv data/exports/papers.csv
```

导出论文作者候选：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-candidates \
  --csv data/exports/publication_candidates.csv
```

导出华人姓名论文作者候选：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-candidates \
  --chinese-only \
  --csv data/exports/publication_candidates_chinese.csv
```

导出论文入口聚合人才候选：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-people-candidates \
  --csv data/exports/publication_people_candidates.csv
```

导出论文采集质量报告：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-quality-report \
  --csv data/exports/publication_quality_report.csv
```

将论文入口候选同步到 `people`：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications import-people-candidates
```

导出人员主表：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli official export-people \
  --csv data/exports/people.csv
```

运行测试：

```bash
pytest -q
```

当前测试结果：

```text
36 passed
```

## 7. 当前实现入口

论文入口相关代码：

- `src/faculty_spider_v3/publications/journal_list.py`
- `src/faculty_spider_v3/publications/openalex.py`
- `src/faculty_spider_v3/publications/crossref.py`
- `src/faculty_spider_v3/publications/pipeline.py`
- `src/faculty_spider_v3/publications/export.py`

命令入口：

- `src/faculty_spider_v3/cli.py`

数据库访问：

- `src/faculty_spider_v3/storage.py`

数据模型：

- `src/faculty_spider_v3/models.py`

测试：

- `tests/test_publications_pipeline.py`

## 8. M6 建议实现顺序

### 8.1 新增批量运行表

建议新增：

```text
publication_runs
publication_run_items
```

`publication_runs` 字段建议：

- `id`
- `run_name`
- `journal_group`
- `from_year`
- `works_per_journal`
- `sources`
- `status`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

`publication_run_items` 字段建议：

- `id`
- `run_id`
- `journal_id`
- `journal_name`
- `status`
- `cursor`
- `page`
- `attempts`
- `papers_seen`
- `papers_saved`
- `last_error`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

### 8.2 新增 M6 命令

建议新增：

```bash
publications batch-create
publications batch-run
publications batch-resume
publications batch-status
```

第一版可以先做：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications batch-run \
  --journal-group default_batch \
  --works-per-journal 50 \
  --from-year 2022 \
  --resume
```

### 8.3 支持断点续跑

要求：

- 已完成的 journal item 不重复跑。
- 失败的 item 可以重试。
- API 错误写入 `publication_run_items.last_error`。
- 同时保留 `review_issues`。

### 8.4 批量质量控制

M6 每次 batch run 完成后应自动生成或刷新：

- `papers.csv`
- `publication_candidates.csv`
- `publication_candidates_chinese.csv`
- `publication_people_candidates.csv`
- `publication_quality_report.csv`

建议在质量报告中增加 run 维度，或者新增：

```text
publication_quality_report_{run_id}.csv
```

## 9. 已知问题

### 9.1 作者缩写与全名

已记录：

```text
data/review/known_issues.csv
```

示例：

```text
H Zhang / Hong Zhang
```

当前不处理，不自动合并。后续整体复核阶段再做保守匹配。

### 9.2 broad_high_impact 主题噪声

Nature / Science / PNAS / PAMI / JMLR 等不应进入 M6 默认批量。它们应该单独跑，并结合论文标题、摘要、期刊方向做学科过滤。

### 9.3 缺机构问题

质量报告显示部分期刊缺机构较多。M6 不应盲目把缺机构比例过高的期刊大批量导入 `people`，建议先批量采论文，再按质量报告决定是否导入人员。

### 9.4 publication-only 人员缺字段

`primary_source_type = publication` 的人员目前只填高置信论文证据。邮箱、主页、title、department、研究方向等字段放到后续信息补全与复核阶段处理。

## 10. 新对话启动建议

新对话开始 M6 时，可以直接说：

```text
请阅读 docs/m6_handoff.md，开始实现 M6 的 publication_runs / publication_run_items 和 batch-run / resume 机制。
```

优先不要改 M4/M5 已有逻辑。先实现批量运行表和断点续跑，然后用 `default_batch` 做小规模验证。
