# Faculty Spider v3

v3 的目标是建设一个可长期维护、可持续更新、多来源融合的管理科学与工程相关人才数据库。

项目拆分为相互独立的管线：

1. 官网入口管线：从学校或学院官网发现 faculty 页面，下载 HTML，并提取个人信息。
2. 论文入口管线：基于期刊白名单查找近年论文，识别第一作者和通讯作者。
3. 信息补充管线：在候选人已有基本识别信息后，从第三方来源补全缺失字段。
4. 合并与复核管线：对候选人去重、保留主来源、计算置信度，并导出可复核记录。

第一阶段只做信息采集，范围限定在管理科学与工程相关方向。目标对象包括博士、博士后、助理教授、副教授、教授，以及相近的研究岗或教学科研岗。

第一阶段的已确认边界：

- 初始学校种子列表使用美国 Top 50 高校。
- 本地 LLM 暂时只保留入口和触发规则，具体运行方式后续开发。
- 论文元数据先同时跑 OpenAlex 和 Crossref，再去重合并；Semantic Scholar、DBLP 和人工导入作为补充。
- 复核结果只导出 CSV。
- 年龄相关字段同时保留 `age` 和 `career_stage`。

## 当前输入

- `管理科学与工程相关期刊筛选清单.csv`：论文入口管线使用的期刊白名单。

## 目标人员字段

- `name`
- `age`
- `email`
- `school`
- `department`
- `field`
- `research_direction`
- `title`
- `source_url`
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

## 设计原则

每个人员记录只保留一个主来源 URL 和一个主来源类型。论文来源候选人额外保留每篇论文链接和按成果级别划分的数量统计。模糊、冲突或可疑的数据不强行写入最终结果，而是写入问题记录文件，供后续复核。

第一阶段详细计划见 `docs/stage1_information_collection_plan.md`。

## 当前交接状态

截至 M5，官网入口和论文入口的小批量验证已完成。当前导出规模：

- `people.csv`：126 人
- `papers.csv`：221 篇论文
- `publication_people_candidates.csv`：82 个论文入口聚合候选
- `publication_quality_report.csv`：30 行期刊质量报告

M6 将在另一个对话中开始，目标是实现论文批量采集、断点续跑和质量控制。

交接文件：

- `docs/m5_publication_entry_summary.md`
- `docs/m6_handoff.md`
- `data/seeds/publication_journal_groups.csv`
