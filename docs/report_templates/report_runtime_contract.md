# Report Runtime Contract

当前目标：先让系统知道“报告是什么”，再改 writer / QA / retrieval。

## Layer Responsibilities

| 层 | 负责 | 不负责 |
|---|---|---|
| Intake | 保留用户原始问题；抽取市场范围、目标品类、地域、角色；把“不知道/无/不确定”归一为 `null` | 替用户决定细分赛道 |
| Discovery | 找玩家、细分、价值链节点；标注证据所属品类 | 把公司级泛证据升级成品类证据 |
| Research | 围绕 `company + target_category + dimension` 采证 | 用公司官网首页、手机价格、通用口碑填 AI 硬件字段 |
| Knowledge extraction | 抽取结构化 facts，并保留 category relevance | 只因为字段存在就标 `complete` |
| Writer | 按市场报告模板组织正文；把 workbench 数据转成用户可读章节 | 直接输出 role map、raw matrix、unknown cells |
| QA | 检查品类相关性、报告结构、证据边界、是否回答用户输入 | 只检查 section 数量和 citation 格式 |

## Required State

```text
ReportContext:
  user_query: str
  market_scope: str | null
  target_category: str
  category_aliases: list[str]
  excluded_categories: list[str]
  analysis_archetype: "landscape" | "comparison"
  report_depth: "quick" | "deep"
```

## Category Relevance

```text
Evidence is category-relevant iff:
  mentions(company_or_product)
  AND mentions(target_category_or_alias)
  AND supports(requested_dimension)
```

Examples:

| Evidence | User query | Valid? |
|---|---|---|
| vivo 手机价格 | AI 硬件全景 | no |
| 华为 OceanStor 存储 | AI 硬件全景 | no，除非用户明确包含企业 AI 基础设施 |
| 理想 Livis AI 眼镜发布 | AI 硬件全景 | yes，但只能支撑 AI 眼镜细分 |
| 阿里夸克 AI 眼镜功能 | AI 硬件全景 | yes，但只能支撑 AI 眼镜细分 |

## Report Sections

Runtime section ids should map to user-facing sections:

| User-facing section | Runtime section id |
|---|---|
| 核心判断 | `executive_takeaways` |
| 市场定义与分析边界 | `market_definition` |
| 市场规模、增长与驱动因素 | `market_size_growth` |
| 细分赛道与应用场景 | `market_segmentation` |
| 竞争格局 | `competitive_landscape` |
| 关键玩家分析 | `key_players` |
| 产业链与生态位 | `value_chain` |
| 机会窗口与主要风险 | `opportunities_risks` |
| 战略建议 | `strategic_recommendations` |
| 方法论与证据边界 | `methodology_limits` |

Deprecated user-facing sections:

| Old section | Status |
|---|---|
| `market_landscape_map` | workbench only |
| `competitor_profiles` | folded into `key_players` |
| `comparison_matrix` | appendix / evidence matrix only |
| `positioning_map` | only if scoring method exists |
| `representative_benchmarks` | removed |

## QA Blocking Rules

| Rule | Reject to |
|---|---|
| Report narrows broad user query without scope disclosure | writer |
| Any `complete` coverage uses non-target-category evidence | researcher |
| Main section has more than 30% unknown cells | researcher |
| Report lacks market definition | writer |
| Report lacks methodology and evidence boundary | writer |
| Competitive landscape contains company groups without evidence | researcher |
| 2x2 appears without axis definitions and scoring method | writer |

## Runbook

When a real E2E report looks unusable:

1. Read `RunIntakeDraft`: compare `user_query`, `target_category`, `self_product`.
2. Inspect evidence by `competitor_id`, `dimension`, `category_relevance`.
3. Inspect knowledge coverage: reject `complete` values backed by wrong category.
4. Inspect `report_section_ids`: old workbench ids in top-level output are a bug.
5. Inspect QA: semantic warning about category mismatch must be blocking.
