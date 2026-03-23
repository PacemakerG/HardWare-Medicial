# 02｜RAG 全流程优化方案（MedAgent）

## 1. 目标与范围

本方案聚焦 MedAgent 的 RAG 全链路优化，覆盖：

1. 文档接入与切分（Ingestion / Chunking）
2. 向量索引与元数据（Indexing）
3. 查询改写与检索（Query Rewriter / Retriever）
4. 重排与上下文构建（Reranker / Context Packing）
5. 生成与安全（Generator / Guardrail）
6. 评测体系与节点级打点（Evaluation / Pipeline Profiling）

目标是把当前 Demo 级 RAG 提升到“可量化、可迭代、可上线”的工程形态。

---

## 2. 当前实现基线（项目现状）

## 2.1 关键链路

当前主链路（医疗场景）：

`Router -> QueryRewriter -> Retriever -> Reranker -> Executor`

对应核心文件：

- 切分与知识入库：`backend/app/tools/pdf_loader.py`
- 向量库：`backend/app/tools/vector_store.py`
- 检索：`backend/app/agents/retriever.py`
- 重排：`backend/app/agents/reranker.py`
- 查询改写：`backend/app/agents/query_rewriter.py`
- 执行生成：`backend/app/agents/executor.py`

## 2.2 当前切分参数

`RecursiveCharacterTextSplitter.from_tiktoken_encoder`：

- `chunk_size=512`
- `chunk_overlap=128`
- `separators=["\\n\\n", ". ", "\\n", " "]`

优势：简单稳定。  
不足：中文医疗文本语义边界利用不足，按场景自适应能力弱。

## 2.3 当前检索重排特点

- 检索：按 `department/domain` metadata 过滤 + 多 query 尝试。
- 重排：轻量规则分（词重叠 + scope 优先级 + raw rank），低延迟但语义精细度有限。

---

## 3. 全流程优化总览（目标架构）

建议改造成“两阶段检索 + 两阶段重排 + 可观测评测闭环”：

1. 文档预处理：清洗噪声、结构提取、术语归一化
2. 多策略切分：结构切分 + token 切分兜底（按文档类型动态参数）
3. 多路召回：向量召回 + 关键词召回（可选 BM25）+ scope 过滤
4. 融合与精排：RRF 融合后进入小模型 reranker（可降级）
5. 上下文打包：去重、覆盖关键子问题、长度预算控制
6. 生成与审计：基于证据回答 + 风险提示 + 来源记录
7. 评测闭环：Recall/MRR + LLM Judge + latency/cost + 节点 profiling

---

## 4. 分环节优化策略（可直接落地）

## 4.1 文档接入与清洗

### 现状问题

- 页眉页脚、目录、版权声明等噪声可能进入 chunk。
- 医疗术语同义表达不统一，影响召回（如“心梗/AMI”）。

### 优化建议

1. 清洗规则前置：
- 去页眉页脚（重复行检测）
- 去目录页（高密度页码/短行模式）
- 去版权页与无关附录

2. 结构化元数据增强：
- `chapter`, `section`, `subsection`
- `disease_tags`, `drug_tags`, `procedure_tags`
- `source_edition`, `publish_year`

3. 医疗术语标准化（可选词典）：
- 同义词映射：`心肌梗死 <-> 心梗 <-> AMI`
- 英中文缩写对齐：`AF, 房颤`

---

## 4.2 切分策略（Chunking）

### 现状问题

- 单一 `chunk_size=512` 不适配不同文档。
- 分隔符对中文医疗场景不够友好。

### 优化建议

1. 从“固定切分”改为“多策略切分”：
- 先结构切分（章/节/段）
- 再 token 切分兜底（超长块再分）

2. 分文档类型参数化：

| 文档类型 | chunk_size | overlap | 说明 |
|---|---:|---:|---|
| 教材叙述型 | 700-900 | 100-150 | 保证论证完整 |
| 指南/规范 | 400-600 | 80-120 | 精准定位条款 |
| FAQ/问答 | 250-400 | 40-80 | 提升命中精度 |

3. 中文医疗分隔符增强：
- `["\\n\\n", "。", "；", "：", "\\n", " "]`

4. Parent-Child 方案（推荐）：
- 子块入索引（精准召回）
- 父块回传生成（上下文完整）

5. 切分质量约束：
- 最小长度阈值（避免无效碎片）
- 信息密度阈值（过滤纯目录块）

---

## 4.3 索引与存储

### 现状问题

- 单向量索引，混合检索能力不够强。
- 缺少版本管理，不利于回滚与 A/B。

### 优化建议

1. 索引分层：
- 向量索引（Chroma）
- 关键词索引（可引入 BM25/ES）

2. 知识库版本化：
- `kb_version` 写入 metadata
- 支持灰度切换 `active_kb_version`

3. 元数据过滤标准化：
- `department`, `domain`, `source_type`, `chapter`

4. 增量更新流程：
- 新文档增量入库，不全量重建
- 周期性 compact + 校验

---

## 4.4 Query Rewriter 优化

### 现状问题

- 重写质量受模型波动影响。
- 对多跳问题覆盖仍不稳定。

### 优化建议

1. 双模式策略：
- Heuristic 快速模式（低延迟）
- LLM 重写模式（高质量）

2. 子查询拆分（复杂问题）：
- 最多 2-3 个子查询并行召回
- 子查询去重与互补性约束

3. 重写质量约束：
- 不允许引入原问题不存在的实体
- 强制保留核心症状词

4. 结果回退机制：
- LLM 重写失败自动降级到 heuristic query

---

## 4.5 检索优化（Retriever）

### 现状问题

- Scope 内召回数量固定，适应性不足。
- 没有显式查询预算管理。

### 优化建议

1. TopK 自适应：
- 主科室 `k` 更高，次科室与 general `k` 较低
- 依据 query 复杂度动态调整总候选数

2. 多路召回融合：
- 向量召回 + BM25 召回
- RRF 融合后再重排

3. 召回去重优化：
- 基于 `(source_path, section, paragraph_hash)` 去重
- 降低同页重复 chunk 污染

4. 失败快速回退：
- 无命中时触发“放宽过滤 + general 医疗库兜底”

---

## 4.6 重排优化（Reranker）

### 现状问题

- 当前规则精排对语义细粒度不足。

### 优化建议

1. 两阶段重排：
- 阶段1：规则精排（快速）
- 阶段2：小模型精排（cross-encoder/reranker）

2. 混合评分：
- `final_score = a*rule_score + b*model_score + c*freshness_score`

3. 可配置降级：
- 小模型不可用时自动回退规则精排

4. 输出多样性约束：
- Top context 要覆盖不同子问题/不同来源章节

---

## 4.7 上下文打包与生成

### 现状问题

- 可能出现上下文冗余，挤占 token。

### 优化建议

1. Context Packing：
- 去重后按“相关性 + 多样性”选 TopN
- 控制上下文 token 预算（如 2k/4k）

2. 证据引用化输出：
- 输出中可附 `source_book/section`（内部版）

3. 安全生成模板：
- 高风险问题强制紧急提示模板
- 未命中证据时降低结论强度，避免幻觉性肯定诊断

---

## 5. 评测体系（必须落地）

## 5.1 检索质量

核心指标：

- `Recall@K`
- `MRR@K`

对比组：

1. 原始 query 检索
2. query 重写后检索
3. reranker 前后对比

## 5.2 回答质量（LLM-as-Judge）

建议维度：

- Faithfulness（是否基于证据）
- Answer Relevance（是否答所问）
- Safety（医疗风险提示）

实践建议：

- 固定 judge prompt 与评分尺度（1-5）
- 抽样人工复核校准 judge 偏差

## 5.3 系统指标

- TTFT（首字延迟）
- E2E latency（总耗时）
- token in/out
- cost per query
- failure rate

---

## 6. 节点级打点（Pipeline Profiling）

按 LangGraph/流式执行链路逐节点埋点：

1. Input：请求时间戳、问题长度
2. Router：耗时、domain/use_rag/selected_department
3. QueryRewrite：耗时、原 query/改写 query
4. Retriever：每个 scope 耗时、召回数、chunk ids
5. Reranker：候选数、重排耗时、topk 分布
6. Executor：TTFT、生成耗时、tokens/s、工具调用次数

存储方式：

- `jsonl`（快速落地）
- 或 DB 表（后续可视化查询）

可视化建议：

- 时间瀑布图（单请求）
- 分位耗时图（P50/P95）
- 节点失败热力图

---

## 7. 迭代路线图（4周）

## Week 1：打基础（评测与打点）

- 搭建评测数据集 schema
- 接入节点级打点
- 出 baseline 报告（Recall/MRR/Latency/Cost）

## Week 2：切分与检索优化

- 上线多策略切分
- 召回链路加入混合检索
- 验证 Recall@3 / MRR 提升

## Week 3：重排与上下文打包

- 两阶段 reranker
- context packing 和 token 预算控制
- 验证 faithfulness 与延迟 tradeoff

## Week 4：灰度与稳定性

- 配置化开关、A/B 对比
- 失败回退策略打磨
- 输出阶段性复盘与下一步计划

---

## 8. 落地改造清单（对应当前代码）

优先改造文件：

- `backend/app/tools/pdf_loader.py`（多策略切分）
- `backend/app/agents/query_rewriter.py`（重写约束与多子查询）
- `backend/app/agents/retriever.py`（混合召回与自适应 K）
- `backend/app/agents/reranker.py`（两阶段精排）
- `backend/app/agents/executor.py`（context packing + 安全模板）
- `backend/app/services/chat_service.py`（节点打点汇总）
- `backend/app/core/config.py` + `.env.example`（开关配置）

新增建议：

- `backend/app/services/rag_eval_service.py`
- `backend/scripts/run_rag_eval.py`
- `docs/engineering/rag_eval_baseline_*.md`

---

## 9. 验收标准（DoD）

1. Recall@3、MRR@5 相比基线有统计意义提升。
2. Faithfulness 与 Answer Relevance 提升，且安全项不下降。
3. P95 延迟增长可控（或下降），成本可解释。
4. 每次请求可追踪到完整节点耗时与中间结果摘要。
5. 有可复现实验脚本与基线报告。

---

## 10. 一句话总结

RAG 优化不是“换一个更强模型”，而是把“切分-召回-重排-生成-评测”做成闭环工程，让每次改动都有量化收益与可追溯证据。
