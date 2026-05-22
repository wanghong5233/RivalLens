# Architecture Doc Examples · 反例 → 正例

> 示例使用虚构项目 `ChartFlow`（数据可视化工作台，含主 API、Pipeline 编排、Editor 协作）。

## 反例：结论先行 + 辩证过程 + 工件清单

```markdown
### B.1 结论先行
当前阶段，ChartFlow 放弃 Cloudflare Tunnel……

### B.2 决策背景
之前的本地 Docker + Tunnel 方案频繁抖动。落地阶段连续遇到三类问题：
1. 网络问题：QUIC 不稳定……
2. 运维问题：Windows 任务计划偶发……

### B.4 我们的辩证过程
1. 第一反应（错）：Tunnel 不稳定 → "再写一个守护脚本"
   - 反驳：守护脚本不等于云服务器架构……

### B.7 已删除/不再维护的工件
- backend/scripts/tunnel_watchdog.ps1
- CF_TUNNEL_TOKEN
- Cloudflare Tunnel 配置截图
```

问题：

- 结论先行的"当前阶段……"是 TL;DR 元结构，纯污染
- 决策背景 / 辩证过程是过去式叙事，不是架构事实
- 工件清单是 git log 的职责

## 正例：现状陈述 + 维度表

```markdown
## B.1 架构

ChartFlow 采用主 API 统一入口，Pipeline 与 Editor 分别承担数据编排与协作编辑。

[mermaid 图]

## B.2 第一性原理

| 维度 | 分析 | 结论 |
|---|---|---|
| 数据规模 | 数据集索引、会话记忆、报告产物规模不同 | 分层存储与分层检索 |
| 能力归属 | LLM 负责生成，代码负责证据、契约和失败边界 | 不把错误吞成空结果 |
| 写入成本 | Demo、调试、云部署目标不同 | 本地调试与公网部署分开描述 |
| 可逆性 | API schema 稳定 | 后续可替换模型、部署和存储 |
```

（工件清单归 git log / CHANGELOG，不进架构文档。）

## 章节形态示例

### 现状陈述

> ChartFlow 采用主 API + Pipeline 编排 + Editor 协作的多服务架构，围绕数据加工、可视化和报告生成提供能力。

一句话 + 一图（mermaid 或分层职责表）。

### 分层职责表

| 层 | 负责 | 不负责 |
|---|---|---|
| Main API | 鉴权、Session、数据集、编排入口、网关错误边界 | 前端布局 |
| Pipeline | 任务编排、工具调用、证据聚合、报告生成 | 主站用户体系 |
| Editor | 工作区文件、协作编辑、编译/检查、人机确认 | 数据集索引策略 |
| Infra Services | 关系库、缓存、消息队列、向量索引、解析服务 | 业务策略 |

三列 `层 / 负责 / 不负责`，无解释段落。

### 第一性原理维度选项

- **数据规模**（量化：行数、QPS、体积）
- **能力归属**（哪个角色负责这件事）
- **写入/读取成本**（延迟、token、依赖体积）
- **故障域**（失败面、传染性）
- **可逆性**（未来换方案的迁移成本）

### 接口契约

```text
POST /api/sessions/{session_id}/ask -> AskResponse | SSE events
POST /api/pipeline/runs -> PipelineRun
POST /api/editor/workspaces/{workspace_id}/agent/run -> AgentRun
```

**不变式**：

- 返回结构必须符合 schema
- Agent 类回答必须能回到证据 chunk、citation、tool trace 或 web evidence
- 无法解析模型输出、外部 API 鉴权失败、索引失败时失败，不返回伪成功

### 可逆性 / 重评触发条件

"当前选 A，未来可能换 B"类决策给量化门槛：

1. 单次上下文超过主模型稳定窗口
2. 单次工具链稳定超时或成本超过目标预算
3. 证据定位失败 case ≥ 5 起
4. 公网演示或云服务器部署的故障域发生变化

**触发判断以运行时指标为准，不在无数据时提前决策。**
