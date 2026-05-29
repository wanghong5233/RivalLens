# Implementation 13: Skill Library

> 状态：ACTIVE  
> 更新时间：2026-05-29

## 1. 目标

Skill Library 用于承载可复用领域知识，并在运行时按需加载，避免：

- 预置目录耦合主流程；
- 把全部领域知识塞入系统提示词；
- 每次扩展都改核心 Agent 代码。

## 2. 目录规范

```text
backend/skills/
  qa_rule/
    <skill_id>/
      SKILL.md
      <supporting files...>
  prompt_template/
    <skill_id>/SKILL.md
  source_routing/
    <skill_id>/SKILL.md
```

## 3. `SKILL.md` 结构

每个技能文件由两部分组成：

1. YAML frontmatter（元数据）
2. markdown body（规则/模板/路由正文）

最小 frontmatter：

```yaml
---
name: evidence-must-cite-source
description: Ensure report claims cite evidence ids.
version: 1.0.0
tags: [qa, citation]
applies_to: qa_rule
---
```

## 4. SkillStore 行为

实现路径：`backend/app/service/skill_store/`

- `scan()`：扫描全部 `SKILL.md`，建立 metadata cache
- `load(skill_id)`：懒加载正文
- `list_by_tag(tag)`
- `list_by_applies_to(applies_to)`
- `read_supporting_file(skill_id, filename)`（含路径越界拦截）

## 5. Agent 工具接入

Researcher 可调用：

- `load_skill(skill_id)`：获取技能摘要与可读文件列表
- `read_skill_file(skill_id, filename)`：读取支持文件

这构成 progressive disclosure：先读摘要，再按需深入。

## 6. QA 与 Curator 联动

- QA 运行时从 SkillStore 加载 `applies_to=qa_rule` 的规则；
- Curator 生成候选写入 `skill_candidates`；
- 审核通过后写回 `backend/skills/**/SKILL.md`；
- 下一次 run 自动可见（依赖 SkillStore scan）。

## 7. 迁移说明

重构阶段提供一次性脚本：

- `backend/app/scripts/migrate_pack_to_skills.py`

用途：

- 历史规则迁移为 `SKILL.md`
- demo competitor 数据迁移为 `demo_fixtures/competitors_seed.yaml`

## 8. 验收检查

- `pytest backend/app/tests/test_skill_store.py`
- `pytest backend/app/tests/test_skill_tools.py`
- `python backend/app/scripts/run_golden.py`（包含 load_skill progressive disclosure case）
