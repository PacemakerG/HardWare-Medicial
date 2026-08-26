<div align="center">

# MedAgent

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

MedAgent 不是单轮医学问答 Demo，而是围绕真实请求链路构建的医疗 Agent 工作台，包含两条业务主线：

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
| B0 | 固定分块 + 单路向量 | 52.00% | 68.00% | 0.6060 | 25.06 ms |
| B1 | 语义边界分块 | 53.33% | 69.67% | 0.6190 | 31.84 ms |
| B2 | 父子索引 | 52.67% | 69.33% | 0.6135 | 42.73 ms |
| B3 | OCR/文本清洗 | 53.33% | 70.00% | 0.6205 | 29.61 ms |
| B4 | Query Rewrite | 53.33% | 75.33% | 0.6280 | 6344.59 ms |
| B5 | ES/向量并行 + RRF | 64.00% | 82.00% | 0.7150 | 38.07 ms |
| B6 | BGE Reranker | **72.00%** | **84.67%** | **0.7820** | 1054.75 ms |

### 最终组合与工程取舍

最终保留 **C2：固定分块 + 向量/Elasticsearch 并行召回 + RRF + BGE Reranker**。

| 组合 | Hit@1 | Recall@5 | MRR | 平均检索耗时 | 决策 |
| --- | ---: | ---: | ---: | ---: | --- |
| C0 基线 | 52.00% | 68.00% | 0.6060 | 25.06 ms | 基线 |
| C1 + Reranker | 72.00% | 84.67% | 0.7820 | 1054.75 ms | 保留 |
| C2 + ES/RRF | **80.00%** | **93.33%** | **0.8560** | 1067.76 ms | **最终方案** |
| C3 + Query Rewrite | 76.67% | 96.00% | 0.8300 | 7395.45 ms | 舍弃 |
| C4 + OCR/文本清洗 | 77.33% | 96.67% | 0.8360 | 7401.82 ms | 舍弃 |
| C5 + 语义边界分块 | 78.67% | 96.00% | 0.8420 | 7448.26 ms | 舍弃 |
| C6 + 父子索引 | 79.33% | 97.33% | 0.8480 | 7491.12 ms | 舍弃 |

- **保留 Reranker**：相对 B0，Hit@1 提升 20.00pp、Recall@5 提升 16.67pp、MRR 提升 0.1760，是独立贡献最大的模块。虽然增加约 1 秒检索耗时，但排序收益足以覆盖成本。
- **保留 ES + RRF**：在 Reranker 之上只增加约 13 ms，却将 Hit@1 继续提升 8.00pp、Recall@5 提升 8.66pp，并改善专业术语和英文缩写的精确召回。
- **默认关闭 Query Rewrite**：它把复杂问题展开成多个更宽泛的子查询，能扩大候选覆盖，但容易弱化原问题中的人群、阶段和条件限制。C2 加入该模块后 Recall@5 提升 2.67pp，Hit@1 却下降 3.33pp、MRR 下降 0.0260，平均额外增加约 6.3 秒。
- **舍弃语义边界分块**：独立实验只带来 Hit@1 1.33pp、Recall@5 1.67pp 的提升，却需要额外计算语义边界、维护切分阈值并增加知识库重建成本，固定分块加重叠窗口更简单可复现。
- **舍弃父子索引**：独立实验只提升 Hit@1 0.67pp、Recall@5 1.33pp、MRR 0.0075；累计实验相对 C5 也只有约 1pp 的增益，但需要维护父子双层索引、映射、去重和父文档回填，收益不足以覆盖复杂度。
- **仅保留基础文本规范化**：复杂 OCR 清洗的独立提升不超过 2pp；这批官方 PDF 原始质量较高，因此只保留页眉页脚、异常换行和乱码处理，不增加独立的复杂清洗链路。

### 路由与缓存结果

| 实验 | 基线 | 优化后结果 |
| --- | --- | --- |
| RAG | Hit@1 52.00%，Recall@5 68.00%，MRR 0.6060 | Hit@1 **80.00%**，Recall@5 **93.33%**，MRR **0.8560**，答案忠实度 **97.33/100** |
| 路由 | 路由准确率 76.00%，科室准确率 65.00% | 路由准确率 **92.00%**，科室准确率 **87.50%** |
| Redis | 完整 RAG 平均 10676.83 ms | 50 对命中判断 **100%**，缓存命中平均 **6.70 ms**，耗时下降 **99.94%** |

完整的指标定义、逐版本结果和实验边界见[评测结果](docs/evaluation/评测结果.md)。

## 快速开始

### 环境要求

- Python `3.11`
- Node.js `20+`
- Redis Stack（需要 RediSearch/`FT.SEARCH`，普通 Redis 不够）
- Elasticsearch `9.x`

### 安装与配置

```bash
git clone https://github.com/PacemakerG/MedAgent.git
cd MedAgent

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
MedAgent/
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

项目早期参考了[开源医疗 Agent 原型](https://github.com/Md-Emon-Hasan/MediGenius)。本仓库在原型基础上重构了分层路由、范围化 RAG、混合检索与重排、Redis 语义缓存、用户身份体系、ECG 交付和完整评测管线。

创作者：[ElonGe](https://github.com/PacemakerG) · [xhforever](https://github.com/xhforever)

## 免责声明

本系统仅用于医疗辅助、工程实践与科研演示，不替代执业医师诊断。出现胸痛、呼吸困难、意识改变等急性高风险症状时，请立即线下就医或呼叫急救。
