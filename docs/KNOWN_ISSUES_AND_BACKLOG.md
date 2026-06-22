# Known Issues & Backlog

最后更新: 2026-06-22

## 竞品档案需要独立事实源

现在竞品档案已经能在页面展示，包括产品名、厂商、赛道、竞争角色和一句话介绍。当前实现为了赶演示，先在 `/api/runs/{run_id}/knowledge` 里把两处历史数据合并成 `competitors[]` 返回，前端只消费这个字段。

问题在于底层还没有真正的单一写入点。竞品档案目前来自 discovery，但数据分散在两个地方：

- `steps.payload.discovered_competitor_sources`：近期 run 稳定有数据。
- `runs.plan_tree.competitor_sources`：只是镜像，部分 run 为空。

已观察到 `run_5d2f4e102594`、`run_c8a2c00298f9` 的 `runs.plan_tree` 为空，而 discovery step 里有完整的 `vendor / segment / introduction`。所以现在后端合并能解决展示问题，但不是最终数据模型。

短期不改。原因是当前页面已经可用，继续建表和迁移会扩大改动范围，演示前收益不如风险高。

以后如果要把竞品追踪做扎实，应把竞品档案沉到一个稳定位置，例如独立 `competitors` 表或 `run_knowledge.competitors` 字段。目标是 discovery 只写一处，`/knowledge` 直接读一处，前端契约保持 `knowledge.competitors` 不变。

触发条件：

- 竞品追踪需要按产品做长期 diff；
- 新增融资、上线时间、市场份额等竞品属性；
- 再次出现竞品介绍、厂商、赛道字段丢失。
