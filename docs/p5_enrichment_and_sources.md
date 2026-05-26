# P5 信息补全与宽口径期刊扩展

## 1. 背景

P5 目标是为 publication-only 人员补全缺失字段，并为宽口径高影响力期刊（Nature、Science、PNAS、PAMI、JMLR 等）增加论文级别学科过滤。

## 2. 宽口径期刊学科过滤

### 2.1 过滤策略

宽口径期刊（`broad_high_impact` 组）由于期刊主题覆盖广，不能依赖期刊名称本身作为管理科学相关性依据。必须通过论文标题、摘要和关键词进行学科过滤。

### 2.2 过滤规则

宽口径期刊论文在入库前必须通过 `score_paper_discipline_relevance()` 评估：

- **接受（accepted）**：score >= 0.6，直接入库
- **需复核（needs_review）**：0.35 <= score < 0.6，标记需人工复核后入库
- **拒绝（rejected）**：score < 0.35，不入库，写入 `review_issues`

### 2.3 过滤关键词

正关键词（增加相关性分数）：

- 管理科学：`management science`, `operations research`, `operations management`, `decision science`, `optimization`, `stochastic`, `queueing`, `supply chain`, `logistics` 等
- 信息系统：`information systems`, `digital platform`, `e-commerce`, `business analytics`, `data analytics`, `machine learning`, `artificial intelligence` 等
- 商业管理：`business school`, `management`, `strategy`, `marketing`, `organization`, `innovation`, `entrepreneurship` 等
- 量化金融经济：`finance`, `fintech`, `risk management`, `economics`, `econometrics` 等
- 工业系统工程：`industrial engineering`, `systems engineering`, `statistics`, `data science` 等

负关键词（降低相关性分数）：

- `medicine`, `medical school`, `biology`, `chemistry`, `physics`, `literature`, `history`, `music`, `law school`, `clinical psychology`, `linguistics` 等

### 2.4 过滤使用场景

```bash
# 宽口径期刊单独批量运行（不混入 default_batch）
PYTHONPATH=src python3 -m faculty_spider_v3.cli publications batch-run \
  --journal-group broad_high_impact \
  --works-per-journal 50 \
  --from-year 2022 \
  --resume
```

### 2.5 过滤样例

| 论文标题 | 摘要关键词 | 评分 | 结果 |
|----------|-----------|------|------|
| "Operations Research for Supply Chain Management" | stochastic optimization, supply chain | 0.65 | accepted |
| "Digital Platforms and Business Analytics" | AI, data analytics, e-commerce | 0.45 | needs_review |
| "Machine Learning Applications in Urban Planning" | machine learning | 0.24 | rejected |
| "Gene Expression in Breast Cancer Metastasis" | biology, medicine | 0.0 | rejected |

## 3. Publication-only 人员字段补全

### 3.1 补全字段

- `personal_homepage`：个人官网主页
- `title`：职位/职称（如 Assistant Professor）
- `department`：所属院系
- `email`：电子邮箱

### 3.2 补全数据来源优先级

数据来源按证据强度分为三级：

**强证据（Strong Evidence）**：

- 官网入口（`official_site`）：来自大学/学院官方网站个人信息页
  - 最高优先级，所有字段均以官网数据为准
  - 来源字段：`primary_source_type = "official_site"`

**中证据（Medium Evidence）**：

- Semantic Scholar：学术社交网络，含有作者画像和元数据
  - 用于补全 homepage、title、department、email
  - 使用条件：官方来源无数据或数据不完整时
  - 来源标注：`homepage_source = "semantic_scholar"`

- DBLP：计算机领域文献数据库
  - 用于补全计算机相关领域人员的 affiliation
  - 使用条件：仅作为补充源，不覆盖已有强证据
  - 来源标注：`affiliation_source = "dblp"`

**弱证据（Weak Evidence）**：

- Crossref / OpenAlex 元数据：仅含 affiliation（机构信息）
  - 用于补全 `school` 字段
  - 不用于推断 homepage、title、department、email
  - 来源标注：`school_source = "crossref"` 或 `"openalex"`

### 3.3 补全规则

1. **强证据覆盖弱证据**：如果 `official_site` 来源已有某字段值，不接受弱证据覆盖
2. **同优先级合并**：同一来源有多条冲突信息时，保留置信度最高的
3. **补全需可追踪**：每次补全操作必须记录来源，用于审计和质量复核
4. **Publication-only 候选人必须人工复核**：所有 `primary_source_type = "publication"` 的人员在补全后必须经过人工复核才能进入最终人才库

### 3.4 实现方式

字段补全通过 EnrichmentPipeline 实现：

```python
# 伪代码示例
def enrich_publication_only_person(store, person_id):
    person = store.get_person(person_id)

    # 1. 从 Semantic Scholar 补全
    if not person.title or not person.department:
        ss_data = semantic_scholar_lookup(person.name, person.school)
        if ss_data.confidence > 0.7:
            apply_if_stronger(person, 'title', ss_data.title, source='semantic_scholar')
            apply_if_stronger(person, 'department', ss_data.department, source='semantic_scholar')

    # 2. 从 DBLP 补全 affiliation
    if not person.school:
        dblp_data = dblp_lookup(person.name)
        if dblp_data and dblp_data.affiliation:
            apply_if_stronger(person, 'school', dblp_data.affiliation, source='dblp')

    # 3. 从 Crossref/OpenAlex 补全 school（弱证据）
    if not person.school:
        crossref_data = crossref_lookup(person.name, person.paper_links)
        if crossref_data and crossref_data.affiliation:
            apply_if_stronger(person, 'school', crossref_data.affiliation, source='crossref')
```

## 4. 补充源使用边界

### 4.1 Semantic Scholar

- **边界**：仅用于补全 `title`、`department`、`homepage`、`email`
- **不用于**：作为主证据来源，不用于覆盖已复核的官方数据
- **置信度要求**：置信度 < 0.7 的数据不自动写入，需人工复核

### 4.2 DBLP

- **边界**：仅用于计算机相关领域人员的 affiliation 补全
- **不用于**：作为主证据来源，不覆盖官方 affiliation
- **优先级**：低于 Semantic Scholar 的 homepage/title 补全

### 4.3 Crossref / OpenAlex

- **边界**：仅用于补全 `school`（机构）字段
- **不用于**：推断 `email`、`title`、`homepage`、`department`
- **证据强度**：弱证据，不可覆盖任何中证据或强证据

### 4.4 补充源与主证据的关系

```
official_site (强证据)
    ↓ 最高优先级，不被覆盖
semantic_scholar (中证据)
    ↓ homepage, title, department, email
dblp (中证据)
    ↓ affiliation（计算机领域）
crossref/openalex (弱证据)
    ↓ school（机构）
```

## 5. 数据库字段变更

### 5.1 新增字段

为支持证据来源追踪，在 `people` 表增加以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `homepage_source` | text | 个人主页来源（semantic_scholar, dblp, crossref, openalex, official_site） |
| `title_source` | text | 职位来源 |
| `department_source` | text | 院系来源 |
| `email_source` | text | 邮箱来源 |
| `school_source` | text | 学校来源 |
| `enrichment_confidence` | real | 补全置信度（0-1） |

### 5.2 迁移脚本

```sql
-- 添加来源追踪字段
ALTER TABLE people ADD COLUMN homepage_source TEXT DEFAULT '';
ALTER TABLE people ADD COLUMN title_source TEXT DEFAULT '';
ALTER TABLE people ADD COLUMN department_source TEXT DEFAULT '';
ALTER TABLE people ADD COLUMN email_source TEXT DEFAULT '';
ALTER TABLE people ADD COLUMN school_source TEXT DEFAULT '';
ALTER TABLE people ADD COLUMN enrichment_confidence REAL DEFAULT 0.0;
```

## 6. 验收标准

1. **宽口径期刊过滤**：
   - [ ] `broad_high_impact` 组期刊使用独立批次运行，不混入 `default_batch`
   - [ ] 过滤规则有可测试用例（见 `tests/test_discipline_filter.py`）
   - [ ] 被过滤论文写入 `review_issues` 并标记 `issue_type = "broad_journal_discipline_filter"`

2. **字段补全**：
   - [ ] 补全字段有来源记录
   - [ ] 弱证据不会覆盖强证据
   - [ ] Publication-only 候选人补全后 review_status = "needs_review"

3. **补充源边界**：
   - [ ] Semantic Scholar / DBLP 仅作补充源
   - [ ] 不改变已复核主证据
   - [ ] 边界在代码注释和文档中明确说明

4. **测试**：
   - [ ] `pytest -q` 在干净环境通过
   - [ ] 新增测试覆盖过滤规则和来源追踪逻辑
