# 第一阶段：信息采集计划

## 1. 阶段目标

第一阶段的目标是搭建一个可长期维护的信息采集系统，用于形成管理科学与工程相关方向的人才数据库。系统先服务于美国 Top 50 高校范围内的疑似华人候选人，后续再扩展到更多国家、学校和数据源。

第一阶段不追求一次性采全所有字段，而是建立稳定的数据流：

1. 从官网发现并下载 faculty 相关页面。
2. 从期刊白名单查找近 5 年论文，识别第一作者和通讯作者。
3. 对缺失字段做受控补充。
4. 对候选人去重、合并、评分，并导出 CSV 复核文件。

## 2. 已确认决策

1. 初始学校种子列表使用美国 Top 50 高校。
2. 本地 LLM 暂时只保留入口、接口和触发规则，具体运行方式后续开发。
3. 论文元数据来源中，OpenAlex 和 Crossref 同时运行，之后进行去重合并；Semantic Scholar、DBLP 和人工导入作为补充来源。
4. 复核格式只导出 CSV，不生成本地 HTML 复核包。
5. 年龄字段同时保留 `age` 和 `career_stage`。`age` 可空，优先使用明确来源；`career_stage` 用于表达博士、博士后、助理教授、副教授、教授等阶段。

## 3. 第一版范围

包含：

- 美国 Top 50 高校。
- 管理科学与工程相关学院、系、中心、实验室和期刊。
- 博士、博士后、助理教授、副教授、教授、研究教授、讲师，以及国际上相近的岗位称谓。
- 官网页面和论文入口产生的候选人。
- 疑似华人姓名候选人。
- 照片、教育背景、导师等可公开采集字段。

暂不包含：

- 全自动 Google Scholar 抓取。
- 付费数据库或登录后才能访问的论文元数据抓取。
- 基于弱来源自动推断年龄。
- 没有种子列表和限速策略的大规模全球爬取。
- 本地 LLM 的实际运行适配。
- CSV 之外的本地复核界面。

## 4. 目标输出

### 4.1 人员主表字段

最终导出的人员记录围绕 `people` 表生成，目标字段包括：

- `name`
- `age`
- `career_stage`
- `email`
- `school`
- `department`
- `field`
- `research_direction`
- `title`
- `source_url`
- `primary_source_type`
- `personal_homepage`
- `research_interests`
- `biography`
- `publications`
- `publication_stats`
- `paper_links`
- `photo_url`
- `photo_path`
- `education`
- `advisor`
- `confidence_score`
- `review_status`

不设置全局必填字段。不完整记录可以入库，但会通过 `confidence_score`、`review_status` 和 `review_issues` 标记后续处理优先级。

### 4.2 复核文件

第一阶段只导出 CSV：

- `data/exports/people.csv`：可使用的人才库结果。
- `data/exports/people_review.csv`：需要人工检查的候选人。
- `data/review/issues.csv`：问题记录文件，记录身份冲突、低置信度、姓名筛选不确定、论文匹配不确定等问题。

## 5. 总体数据流

```text
美国 Top 50 学校种子
  -> 官网链接发现
  -> 页面下载与 raw_html 保存
  -> HTML 规则解析
  -> 必要时标记 LLM 待处理
  -> 华人姓名评分
  -> people / review_issues

期刊白名单
  -> OpenAlex + Crossref 并行检索
  -> 论文结果去重合并
  -> Semantic Scholar / DBLP / 人工导入补充
  -> 第一作者与通讯作者抽取
  -> 华人姓名评分
  -> person_papers / publication_stats / people / review_issues

不完整候选人
  -> 第三方结构化来源补充
  -> 合并去重
  -> CSV 导出
```

## 6. 管线设计

### 6.1 官网入口管线

职责：

- 从美国 Top 50 高校种子出发。
- 发现学校、学院、系、研究中心和 faculty 相关页面。
- 下载页面并保存原始 HTML。
- 使用规则解析提取人员信息。
- 判断是否需要进入 LLM 待处理队列。
- 输出官网来源候选人和问题记录。

主要步骤：

1. `official import-seeds` 导入美国 Top 50 学校种子。
2. `official discover` 发现 faculty 列表页、个人主页和相关组织页。
3. `official fetch` 下载页面，保存 `raw_html_path`。
4. `official crawl` 按批次递归消费候选链接队列。
5. `official extract-html` 使用规则解析个人详情页和 faculty 列表页中的个人卡片。
6. `official extract-llm --trigger-only` 只标记需要 LLM 的页面，不实际调用模型。
7. 运行华人姓名评分，低分跳过，边界样本写入 `review_issues`。
8. `official export-people` 和 `official audit-pages` 导出官网入口结果和页面审计。

官网入口优先提取：

- 姓名、title、学校、部门、email。
- 个人主页、研究兴趣、简介、发表论文。
- 照片、教育背景、导师。
- 公开可见的职业阶段信息。

### 6.2 论文入口管线

职责：

- 导入管理科学与工程相关期刊白名单。
- 查找近 5 年命中期刊的论文。
- 识别第一作者和通讯作者。
- 记录每篇论文链接。
- 按成果级别统计数量。
- 输出论文来源候选人和问题记录。

主要步骤：

1. `publications import-journals` 导入期刊白名单。
2. `publications search --source openalex,crossref` 同时查询 OpenAlex 和 Crossref。
3. `publications merge-results` 按 DOI、标题、年份和期刊去重合并。
4. 必要时使用 Semantic Scholar、DBLP 或人工导入补充。
5. `publications extract-authors` 抽取第一作者和通讯作者。
6. `publications update-stats` 聚合 `publication_stats`。
7. 对作者姓名做华人姓名评分。

论文元数据来源优先级：

1. OpenAlex 和 Crossref 同时运行，然后合并。
2. Semantic Scholar 用于补充摘要、作者主页、引用和开放论文链接。
3. DBLP 用于计算机科学、信息系统及相关方向。
4. 人工导入 CSV/BibTeX/RIS 用于 API 覆盖不足的期刊。

论文成果统计指标：

- `last_5_year_total`
- `first_author_total`
- `corresponding_author_total`
- `top_total`
- `a_plus_total`
- `a_total`
- `a1_total`
- `a2_total`
- `level_counts_json`

### 6.3 信息补充管线

职责：

- 选择信息不完整但身份线索较强的候选人。
- 从结构化第三方来源补充主页、机构、研究方向、论文身份等信息。
- 不用弱证据覆盖已复核字段。

第一阶段只保留入口和基本流程，不把 Google Scholar 自动抓取作为主功能。

### 6.4 合并与复核管线

职责：

- 归一化姓名、学校、部门、主页和论文标识。
- 合并官网入口和论文入口产生的同一候选人。
- 生成置信度评分。
- 写入 `review_issues`。
- 导出 CSV。

进入复核的典型情况：

- 姓名常见且机构信息弱。
- 论文元数据缺少 email、ORCID 或可靠机构信息。
- 同一规范化姓名对应多个机构。
- 华人姓名评分落在复核区间。
- 导师、教育背景或年龄相关信息来自弱上下文推断。
- 页面只应由 LLM 处理，但当前阶段尚未实际接入 LLM。

## 7. 数据模型

### 7.1 `sources`

记录数据源及其配置。

- `id`
- `source_type`：`official_site`、`journal_list`、`paper_index`、`third_party`、`manual`
- `name`
- `base_url`
- `config_json`
- `enabled`
- `created_at`
- `updated_at`

### 7.2 `school_seeds`

记录官网入口使用的学校种子列表。第一阶段使用美国 Top 50 高校。

- `id`
- `rank`
- `school_name_en`
- `school_name_zh`
- `homepage_url`
- `difficulty_level`
- `crawl_status`
- `notes`
- `created_at`
- `updated_at`

### 7.3 `pages`

记录已下载网页及其解析状态。

- `id`
- `source_id`
- `url`
- `source_url`
- `school`
- `department`
- `page_type`：`school_home`、`department_home`、`faculty_list`、`profile`、`paper_page`、`third_party_profile`
- `status_code`
- `content_hash`
- `raw_html_path`
- `fetched_at`
- `fetch_error`
- `parser_status`
- `llm_status`

### 7.4 `journals`

记录期刊白名单，供论文入口匹配期刊名、ISSN/CN 和成果级别。

- `id`
- `source_file`
- `journal_system`
- `discipline`
- `journal_name`
- `normalized_journal_name`
- `issn_cn`
- `achievement_level`
- `talent_pool_use`
- `notes`
- `created_at`
- `updated_at`

### 7.5 `papers`

记录论文入口获得的论文元数据。

- `id`
- `title`
- `journal`
- `year`
- `doi`
- `url`
- `abstract`
- `authors_json`
- `first_author_name`
- `corresponding_author_names_json`
- `affiliations_json`
- `source`
- `paper_url`
- `source_api_url`
- `created_at`

### 7.6 `person_papers`

连接人员和论文记录。该表用于保存每篇论文链接，并支持按成果级别统计。

- `id`
- `person_id`
- `paper_id`
- `author_role`：`first_author`、`corresponding_author`、`first_and_corresponding`、`coauthor`
- `achievement_level`：从期刊白名单复制，例如 `A+(TOP)`、`A+`、`A`、`A1`、`A2`
- `paper_url`
- `doi`
- `year`
- `journal`
- `created_at`

### 7.7 `publication_stats`

记录每个人的论文统计结果。

- `person_id`
- `last_5_year_total`
- `first_author_total`
- `corresponding_author_total`
- `top_total`
- `a_plus_total`
- `a_total`
- `a1_total`
- `a2_total`
- `level_counts_json`
- `updated_at`

### 7.8 `people`

记录合并后的规范人员信息。

- `id`
- `name`
- `normalized_name`
- `email`
- `school`
- `department`
- `field`
- `research_direction`
- `title`
- `career_stage`
- `age`
- `birth_year`
- `photo_url`
- `photo_path`
- `education`
- `advisor`
- `personal_homepage`
- `research_interests`
- `biography`
- `publications_json`
- `publication_stats_json`
- `paper_links_json`
- `primary_source_type`：`official_site`、`publication`、`third_party`、`manual`
- `primary_source_url`
- `extraction_method`：`html_rule`、`local_llm`、`paper_metadata`、`third_party`、`manual`
- `is_likely_chinese_name`
- `chinese_name_score`
- `name_filter_reason`
- `confidence_score`
- `review_status`：`new`、`needs_review`、`verified`、`rejected`
- `created_at`
- `updated_at`

### 7.9 `review_issues`

记录后续需要人工复核的问题。该表导出到 `data/review/issues.csv`。

- `id`
- `person_id`
- `related_table`
- `related_id`
- `issue_type`：`missing_field`、`name_filter_uncertain`、`identity_conflict`、`low_confidence`、`llm_used`、`source_error`、`duplicate_candidate`、`paper_match_uncertain`
- `severity`：`low`、`medium`、`high`
- `message`
- `source_url`
- `status`：`open`、`resolved`、`ignored`
- `created_at`
- `resolved_at`

### 7.10 `candidate_links`

记录爬取前发现的候选链接。

- `id`
- `source_id`
- `url`
- `source_url`
- `anchor_text`
- `page_type`
- `confidence_score`
- `status`：`queued`、`fetched`、`skipped`、`failed`
- `created_at`

## 8. 模块结构

```text
src/faculty_spider_v3/
  cli.py
  config.py
  models.py
  storage.py
  official/
    discover.py
    fetch.py
    parse_html.py
    parse_llm.py
    pipeline.py
  publications/
    journal_list.py
    search_openalex.py
    search_crossref.py
    search_semantic_scholar.py
    search_dblp.py
    import_manual.py
    pipeline.py
  names/
    chinese_name.py
  enrichment/
    openalex.py
    semantic_scholar.py
    scholar_manual.py
    pipeline.py
  merge/
    normalize.py
    dedupe.py
    publication_stats.py
  review/
    issues.py
    export.py
    quality.py
```

## 9. 命令设计

官网入口：

```bash
faculty-spider-v3 official import-seeds data/seeds/us_top50_schools.csv
faculty-spider-v3 official discover --limit 50 --links-per-school 20
faculty-spider-v3 official fetch --limit 100
faculty-spider-v3 official crawl --max-pages 100 --batch-size 25
faculty-spider-v3 official extract-html --limit 100
faculty-spider-v3 official extract-llm --limit 50 --trigger-only
faculty-spider-v3 official export-people --csv data/exports/people.csv
faculty-spider-v3 official audit-pages --csv data/exports/page_audit.csv
```

论文入口：

```bash
faculty-spider-v3 publications import-journals "管理科学与工程相关期刊筛选清单.csv"
faculty-spider-v3 publications search --years 5 --source openalex,crossref
faculty-spider-v3 publications merge-results
faculty-spider-v3 publications search --years 5 --source semantic-scholar
faculty-spider-v3 publications import-manual data/manual_papers.csv
faculty-spider-v3 publications extract-authors
faculty-spider-v3 publications update-stats
```

信息补充：

```bash
faculty-spider-v3 enrichment run --missing email,homepage,research_interests --limit 50
```

合并、复核和导出：

```bash
faculty-spider-v3 merge candidates
faculty-spider-v3 review export --csv data/exports/people_review.csv
faculty-spider-v3 review issues --csv data/review/issues.csv
faculty-spider-v3 export --csv data/exports/people.csv --xlsx data/exports/people.xlsx
```

## 10. 关键规则

### 10.1 来源记录规则

当前阶段不做字段级来源追踪。每个人员记录只保存：

- `primary_source_type`
- `primary_source_url`
- `extraction_method`
- `confidence_score`

论文来源候选人的每篇论文链接和成果级别保存在 `person_papers`，聚合统计保存在 `publication_stats`。

### 10.2 LLM 触发规则

第一阶段不实际接入本地 LLM，只判断哪些页面未来需要 LLM 处理。

满足以下至少一个条件时，标记为 LLM 待处理：

- HTML 规则解析判断页面像个人主页，但在 `name`、`title`、`email`、`school`、`department`、`research_interests`、`biography`、`education`、`advisor`、`photo_url` 中提取到的有效字段少于 3 个。
- 页面文本包含 `Biography`、`Research`、`Education`、`Advisor`、`PhD`、`Postdoctoral`、`Publications` 等目标标签，但 DOM 规则无法稳定分离对应段落。
- 页面主要内容来自 JSON 或 script 块，语义化 HTML 很少。
- 一个页面包含多个人，规则解析无法可靠拆分个人卡片。
- 页面中英文混杂，规则解析结果互相冲突。
- HTML 解析器置信度低于配置阈值，例如 `0.65`。

以下情况不标记 LLM：

- 规则解析已经获得高置信度结果。
- 页面只是通用 faculty 列表，没有个人详细信息。
- 页面过长，应先拆分为个人卡片或局部文本片段。
- 来源是已经结构化的论文元数据 API 响应。

### 10.3 华人姓名筛选规则

第一版使用评分过滤，而不是简单的二元判断。

评分信号：

- 姓名中包含中文字符，作为强信号。
- 罗马字母姓名使用中文姓氏和拼音名模式打分。
- 姓氏词典包含常见中文姓氏拼音，例如 `Wang`、`Li`、`Zhang`、`Liu`、`Chen`、`Yang`、`Huang`、`Zhao`、`Wu`、`Zhou`、`Xu`、`Sun`、`Ma`、`Zhu`、`Hu`、`Guo`、`He`、`Gao`、`Lin`、`Luo`、`Zheng`、`Liang`、`Xie`、`Song`、`Tang`、`Deng`、`Han`、`Feng`、`Cao`、`Peng`、`Cai`、`Yuan`、`Pan`、`Du`、`Jiang`、`Xiao`、`Cheng`、`Shen`、`Yu`、`Lu`、`Wei`、`Ye`、`Fang`、`Ren`、`Qian`。
- 支持复姓拼音，例如 `Ouyang`、`Sima`、`Zhuge`、`Shangguan`、`Situ`、`Huangfu` 等。
- 名字部分支持一到两个拼音音节、连字符形式、首字母加拼音、连写拼音，例如 `Xiaoming`、`Wei Zhang`、`Yifan Chen`。
- 上下文信号包括中国高校经历、中文个人页、中文简历、教育背景等。
- 负向信号包括明显非中文姓氏、机构名、不是人的页面标题等。

实现要求：

- 新增 `names/chinese_name.py`。
- 核心函数：`score_chinese_name(name: str, context: str = "") -> NameScore`。
- 保存 `is_likely_chinese_name`、`chinese_name_score` 和 `name_filter_reason`。
- 默认保留阈值：`0.70`。
- 默认复核区间：`0.45` 到 `0.70`。
- 低于 `0.45` 的记录默认跳过，除非人工强制保留。

已知限制：

- 罗马字母姓名过滤一定会有误判和漏判。它的作用是降低工作量，不是最终身份判断。

### 10.4 质量门槛

候选人可以自动进入结果库的条件是：整体置信度足够高，且没有高严重度的未解决问题。全局上不设置必填字段。

以下情况必须进入复核：

- 姓名常见且机构信息弱。
- 论文元数据没有 email、ORCID 或可靠机构信息。
- 同一个规范化姓名对应多个机构。
- 华人姓名评分落在复核区间。
- 导师、教育背景或年龄相关信息来自弱上下文推断。
- 页面被标记为需要 LLM，但当前阶段尚未实际接入 LLM。

## 11. 可行性与风险

官网采集可行，但不同学校页面差异很大。v2 已验证静态 HTML 抓取和基础解析路线可行；v3 需要补上队列管理、原始 HTML 保存、LLM 待处理标记和 CSV 复核闭环。

论文入口可行，但应依赖元数据 API 和人工导入，而不是依赖 Google Scholar 自动抓取。英文期刊相对容易，中文期刊难度更高，主要问题是元数据结构、通讯作者和邮箱信息不稳定。

第三方补全可行，但应作为受控兜底流程。它适合补全主页、机构、研究方向和论文身份，不适合从弱来源自动推断敏感或低可信字段。

完整的全球人才数据库是长期目标，不能靠一个大脚本完成。可维护的实现单元应是带持久化存储、来源记录、重试机制、去重逻辑和复核导出的管线系统。

## 12. 执行里程碑

### M1：项目骨架与数据库

- 创建 v3 包结构。
- 创建数据库 schema。
- 实现 `sources`、`school_seeds`、`journals`、`pages`、`papers`、`person_papers`、`publication_stats`、`people`、`candidate_links` 和 `review_issues` 表。
- 为数据库初始化写测试。

### M2：基础输入导入

- 实现现有 CSV 期刊白名单导入。
- 增加美国 Top 50 高校种子文件。
- 实现学校种子导入命令。

### M3：姓名筛选与复核问题

- 实现华人姓名评分。
- 将评分应用到官网入口和论文入口候选人。
- 实现 `review_issues` 写入和 CSV 导出。

### M4：官网入口 MVP

- 迁移 v2 的静态抓取能力。
- 迁移并扩展 HTML 规则解析。
- 增加按队列递归抓取的 `official crawl`。
- 增加 faculty 列表页个人卡片抽取。
- 增加照片、教育背景、导师字段提取。
- 增加照片下载。
- 增加 LLM 待处理标记，不实际调用模型。
- 增加官网人员 CSV 导出和页面审计 CSV 导出。

### M5：论文入口 MVP

- 实现 OpenAlex 与 Crossref 并行搜索。
- 实现论文结果去重合并。
- 抽取第一作者和通讯作者。
- 保存每篇论文链接。
- 统计按成果级别划分的论文数量。

### M6：合并、导出与质量评分

- 合并官网入口和论文入口候选人。
- 实现基础去重规则。
- 实现置信度评分。
- 导出 `people.csv`、`people_review.csv` 和 `issues.csv`。

## 13. 后续暂缓问题

1. 本地 LLM 具体运行方式：Ollama、LM Studio、llama.cpp server，或其他 OpenAI-compatible 本地服务。
2. 是否在 CSV 复核之外增加更友好的本地复核界面。
