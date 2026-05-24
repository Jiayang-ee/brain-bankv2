# M5 论文入口阶段总结

## 1. 阶段目标

M5 的目标是跑通论文入口数据流，并用小批量真实数据验证 OpenAlex 与 Crossref 的可用性。

本阶段不做全量抓取。全量或准全量抓取放到 M6，原因是 M6 需要断点续跑、批次状态、限速、质量报告和异常恢复机制。

## 2. 已完成能力

### 2.1 期刊清单导入

已支持导入管理科学与工程相关期刊清单：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications import-journals 管理科学与工程相关期刊筛选清单.csv
```

导入后写入 `journals` 表，保留：

- 期刊名称
- ISSN
- 学校级别
- 人才库用途
- 方向备注

### 2.2 OpenAlex + Crossref 检索

已实现：

- OpenAlex 按 source / journal 查询。
- Crossref 优先按 ISSN 查询。
- 两个来源同时跑，按标题、年份、期刊合并。
- 只保留近 5 年窗口内的论文。
- 严格过滤期刊名，避免 Crossref 近似匹配污染。

当前验证窗口为：

```text
2022-2026
```

### 2.3 论文与作者候选导出

已生成：

- `data/exports/papers.csv`
- `data/exports/publication_candidates.csv`
- `data/exports/publication_candidates_chinese.csv`
- `data/exports/publication_people_candidates.csv`

论文候选支持：

- 第一作者
- 通讯作者
- 作者机构
- DOI / paper_url
- 期刊级别
- 年份
- 华人姓名评分

### 2.4 论文候选进入 people

已支持把论文入口聚合候选写入 `people` 表。

规则：

- 官网已有同名人员：补充论文统计与论文链接。
- 官网没有出现过的人：新增为 `publication` 来源人员。
- 新增人员只填已有高置信信息。
- 官网字段如 `email`、`title`、`department`、`homepage` 暂不推断。
- `review_status = needs_review`。

命令：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications import-people-candidates
```

### 2.5 质量报告

已新增质量报告：

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-quality-report \
  --csv data/exports/publication_quality_report.csv
```

质量报告字段：

- `journal`
- `achievement_level`
- `papers_count`
- `openalex_count`
- `crossref_count`
- `merged_count`
- `candidates_count`
- `chinese_candidates_count`
- `missing_author_count`
- `missing_affiliation_count`
- `source_errors`

## 3. 当前真实数据规模

本阶段已对英文、有 ISSN、A+/A1/A2 期刊做小批量采集。

采集参数：

```text
target_journals = 39
works_per_journal = 5
from_year = 2022
sources = openalex,crossref
```

结果：

```text
papers = 221
publication_candidates = 245
publication_candidates_chinese = 82
publication_people_candidates = 82
people = 126
```

`people` 来源分布：

```text
official_site = 44
publication = 82
```

论文来源覆盖：

```text
openalex,crossref = 79
openalex = 71
crossref = 70
crossref,openalex = 1
```

期刊级别覆盖：

```text
A+(TOP) = 20
A+ = 97
A1 = 74
A2 = 30
```

论文入口人才候选状态：

```text
strong_candidate = 34
needs_review = 48
```

## 4. M6 期刊分组

已新增：

```text
data/seeds/publication_journal_groups.csv
```

分组：

- `default_batch`：M6 默认批量采集组。
- `broad_high_impact`：综合或宽主题高影响力期刊，单独批量采集。
- `needs_review`：小批量质量报告显示缺机构较多、匹配质量待确认的期刊。

默认进入 M6 的期刊只包括主题更贴近管理科学、运筹、信息系统、运营管理、组织管理、交通运筹等方向的期刊。

`Nature / Science / PNAS / PAMI / JMLR / 统计学宽口径期刊` 暂不进入默认组，后续作为高影响力补充组单独处理。

## 5. 已知问题

### 5.1 作者缩写与全名归并

已记录到：

```text
data/review/known_issues.csv
```

示例：

```text
H Zhang / Hong Zhang
```

当前不做自动合并。后续整体复核阶段实现保守身份归并，低置信只导出复核 CSV。

### 5.2 Broad journals 主题噪声

`Nature / Science / PNAS / PAMI / JMLR` 等能产生高水平候选，但与管理科学与工程的主题相关性不稳定。

处理策略：

- 不进入 M6 默认批量。
- 作为 `broad_high_impact` 单独跑。
- 后续需要更强的学科过滤或论文主题过滤。

### 5.3 缺机构期刊

质量报告显示部分期刊缺机构较多，例如：

- `AUTOMATICA`
- `JOURNAL OF MARKETING`
- `JOURNAL OF MARKETING RESEARCH`
- `EUROPEAN JOURNAL OF OPERATIONAL RESEARCH`
- `PRODUCTION AND OPERATIONS MANAGEMENT`

处理策略：

- 暂标为 `needs_review`。
- M6 默认批量前先检查 Crossref/OpenAlex 是否有更好的查询方式。
- 必要时以后接 Semantic Scholar 或出版社页面补充。

### 5.4 publication-only 人员字段不完整

论文入口新增到 `people` 的人员目前主要有：

- `name`
- `school`，暂存作者机构
- `publication_stats_json`
- `paper_links_json`
- `publications_json`
- `primary_source_type = publication`

缺失字段包括：

- email
- title
- department
- personal_homepage
- research_interests
- biography

这些字段放到后续整体信息补全与复核阶段处理，不在 M5 里自动推断。

## 6. 已验证命令

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications search \
  --journals-limit 39 \
  --works-per-journal 5 \
  --from-year 2022
```

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-papers \
  --csv data/exports/papers.csv
```

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-candidates \
  --csv data/exports/publication_candidates.csv
```

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-candidates \
  --chinese-only \
  --csv data/exports/publication_candidates_chinese.csv
```

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-people-candidates \
  --csv data/exports/publication_people_candidates.csv
```

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications export-quality-report \
  --csv data/exports/publication_quality_report.csv
```

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications import-people-candidates
```

```bash
PYTHONPATH=src python3 -m faculty_spider_v3.cli official export-people \
  --csv data/exports/people.csv
```

## 7. M6 准备清单

M6 目标是批量采集与质量控制，不再只是小批量验证。

M6 需要新增或完善：

1. `publication_runs`
   - `run_id`
   - `source`
   - `from_year`
   - `works_per_journal`
   - `journal_group`
   - `status`
   - `started_at`
   - `finished_at`

2. `publication_run_items`
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

3. 断点续跑
   - `--resume`
   - 按 `run_id` 恢复。
   - 已完成期刊不重复请求。

4. 限速与重试
   - source 级别限速。
   - Crossref / OpenAlex 分别控制请求间隔。
   - 错误写入 `review_issues` 和 run item。

5. 分组采集
   - `default_batch`
   - `broad_high_impact`
   - `needs_review`

6. 批量质量报告
   - 每次 run 自动生成质量报告。
   - 和历史 run 对比。
   - 缺作者、缺机构、来源错误超过阈值的期刊不自动进入 people。

## 8. 进入 M6 的判断

M5 已完成进入 M6 的前置条件：

- 论文入口能真实跑通。
- 双来源能合并。
- 华人姓名筛选已接入。
- publication-only 人员可进入 `people`。
- 期刊质量报告可导出。
- 已有 M6 期刊分组文件。

下一阶段可以开始实现 M6 的批量运行表和断点续跑机制。
