# RivalLens Frontend

RivalLens 联调控制台（React + Vite + TypeScript + Tailwind + shadcn/ui）。

## 1. 环境准备

- Node.js >= 18
- npm >= 10
- 后端 API 已运行（默认 `http://localhost:8010`）

## 2. 本地启动

```bash
cd frontend
npm install
npm run dev
```

默认访问：`http://localhost:5173`。

## 3. API 配置

- 环境变量：`VITE_API_BASE_URL`
- 默认值：`http://localhost:8010`
- 推荐在本机创建 `frontend/.env.local`（已 gitignore）

示例：

```bash
VITE_API_BASE_URL=http://localhost:8010
```

## 4. 已打通页面

- `/`：run 列表页
- `/runs/new`：新建任务
- `/runs/:run_id`：运行中/报告页（含 Evidence Drawer）
- `/runs/:run_id/trace`：开发者视图

## 5. 脚本

```bash
npm run dev
npm run build
npm run preview
npm run type-check
```

`npm run build` 会先跑 TypeScript 编译检查，再执行 Vite 构建。
