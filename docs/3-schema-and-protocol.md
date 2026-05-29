# RivalLens Schema 与协议

> 更新时间：2026-05-29

本文是后端 API 与核心数据结构的对齐文档，强调“当前实现真实字段”。

## 1. Run API

### 1.1 `POST /api/runs`

请求体：

```json
{
  "user_query": "compare Notion and Obsidian",
  "competitors": ["Notion", "Obsidian"],
  "target_roles": ["pm"],
  "domain_hint": "knowledge management",
  "reference_urls": ["https://www.notion.so/product", "https://obsidian.md"]
}
```

字段语义：

- `competitors`：必填，去重后至少 1 个
- `target_roles`：必填，业务受众
- `domain_hint`：可选，run 级场景提示
- `reference_urls`：可选，Researcher 优先参考 URL

响应体：

```json
{
  "run_id": "run_xxx",
  "status": "completed",
  "message": "..."
}
```

### 1.2 `GET /api/runs/{run_id}`

返回关键字段：

- `run_id`
- `user_query`
- `domain_hint`
- `reference_urls`
- `status`
- `target_roles`
- `competitors`
- `started_at` / `finished_at` / `created_at`

### 1.3 `GET /api/runs`

列表项关键字段：

- `run_id`
- `user_query`
- `domain_hint`
- `status`
- `step_count`
- `evidence_count`
- `has_report`

## 2. Trace 相关协议

### 2.1 Step

- `step_id`
- `run_id`
- `agent_name`
- `status`
- `retry_count`
- `payload`（agent-specific）
- `rejection_reason`
- `started_at` / `finished_at` / `created_at`

### 2.2 SupervisorDecision

- `chosen_tool`
- `tool_args`
- `reasoning_summary`
- `triggered_by`
- `outcome`

### 2.3 Evidence

- `id`
- `run_id`
- `source_type`
- `source_url` / `source_title`
- `quote` / `sanitized_text`
- `span`（含 dimension/competitor_id）
- `desensitized`

## 3. Skill Candidate 协议

### 3.1 `GET /api/skill-candidates`

支持过滤：

- `status`
- `applies_to`
- `tag`
- `limit` / `offset`

### 3.2 SkillCandidateResponse

```json
{
  "id": "skill_xxx",
  "candidate_type": "qa_rule",
  "applies_to": "qa_rule",
  "tags": ["pricing", "ai_coding"],
  "payload": {},
  "rationale": "...",
  "supporting_run_ids": ["run_xxx"],
  "confidence": "medium",
  "status": "staging",
  "reviewed_by": null,
  "reviewed_at": null,
  "error": null,
  "created_at": "..."
}
```

### 3.3 审核接口

- `POST /api/skill-candidates/{candidate_id}/approve`
- `POST /api/skill-candidates/{candidate_id}/reject`

approve 响应包含：

- `status=approved`
- `promoted_artifacts[]`（`path` / `action` / `entry_id`）

## 4. Skill 文件协议

目录规范：

`backend/skills/<applies_to>/<skill_id>/SKILL.md`

frontmatter 字段：

- `name`
- `description`
- `version`
- `tags`
- `applies_to`
- `dependencies`（可选）

## 5. QA 协议关键字段

QA step payload 重点字段：

- `qa_outcome`
- `qa_reject_to` / `reject_to`
- `failed_rule_ids`
- `promoted_qa_rule_ids`
- `promoted_qa_blocked_rule_ids`
- `qa_semantic_mode`

## 6. Demo Fixtures 协议

`GET /api/demo-fixtures/competitors` 返回数组：

```json
[
  {
    "id": "comp_cursor",
    "display_name": "Cursor",
    "aliases": ["cursor ai"],
    "official_url": "https://cursor.com",
    "category": "ai_coding_assistant"
  }
]
```

## 7. 兼容性说明

- 旧版静态打包字段已完全移除，不再接受/返回。
- 相关扩展能力由 `domain_hint`、`reference_urls`、`applies_to`、`tags` 替代。
