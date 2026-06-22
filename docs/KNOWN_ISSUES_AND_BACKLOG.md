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

## 上游 URL 相关性过滤还不够稳

`fetch_url` 现在能抓全文，也会遵守 robots.txt。但最近的真实 run 里出现了另一个问题：有些抓取返回 `success=true`，内容却和当前竞品/维度不匹配。

已观察到 `run_5cbdf2f9f788` 里几类偏题内容：

- AI 硬件竞品任务抓到无线通信、ABI Research 营销页、全景扫描网站；
- 部分官网或文档页只是通用入口页，不能支撑功能、定价、用户反馈结论；
- robots.txt 拒绝 Reddit 抓取是合规跳过，不是质量 bug，但前端不能把它展示成系统失败。

影响是 writer 会拿到看似“达标”的证据，实际证据主题漂移，报告可能出现不该有的引用或空泛结论。

短期已经先修演示问题：robots 拒绝显示为合规跳过，`全景扫描` 选项不再进入检索词。

以后如果继续提高报告稳定性，应治理 URL admission：抓取成功后再判断页面是否同时匹配 `target_category / competitor_id / dimension`，不匹配就不要进入可引用证据池。

触发条件：

- 再次出现 `fetch_url success=true` 但证据正文明显偏题；
- 报告引用了官网首页、营销页、搜索入口页这类弱证据；
- 竞品追踪 diff 被偏题页面污染。
