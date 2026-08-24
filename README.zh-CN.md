<div align="center">

# 医枢智疗 · MediGenius

**面向多科室医疗问答与 ECG 报告交付的工程化 AI Agent 系统**

从分层路由、混合检索和证据生成，到 Redis 语义缓存、LangSmith 评测与 SSE 流式交互，形成可运行、可观测、可评测的完整链路。

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](backend/pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0-1C3C3C)](https://github.com/langchain-ai/langgraph)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](frontend/package.json)
[![Redis](https://img.shields.io/badge/Redis_Stack-HNSW-DC382D?logo=redis&logoColor=white)](https://redis.io/docs/latest/develop/interact/search-and-query/)
[![Elasticsearch](https://img.shields.io/badge/Elasticsearch-9.4-005571?logo=elasticsearch&logoColor=white)](docker-compose.yml)

[English](./README.md) · **简体中文** · [评测方案](docs/evaluation/评测方案.md) · [评测结果](docs/evaluation/评测结果.md)

</div>

---

## 项目简介

医枢智疗不是单轮医学问答 Demo，而是围绕真实请求链路构建的医疗 Agent 工作台，包含两条业务主线：

- **多科室医疗问答**：识别医学问题，路由至 8 个科室，在限定知识范围内执行向量/关键词混合检索、RRF 融合和 BGE 重排，必要时使用联网搜索。
- **ECG 报告交付**：抓取或接收结构化心电数据，完成参数分析、风险分层，并输出包含波形的中文 PDF 报告。

系统同时覆盖用户与会话隔离、长期记忆、SSE 流式返回、语义缓存、限流、异步任务、LangSmith 链路追踪和专项评测。

## 核心能力

| 能力 | 实现 |
| --- | --- |
| Agent 编排 | LangGraph 9 节点工作流，所有分支汇聚至统一 Executor |
| 分层路由 | 医疗/非医疗判断 + 8 科室分类 + 本地 RAG/联网搜索决策 |
| 混合检索 | ChromaDB 向量召回与 Elasticsearch BM25 并行，使用 RRF 融合 |
| 结果重排 | 规则预排序 + `BAAI/bge-reranker-v2-m3` 交叉编码器重排 |
| 语义缓存 | `qwen3.5-flash` 结构化抽取 + Redis Stack TAG 过滤 + HNSW 向量检索 |
| 实时交互 | FastAPI SSE 按 Token 增量返回，前端实时渲染 |
| 身份隔离 | `user_id + session_id` 校验会话归属，PBKDF2 密码哈希与 HMAC Token |
| 可观测评测 | LangSmith Trace + RAG、路由、Redis 三套独立评测集 |

## 系统架构

```text
React / Vite
    │
    ├── REST：认证、会话、ECG、任务查询
    └── SSE：医疗问答流式输出
             │
             ▼
      Redis Semantic Cache
       ├── Hit ───────────────────────────────────────► Response
       └── Miss
             │
             ▼
        MemoryRead
             │
        KeywordRouter ── 非医疗 ──► JudgeNeedRAG ─────┐
             │                                        │
           医疗                                       │
             ▼                                        │
        MedicalRouter（8 科室）                       │
             │                                        │
        QueryRewriter（默认透传，可配置）              │
             │                                        │
        Vector + Elasticsearch ──► RRF                │
             │                                        │
        BGE Reranker                                  │
             └──────────────────► Executor ◄──────────┘
                                      │
                           MemoryWriteAsync
                                      │
                         Semantic Cache Store
                                      │
                                  Response
```

### 八科室检索范围

通用医疗、普外科、儿科、神经内科、感染科、耳鼻喉科、眼科、皮肤科。

- 专业科室只检索对应科室 PDF，减少跨领域噪声。
- 通用医疗检索全部医学 PDF，兼容跨科室问题。
- 手动选择科室和自动路由使用相同的范围控制规则。

## Redis 语义缓存

缓存不会仅凭“两个问题向量很像”就复用答案，而是先比较能够改变答案的结构化语义，再执行向量检索。

```text
Question
   │
   ├── qwen3.5-flash
   │      └── { entities, action, constraints }
   │
   ├── BAAI/bge-small-zh-v1.5
   │      └── 512-d normalized embedding
   │
   └── FT.SEARCH
          ├── entities：TAG 精确匹配
          ├── action：TAG 精确匹配
          ├── constraints：TAG 精确匹配
          └── embedding：KNN Top1，cosine similarity ≥ 0.80
```

每条缓存使用带 TTL 的 Redis Hash：

```text
Key: mg:semcache:item:{uuid}

entities | action | constraints | embedding | answer
```

查询使用 `FT.SEARCH` 完成三字段过滤与向量 KNN；只有三个结构字段完全一致且相似度达到 `0.80` 才读取 `answer`。任一抽取、向量或 Redis Search 步骤失败，都会按缓存未命中继续完整 RAG，不阻断请求。

## 评测体系

三套数据集独立构建、独立计算指标，共 250 个样本：

| 系统 | 数量 | 数据划分 | 核心指标 |
| --- | ---: | --- | --- |
| RAG | 150 | 单跳 50、多跳 50、困难检索 50 | Hit@1、Recall@5、MRR、答案忠实度 |
| 路由 | 50 | 本地 RAG 30、联网医疗 10、非医疗 10 | 路由准确率、科室准确率 |
| Redis | 50 对 | 语义等价 25、不可复用 25 | 缓存命中准确率、平均耗时 |

RAG 使用 20 份完整医学 PDF、3219 页作为候选语料，不使用只包含正确证据的裁剪语料。问题由英文原始证据反向构造，因此 RAG Query 保持英文；中文产品入口、路由和缓存专项保持中文。

### RAG 独立模块实验

每个模块先单独与同一个 B0 基线比较，再进行累计组合，避免把累计收益错误归因给最后一个模块。

| 版本 | 相对 B0 的单一变化 | Hit@1 | Recall@5 | MRR | 平均检索耗时 |
| --- | --- | ---: | ---: | ---: | ---: |
| B0 | 固定分块 + 单路向量 | 14.67% | 35.33% | 0.2419 | 25.06 ms |
| B1 | 语义边界分块 | 16.00% | 31.67% | 0.2412 | 16.64 ms |
| B2 | 父子索引 | 12.00% | 36.00% | 0.2297 | 16.79 ms |
| B3 | OCR/文本清洗 | 12.67% | 36.33% | 0.2321 | 16.79 ms |
| B4 | Query Rewrite | 14.67% | 38.00% | 0.2511 | 6344.59 ms |
| B5 | ES/向量并行 + RRF | 19.33% | 41.67% | 0.2989 | 17.64 ms |
| B6 | BGE Reranker | **28.67%** | **44.33%** | **0.3773** | 1054.75 ms |

### 最终组合与工程取舍

最终保留 **C2：固定分块 + 向量/Elasticsearch 并行召回 + RRF + BGE Reranker**。

| 组合 | Hit@1 | Recall@5 | MRR | 平均检索耗时 | 决策 |
| --- | ---: | ---: | ---: | ---: | --- |
| C0 基线 | 14.67% | 35.33% | 0.2419 | 25.06 ms | 基线 |
| C1 + Reranker | 28.67% | 44.33% | 0.3773 | 1054.75 ms | 保留 |
| C2 + ES/RRF | **30.00%** | **48.67%** | **0.4050** | 1067.76 ms | **最终方案** |
| C3 + Query Rewrite | 26.67% | 54.67% | 0.3970 | 7395.45 ms | 舍弃 |
| C6 含父子索引 | 22.67% | 46.33% | 0.3453 | 7393.07 ms | 舍弃 |

- **保留 Reranker**：独立模块中综合提升最大。
- **保留 ES + RRF**：只增加约 13 ms，三个检索指标继续提升。
- **默认关闭 Query Rewrite**：Recall@5 上升，但 Hit@1、MRR 下降，平均额外增加约 6.3 秒。
- **舍弃父子索引**：最终组合质量下降，同时增加索引、存储和链路复杂度。

### 路由与缓存结果

| 实验 | 当前结果 | 状态说明 |
| --- | --- | --- |
| 路由 | 路由准确率 76.00%，科室准确率 65.00% | 优化前诊断值；修正后的模型重跑待补 |
| Redis | 50 对命中判断 100%；约 10.7 s → 6.70 ms | 五字段签名代码已落地；真实 Redis Stack v2 回归待归档 |

答案忠实度的未完成版本和修正后路由实验需要模型调用，README 不将其标记为已完成。完整定义、逐版本忠实度覆盖和实验边界见[评测结果](docs/evaluation/评测结果.md)。

## 快速开始

### 环境要求

- Python `3.11`
- Node.js `20+`
- Redis Stack（需要 RediSearch/`FT.SEARCH`，普通 Redis 不够）
- Elasticsearch `9.x`

### 安装与配置

```bash
git clone https://github.com/PacemakerG/HardWare-Medicial.git
cd HardWare-Medicial

cp backend/.env.example backend/.env

cd backend
uv sync --extra dev

cd ../frontend
npm install
```

至少配置以下变量：

```dotenv
OPENAI_BASE_URL=your-openai-compatible-base-url
OPENAI_API_KEY=your-api-key
LLM_MODEL=Pro/deepseek-ai/DeepSeek-V3.2
LIGHT_LLM_MODEL=Pro/deepseek-ai/DeepSeek-V3.2

REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
SEMANTIC_CACHE_EXTRACTION_MODEL=qwen3.5-flash

ES_ENABLED=true
ES_HOST=http://localhost:9200
```

### 启动

```bash
# 启动 Redis Stack 与 Elasticsearch
docker compose up -d redis elasticsearch

# 启动后端与前端
python run.py
```

默认地址：前端 `http://localhost:5173`，后端 `http://localhost:8000`，OpenAPI 文档 `http://localhost:8000/docs`。

## 本地医学知识库

医学 PDF 体积较大且受发布机构条款约束，只保留在本地，不提交 GitHub。请根据[官方来源清单](backend/data/knowledge/医学知识库官方下载来源.md)下载，并保持清单中的目录和文件名；下载完成后重新构建向量库。

## 复现实验

```bash
cd backend

uv run python scripts/evaluation/build_datasets.py --validate-only
uv run python scripts/evaluation/upload_langsmith.py
uv run python scripts/evaluation/evaluate_rag.py --with-faithfulness
uv run python scripts/evaluation/evaluate_routing.py
uv run python scripts/evaluation/evaluate_redis_cache.py
```

正式实验要求 LLM、Tavily、Redis Stack Search 与 Elasticsearch 均为真实可用服务，不以 mock 结果替代。

## 测试

```bash
# 后端
cd backend
uv run pytest -q

# 真实 Redis Stack 集成测试
REDIS_ENABLED=true RUN_REDIS_STACK_INTEGRATION=1 \
uv run pytest tests/test_semantic_cache_redis_integration.py -q

# 前端
cd ../frontend
npm test -- --run
npm run build
```

## 项目结构

```text
HardWare-Medicial/
├── backend/
│   ├── app/
│   │   ├── agents/              # LangGraph 节点
│   │   ├── api/v1/              # FastAPI 接口
│   │   ├── core/                # 配置、状态、工作流、科室体系
│   │   ├── services/            # 会话、认证、缓存、ECG、任务服务
│   │   └── tools/               # LLM、向量库、ES、重排、联网工具
│   ├── data/eval/               # 三套评测集与结果
│   ├── data/knowledge/          # 本地 PDF（Git 忽略）与来源清单
│   ├── scripts/evaluation/      # 五个统一评测脚本
│   └── tests/                   # 单元、工作流与真实服务集成测试
├── frontend/                    # React 19 / Vite 单页应用
├── docs/evaluation/             # 评测方案与评测结果
├── hardware/                    # ECG 数据处理脚本
└── run.py                       # 全栈启动入口
```

## API 概览

| 模块 | 主要接口 |
| --- | --- |
| 认证 | `POST /api/v1/auth/login`、`GET /api/v1/auth/me` |
| 对话 | `POST /api/v1/chat`、`POST /api/v1/chat/stream` |
| 会话 | `GET /api/v1/sessions`、`GET/DELETE /api/v1/session/{session_id}` |
| ECG | `POST /api/v1/ecg/report`、`GET /api/v1/ecg/report/{id}/pdf` |
| 健康检查 | `GET /api/v1/healthz`、`GET /api/v1/readyz` |

## 致谢

项目早期灵感来自 [Md. Emon Hasan / MediGenius](https://github.com/Md-Emon-Hasan/MediGenius)。本仓库在原型基础上重构了分层路由、范围化 RAG、混合检索与重排、Redis 语义缓存、用户身份体系、ECG 交付和完整评测管线。

创作者：[ElonGe](https://github.com/PacemakerG) · [xhforever](https://github.com/xhforever)

## 免责声明

本系统仅用于医疗辅助、工程实践与科研演示，不替代执业医师诊断。出现胸痛、呼吸困难、意识改变等急性高风险症状时，请立即线下就医或呼叫急救。
