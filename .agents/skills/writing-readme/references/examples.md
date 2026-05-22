# README Examples · 反例 → 正例

> 示例使用虚构项目 `ChartFlow`（数据可视化工作台）。复制时换成你自己的项目名与服务名。

## 反例 1：口水话 + 内部业务字段

```markdown
### 检索

为了提供更准确的语义检索能力，ChartFlow 采用了 BM25 + 向量混合检索的方案。
具体来说，BM25 通过 PostgreSQL 内置的 `ts_rank_cd` 函数实现全文检索，向量
检索基于 pgvector 的 cosine 距离。值得一提的是，生产部署默认不启用本地
Reranker，而是走云端重排。
```

问题：`ts_rank_cd` / `cosine` 是实现细节，"为了 / 具体来说 / 值得一提的是"是口水话，"生产默认不启用"是内部决策细节。

## 正例 1

```markdown
### 检索

BM25 + 向量混合检索（PostgreSQL 全文索引 + 向量索引），云端重排。
```

## 反例 2：服务表 + 自我夸赞 + 已下线服务

```markdown
ChartFlow 包含强大的 6 个微服务：
- API Gateway：业界领先的高性能网关
- Editor：优雅的图表协作平台
- Pipeline：创新的数据编排引擎
- Reranker：精准的重排服务（已下线）
- DataParser：先进的数据解析（已下线）
```

问题：形容词堆砌；已下线服务出现在公开介绍里。

## 正例 2

```markdown
| 服务 | 端口 | 职责 |
|---|---|---|
| `chartflow_api` | 8000 | 鉴权、会话、编排 |
| `chartflow_editor` | 8003 | 工作区、协作 |
| `chartflow_pipeline` | 8002 | 数据加工、报告生成 |
```

（已下线服务归 git log，不进 README。）

## 反例 3：失效链接 + 内部目录

```markdown
> Demo: https://demo-old.example.com （旧子域，404）
>
> 云端部署见 [notes/DEPLOYMENT.md](./notes/DEPLOYMENT.md)
```

问题：旧 demo 子域已废弃；`notes/` 是 git ignored 内部目录，链接对公开访客 404。

## 正例 3

```markdown
> Demo: https://chartflow.example.com/demo
>
> 云端部署见 [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)
```

## 子 README 误写 vs 正确归宿

| 子 README 误写 | 正确归宿 |
|---|---|
| 复述项目愿景 / 整体架构 / 功能特性 | 删，引根 README |
| 描述与根 README 重叠的 Tech Stack | 删 |
| 子目录独有的运维 SOP（tunnel / DB migration / watchdog） | **保留** |
| 子目录独有的开发命令（`npm run dev` / `alembic upgrade`） | 保留 |
| 子目录独有的环境变量 / 目录约定 | 保留 |

**判别口诀**：删掉这段后，根 README 仍能让人启动起来吗？能 → 子 README 该写它；不能 → 它属于根 README。
