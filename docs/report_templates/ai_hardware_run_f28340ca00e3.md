# AI Hardware Run `run_f28340ca00e3`

## Input

| Field | Value |
|---|---|
| `user_query` | `AI硬件全景与趋势` |
| `domain_hint` | `AI硬件` |
| `market_scope` | `中国市场 (China)` |
| `analysis_archetype` | `landscape` |
| `report_depth` | `quick` |
| `self_product` | `不知道` |

User did not ask for AI glasses.

## Observed Output

Top-level sections:

```text
market_landscape_map
competitor_profiles
comparison_matrix
positioning_map
trend_summary
opportunity_map
strategic_recommendations
```

These are analyst workbench sections, not a mature market report outline.

## Runtime Metrics

| Metric | Value |
|---|---|
| Evidence count | 99 |
| Competitors | 小米, vivo, 华为, 理想汽车, 字节跳动, Apple, 阿里巴巴 |
| Knowledge schema coverage | 0.339 |
| Dimension coverage | 0.267 |
| QA rejected steps | 0 |
| QA outcome | approved |

Evidence distribution:

| Company | Evidence count |
|---|---:|
| vivo | 32 |
| 阿里巴巴 | 23 |
| 华为 | 16 |
| 字节跳动 | 12 |
| 小米 | 9 |
| 理想汽车 | 6 |
| Apple | 1 |

## Fault Boundary

| Boundary | Evidence | Failure |
|---|---|---|
| Intake | `self_product="不知道"` | Unknown value not normalized to `null` |
| Retrieval / extraction | vivo phone pricing became `pricing=complete` | Evidence did not match target category |
| Knowledge | Huawei enterprise storage became feature signal | Company-level evidence entered AI hardware facts |
| Writer | Workbench sections rendered as report sections | Report structure is internal, not user-facing |
| QA | Semantic audit warned about vivo pricing mismatch but approved | Category mismatch is warning, not blocking |

## AI Glasses Drift

No production hardcode for `AI眼镜` was found in runtime code. The term appears in tests/golden cases and prior diagnostics.

The real drift source is different:

1. User asked broad `AI硬件`.
2. Search results and analyst narrative over-indexed on AI glasses because public market reports are rich in that subcategory.
3. Writer did not disclose that the evidence was mostly AI glasses.
4. QA did not reject the unannounced scope narrowing.

Correct behavior:

```text
本轮公开资料对 AI 眼镜覆盖最充分；其他 AI 硬件细分证据不足。
以下趋势判断以 AI 眼镜为主要样本，不代表整个 AI 硬件市场。
```

If the product should not narrow, supervisor must trigger follow-up research for other AI hardware segments.

## Why The Report Is Unusable

| Symptom | Root cause |
|---|---|
| `竞品分层地图` appears before market definition | Old workbench-first report architecture |
| vivo appears as pricing-complete | Pricing evidence is for phones, not AI hardware |
| Huawei storage appears as capability | Category relevance gate is missing |
| Matrices contain `未核验` cells | Report renders sparse internal tables |
| 2x2 ranks vivo as leader | Scoring uses coverage existence, not market relevance |
| QA approved | QA checks structure/citation, not commercial usability |

## Required Fix

| Area | Change |
|---|---|
| Intake | Normalize `不知道/不清楚/无/none/null` to `None` for `self_product` and optional fields |
| Discovery | Extract `target_category` and `category_aliases`; preserve broad category unless user narrows |
| Research | Query with `{company} + {target_category_alias} + {dimension}` |
| Knowledge | Store `category_relevance`; `complete` requires category-relevant evidence |
| Writer | Use `market_landscape_template.md`; move workbench blocks to appendix |
| QA | Make category mismatch and unannounced narrowing blocking |

## Regression Tests

Minimum cases:

| Case | Expected |
|---|---|
| `AI硬件全景与趋势` | No silent narrowing to AI glasses |
| `AI眼镜全景与趋势` | AI glasses-specific report allowed |
| `vivo 手机价格` under AI hardware | Does not satisfy AI hardware pricing |
| `华为 OceanStor` under AI hardware | Does not satisfy AI hardware feature unless scope includes AI infrastructure |
| `self_product=不知道` | Stored as `null` |
