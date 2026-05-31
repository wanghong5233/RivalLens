# RivalLens Frontend

> 项目入口见根目录 [`README.md`](../README.md)。

## Scope

该目录负责 RivalLens 前端应用：公开区（营销与分享）与工作区（分析执行与对比）。

## Routes

| Group | Routes |
|---|---|
| Public | `/`, `/examples`, `/pricing`, `/share/:runId` |
| Workspace | `/app`, `/app/runs/new`, `/app/runs/:runId`, `/app/compare`, `/app/watch`, `/app/settings` |

## Development

```bash
cd frontend
npm install
npm run dev
```

默认地址：`http://localhost:5173`。

## API Configuration

本地开发默认走 **Vite 代理**：前端请求 `/api/*` 由 `vite.config.ts` 转发到 `http://localhost:8010`，无需配置 CORS。

- 环境变量：`VITE_API_BASE_URL`（留空即可使用代理）
- 直连后端（不经代理）时设为：`http://localhost:8010`
- 推荐本地文件：`frontend/.env.local`

```bash
# 默认：留空，走 Vite /api 代理
VITE_API_BASE_URL=
```

## Scripts

```bash
npm run dev
npm run build
npm run preview
npm run type-check
```

## Notes

- 所有页面通过路由 `lazy()` 加载，减少首屏负担。
- 全局错误与请求失败通过 ErrorBoundary + Toaster 统一处理。
- 运行事件通过 SSE 分发到 report/metrics/trace 等 query cache。
