# RivalLens

> Multi-Agent 协作的自动化竞品分析系统，每条结论可追溯到原始证据。

![Status](https://img.shields.io/badge/status-WIP-yellow)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-TBD-lightgrey)

## Background

传统竞品分析流程繁琐、信息源分散、对个人行业认知依赖大。RivalLens 通过 Collector / Extractor / Analyst / Writer / QA 五个专职 Agent 的 DAG 协作，自动完成从公开信息采集到结构化竞品报告的全链路输出，并保证每条分析结论可追溯到原始来源。

## Tech Stack

| 层 | 选型 |
|---|---|
| Orchestration | LangGraph + langgraph-checkpoint-postgres |
| Backend | FastAPI + Pydantic + SQLAlchemy + Python 3.11 |
| Database | PostgreSQL 16 |
| LLM | 豆包 Doubao-Seed-2.0-lite |
| Frontend | React + Vite + TypeScript |
| Deploy | docker compose |

## Local Development

### Backend

```bash
docker compose -f backend/docker-compose.dev.yml up -d
```

后端默认地址：`http://localhost:8010`。

### Frontend

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：`http://localhost:5173`，通过 `VITE_API_BASE_URL` 对接后端。

## License

TBD。
