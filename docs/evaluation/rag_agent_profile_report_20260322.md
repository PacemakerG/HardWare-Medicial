# MediGenius RAG Agent 节点 Profiling 结果（2026-03-22）

## 1. Profiling 范围

- 数据集：`backend/data/eval/rag_eval_dataset_v1.jsonl`
- 样本量：`48`
- Profiling 目标：
  - 节点耗时
  - 检索行为
  - 回答与 Judge 的 token 估算
- 原始结果：`backend/data/eval/rag_agent_profile_full_20260322.json`

## 2. LangSmith 状态

| 项目 | 数值 |
| --- | --- |
| LANGSMITH_TRACING | false |
| LANGSMITH_PROJECT | medigenius |

说明：

- 当前这次实际跑分时，`LangSmith tracing` 没有开启。
- 如果你把环境变量里的 `LANGSMITH_TRACING=true` 并配置好 key，再运行同样脚本，`query_rewriter / rag / reranker` 这些节点会进入 LangSmith trace。

## 3. 节点耗时

| 节点 | Avg (ms) | P50 (ms) | P95 (ms) |
| --- | ---: | ---: | ---: |
| query_rewriter | 0.47 | 0.36 | 0.83 |
| rag | 786.38 | 211.72 | 2444.98 |
| reranker | 0.10 | 0.09 | 0.17 |
| total pipeline | 786.94 | 212.63 | 2445.39 |

### 结论

- 绝对瓶颈在 `rag` 节点。
- `query_rewriter` 和 `reranker` 几乎不耗时。
- `P95` 明显高于 `P50`，说明检索耗时波动很大，存在长尾样本。

## 4. 检索行为统计

| 指标 | 数值 |
| --- | ---: |
| Avg Context Count | 4.29 |
| Avg Retrieval Query Count | 2.50 |
| Avg Vector Hits | 4.83 |
| Avg Keyword Hits | 0.00 |

### 结论

- 当前基本只走了 `vector retrieval`。
- `keyword retrieval` 实际没有贡献，说明这版评测链路中混合召回还没有真正发挥作用。
- 平均每条样本会生成 `2.5` 条检索 query，但这些 query 并没有转化成有效召回提升。

## 5. Token 消耗估算

### 回答生成

| 指标 | 数值 |
| --- | ---: |
| Avg Prompt Tokens | 120.12 |
| Avg Completion Tokens | 68.88 |
| Avg Total Tokens | 189.00 |

### LLM Judge

| 指标 | 数值 |
| --- | ---: |
| Avg Prompt Tokens | 283.10 |
| Avg Completion Tokens | 13.00 |
| Avg Total Tokens | 296.10 |

### 合计

| 指标 | 数值 |
| --- | ---: |
| Combined Avg Total Tokens | 485.10 |

### 结论

- `LLM Judge` 比回答生成更耗 prompt token。
- 当前评测成本里，Judge 成本比回答成本更高。
- 如果要大规模回归测试，优先优化：
  - Judge prompt 压缩
  - 小模型 Judge 或分层 Judge
  - 先跑检索指标，再对命中样本跑 Judge

## 6. 最慢样本

| 样本 | Total (ms) | Query Count | Context Count |
| --- | ---: | ---: | ---: |
| dermatology_001 | 14859.38 | 2 | 4 |
| general_medical_001 | 4523.78 | 2 | 4 |
| general_surgery_001 | 2914.77 | 2 | 3 |
| infectious_disease_001 | 1573.69 | 2 | 0 |
| pediatrics_001 | 1520.01 | 2 | 4 |
| ophthalmology_001 | 1505.46 | 2 | 4 |
| neurology_001 | 1448.19 | 2 | 3 |
| ent_001 | 1160.90 | 2 | 2 |

### 结论

- 长尾耗时集中在特定样本，而不是 query rewriter 或 reranker。
- `infectious_disease_001` 这种 `Context Count = 0` 但仍然耗时高的样本，说明检索失败样本本身也可能很贵。

## 7. 关键判断

### 当前最主要的系统问题

1. `RAG 检索质量差`
2. `检索延迟集中在 rag 节点`
3. `Judge 成本偏高`
4. `LangSmith 已接入但这次未启用 tracing`

### 如果你要继续优化，优先级建议是

1. 先把 `gold dataset` 清洗好
2. 再优化 `rag` 节点本身：
   - 更干净的 chunk
   - 更强的 query rewrite
   - 真正启用 hybrid retrieval
   - 调整 reranker 前的召回池
3. 再压缩评测成本：
   - 缩短 Judge prompt
   - 只对命中样本跑 Judge
   - 或换更便宜的小模型 Judge
