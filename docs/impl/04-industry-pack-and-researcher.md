# [DEPRECATED] Implementation 04: Industry Pack + Researcher

> 状态：**DEPRECATED**（2026-05-29）  
> 原因：核心架构已迁移到 Agent-Native 4 轴模型（Entity / Source / Skill / Hint）。

## 迁移说明

本实现文档描述的是历史版本中的静态打包方案，已不再作为现行实现依据。  
当前实现请以以下文档为准：

- `docs/2-architecture-decision.md`
- `docs/2.5-agent-architecture.md`
- `docs/2.6-collector-channels.md`
- `docs/impl/13-skill-library.md`

## 历史留档边界

本文件仅用于：

- 回溯重构前的设计假设；
- 对照迁移脚本与数据库变更历史；
- 复盘“为何需要改为按需加载技能”。

除上述用途外，不应再引用本文件指导新开发。
