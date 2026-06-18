# 竞品追踪功能完善计划（前后端全栈）

## Context

RivalLens 的竞品追踪（Watchlist）目前只是"命名收藏夹"：
- `WatchlistItem.next_refresh_at` 字段已建模但从未被读取，无调度逻辑
- 没有变更检测，无法感知"自上次分析以来发生了什么"
- 研究维度仅覆盖 feature/pricing/user_feedback，缺少业界标准信号
- 前端 WatchPage 仅支持 add/delete，无刷新调度 UI、无变更可视化

业界 CI 平台（Crayon、Klue）的核心价值：**持续监控 + 变更感知 + 广谱信号**

---

## Feature 1：Watchlist 定时刷新

### 后端

**DB 迁移：** `backend/app/alembic/versions/XXXX_watchlist_refresh_fields.py`

`watchlist` 表新增字段（同步更新 `backend/app/models/watchlist.py`）：
```python
last_refreshed_at: DateTime(timezone=True) | None
refresh_interval_hours: int | None   # None = 仅手动
last_run_id: str | None
```

**新文件：** `backend/app/service/watchlist/refresher.py`
```python
class WatchlistRefresher:
    async def run_once(self) -> None
        # 查询 next_refresh_at <= now() 的条目
        # 为每项创建 quick-tier Run（competitors=[competitor_id]）
        # 监听 RUN_FINISH 事件后更新 last_refreshed_at / last_run_id / next_refresh_at
        # 并发上限：同时触发 ≤ 3 个刷新 Run

    async def start_loop(self, interval_seconds=300) -> None
        # 后台轮询，参考 main.py 已有的 _sweep_orphan_running_runs 模式

    async def trigger_single(self, watch_id: str, *, session) -> str
        # 手动触发，返回 run_id
```

**注册：** `backend/app/main.py` lifespan 中 `asyncio.create_task(refresher.start_loop())`

**API 变更：** `backend/app/router/run_rt.py`
- `POST /api/watchlist` — 新增 `refresh_interval_hours?: int` 字段
- `PATCH /api/watchlist/{watch_id}` — 新增端点，更新 `refresh_interval_hours` / `next_refresh_at` / `note`
- `POST /api/watchlist/{watch_id}/refresh` — 手动立即触发，返回 `{run_id}`
- `GET /api/watchlist/digest` — 响应新增 `last_run_id`, `last_refreshed_at`, `next_refresh_at`

### 前端

**修改：** `frontend/src/api/types.ts`
```typescript
// WatchlistItemResponse 新增字段
interface WatchlistItemResponse {
  // ... 现有字段
  last_refreshed_at: string | null;
  refresh_interval_hours: number | null;
  last_run_id: string | null;
}

interface WatchlistUpdateRequest {
  note?: string;
  refresh_interval_hours?: number | null;
  next_refresh_at?: string | null;
}

interface WatchlistRefreshResponse { run_id: string }
```

**修改：** `frontend/src/api/hooks.ts`
```typescript
usePatchWatchlistItem()   // PATCH /api/watchlist/{watchId}
useManualRefreshWatchlist() // POST /api/watchlist/{watchId}/refresh → { run_id }
```

**新文件：** `frontend/src/components/watchlist/RefreshScheduleDialog.tsx`
- Radix Dialog（复用现有 `components/ui/dialog.tsx`）
- 刷新频率选择：手动 / 每日 / 每周 / 每两周（NativeSelect，参考 `components/ui/NativeSelect.tsx`）
- 下次刷新时间显示（`lib/format.ts` 格式化）
- 保存按钮调用 `usePatchWatchlistItem()`

**修改：** `frontend/src/pages/app/WatchPage.tsx`
- 每个 WatchlistDigestItem 卡片右上角新增：
  - "立即刷新" 按钮（`useManualRefreshWatchlist`，点击后跳转 `/app/runs/{run_id}/live`）
  - 调度设置按钮（打开 `RefreshScheduleDialog`）
- 刷新中状态：按钮 loading + disabled（参考现有 `useCreateWatchlistItem` 的 `isPending` 模式）
- 展示 `last_refreshed_at`、`next_refresh_at`（用 `lib/format.ts` 的相对时间格式）

---

## Feature 2：Competitive Diff 变更检测

### 后端

**新模型：** `backend/app/models/competitor_diff.py`
```python
class CompetitorDiff(Base):
    __tablename__ = "competitor_diffs"
    diff_id: str           # PK
    competitor_id: str     # indexed
    run_id_new: str        # FK runs
    run_id_old: str        # FK runs
    dimension: str
    change_type: str       # stance_changed | new_dimension | lost_dimension | summary_changed
    old_value: dict | None # JSONB: {stance, summary}
    new_value: dict | None # JSONB: {stance, summary}
    significance: str      # high | medium | low（LLM 判定）
    created_at: datetime
```

**新迁移：** `backend/app/alembic/versions/XXXX_competitor_diffs.py`

**新文件：** `backend/app/service/diff/comparator.py`
```python
async def compute_diff(*, run_id_new: str, competitor_id: str, session) -> list[CompetitorDiff]:
    # 1. 加载 run_id_new 的 comparison_cells（按 competitor_id 过滤）
    # 2. 查找同 competitor_id 最近一次成功 Run 的 comparison_cells
    # 3. 对比每个 dimension 的 stance + summary
    # 4. 有差异时调用 complete_structured() 判定 significance
    # 返回 diff 列表
```

LLM 调用复用 `backend/app/service/llm/harness.py` 的 `complete_structured()`。

**新文件：** `backend/app/service/diff/persistence.py` — 批量 upsert `CompetitorDiff`

**触发时机：** `backend/app/router/run_rt.py` 的 `_execute_run_graph()` terminal 段，
对 `run.competitors` 中有 watchlist 条目的竞品，异步触发 `compute_diff()`。

**API 变更：** `backend/app/router/run_rt.py`
- `GET /api/runs/{run_id}/diff` — 返回本次 Run 的全部 `CompetitorDiff` 记录
- `GET /api/watchlist/digest` — 响应新增 `recent_changes: list[CompetitorDiff]`（最近 5 条）

### 前端

**修改：** `frontend/src/api/types.ts`
```typescript
type DiffChangeType = "stance_changed" | "new_dimension" | "lost_dimension" | "summary_changed"
type DiffSignificance = "high" | "medium" | "low"

interface CompetitorDiffResponse {
  diff_id: string
  competitor_id: string
  run_id_new: string
  run_id_old: string
  dimension: string
  change_type: DiffChangeType
  old_value: { stance?: string; summary?: string } | null
  new_value: { stance?: string; summary?: string } | null
  significance: DiffSignificance
  created_at: string
}
```

**修改：** `frontend/src/api/hooks.ts`
```typescript
useRunDiff(runId: string)      // GET /api/runs/{runId}/diff
```

**新文件：** `frontend/src/components/comparison/CompetitorDiffCard.tsx`
- 按 `competitor_id` 分组展示变更条目
- `change_type` 对应的图标 + Badge（复用现有 `components/ui/badge.tsx`）：
  - `stance_changed` → "↑↓ 阵营变化"（significance=high: danger/success Badge）
  - `new_dimension` → "+ 新增维度" (accent Badge)
  - `lost_dimension` → "- 丢失维度" (warning Badge)
  - `summary_changed` → "~ 描述更新" (secondary Badge)
- old → new 箭头展示（`→` stance 旧值 → 新值）

**修改：** `frontend/src/pages/RunViewPage.tsx`
- "报告" tab 中 ComparisonMatrix 上方，当 `useRunDiff(runId)` 返回非空时展示 `CompetitorDiffCard`
- 提示文案："与上次分析相比，X 项维度发生变化"（可折叠）

**修改：** `frontend/src/pages/app/WatchPage.tsx`
- WatchlistDigestItem 卡片底部：展示 `recent_changes`（最多 3 条）
- 每条变更用一行紧凑格式：`[dimension] [change_type] [significance badge]`
- "查看完整报告" 链接指向 `/app/runs/{last_run_id}`

---

## Feature 3：新增信号维度

### 后端

**修改：** `backend/app/schemas/contracts.py`

在维度归一化映射中新增（参考现有 `market_differences` 等的添加方式）：
```python
"hiring_signals": ["hiring", "jobs", "recruitment", "talent"],
"recent_news":    ["news", "funding", "announcements", "press"],
"product_changelog": ["changelog", "releases", "updates", "version"],
```

**修改：** `backend/app/service/collector/source_resolver.py`

在 `_KEY_PAGE_BUCKETS` 中补充 changelog URL 模式（`/changelog`, `/releases`, `/updates`, `/blog/release`）。

**新技能文件**（参考现有 skills 的 YAML 格式）：
- `backend/skills/source_routing/hiring_signals_priority/SKILL.md` — 搜索词模板 + 提取指引（岗位数量、部门分布、关键岗位名称）
- `backend/skills/source_routing/recent_news_priority/SKILL.md` — 搜索词模板 + 提取指引（融资金额、收购方、发布日期）
- `backend/skills/source_routing/product_changelog_priority/SKILL.md` — 搜索词模板 + 提取指引（版本号、新功能列表、Breaking Changes）

### 前端

**修改：** `frontend/src/components/comparison/ComparisonMatrix.tsx`
- 表头维度名称用 `DimensionLabel` 映射展示中文（新增维度的中文标签）：
  ```typescript
  hiring_signals: "招聘动态",
  recent_news: "近期动态",
  product_changelog: "产品更新",
  ```
- 维度名无法识别时 fallback 为 title-case 原文（已有逻辑兼容）

**修改：** `frontend/src/pages/RunViewPage.tsx`（运行创建入口亦如此）
- 维度筛选 Chip 行（复用 `Badge` 组件变体 outline）：点击切换维度可见性，状态存 `useState`
- 三个新维度 Chip 与现有维度平等展示，无需特殊处理

---

## 关键文件一览

### 后端

| 文件 | 变更类型 |
|------|---------|
| `backend/app/models/watchlist.py` | 新增 3 个字段 |
| `backend/app/models/competitor_diff.py` | **新文件** |
| `backend/app/service/watchlist/refresher.py` | **新文件** |
| `backend/app/service/diff/comparator.py` | **新文件** |
| `backend/app/service/diff/persistence.py` | **新文件** |
| `backend/app/router/run_rt.py` | 新增 3 个端点，修改 watchlist create/digest，触发 diff |
| `backend/app/app_main.py` | 注册 refresher 后台任务 |
| `backend/app/schemas/contracts.py` | 新增 3 个维度 token |
| `backend/app/service/collector/source_resolver.py` | 扩展 changelog URL 模式 |
| `backend/skills/source_routing/hiring_signals_priority/SKILL.md` | **新文件** |
| `backend/skills/source_routing/recent_news_priority/SKILL.md` | **新文件** |
| `backend/skills/source_routing/product_changelog_priority/SKILL.md` | **新文件** |
| `backend/app/alembic/versions/0022_watchlist_refresh_and_diffs.py` | **新迁移** |

### 前端

| 文件 | 变更类型 |
|------|---------|
| `frontend/src/api/types.ts` | 新增 `WatchlistUpdateRequest`、`CompetitorDiffResponse` 等类型 |
| `frontend/src/api/hooks.ts` | 新增 `usePatchWatchlistItem`、`useManualRefreshWatchlist`、`useRunDiff` |
| `frontend/src/pages/app/WatchPage.tsx` | 新增刷新按钮、调度设置、recent_changes 展示 |
| `frontend/src/pages/RunViewPage.tsx` | 新增 CompetitorDiffCard、维度筛选 Chip 行 |
| `frontend/src/components/watchlist/RefreshScheduleDialog.tsx` | **新文件**（Dialog + 频率选择） |
| `frontend/src/components/comparison/CompetitorDiffCard.tsx` | **新文件**（变更列表卡片） |
| `frontend/src/components/comparison/ComparisonMatrix.tsx` | 新增中文维度标签映射 |

---

## 不在本次范围内

- 付费数据源（Crunchbase API、LinkedIn Talent Insights）
- 跨 Run 的全量对比选择器（两个任意 Run 对比，可作独立后续迭代）
- Battlecard 模板格式（Writer 节点独立迭代）
- 前端实时 WebSocket 推送（现有 SSE 满足基本需求）

---

## 验证步骤

1. **迁移验证**
   ```
   docker compose -f backend/docker-compose.dev.yml exec -T rivallens_api alembic upgrade head
   ```
   检查 `watchlist` 新字段和 `competitor_diffs` 表是否存在。

2. **Watchlist 刷新**
   - `POST /api/watchlist`（`refresh_interval_hours=1`）创建条目
   - 直接更新 DB 将 `next_refresh_at` 设为过去时间，观察后台是否自动触发 Run
   - `POST /api/watchlist/{watch_id}/refresh` 验证手动触发
   - 检查 Run 完成后 `last_refreshed_at`、`last_run_id` 更新，前端刷新按钮状态正确

3. **Diff 计算**
   - 对同一竞品跑两次 Run；
   - `GET /api/runs/{run_id}/diff` 确认有 `CompetitorDiff` 记录返回
   - 前端 RunViewPage 报告 Tab 中 CompetitorDiffCard 正常渲染
   - WatchPage digest 的 `recent_changes` 展示最近变更

4. **新维度**
   - 创建 Run，`focus_dimensions=["hiring_signals"]`
   - 检查 researcher `coverage_matrix` 中出现 `hiring_signals` 维度
   - ComparisonMatrix 前端展示"招聘动态"中文标签

5. **前端类型检查**
   ```
   cd frontend && npm run type-check
   ```
