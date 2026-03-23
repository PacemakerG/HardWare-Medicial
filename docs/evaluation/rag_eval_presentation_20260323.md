# MediGenius RAG 评测与监控展示版报告（2026-03-23）

## 1. 一页结论

本次工作完成了两件核心事情：

1. 将自动生成、噪声较重的 `seed dataset` 清洗为一版更可信的 `gold dataset`
2. 基于 `gold dataset` 重新执行 RAG 检索评测、LLM-as-Judge 评测和节点级 Profiling

这一步的意义不是“把指标做高”，而是先把评测基线做对。对于医疗 RAG 系统，如果数据集本身含有大量 OCR 噪声、问题表达不自然、gold 锚点不稳定，那么后续所有检索优化都很难被客观验证。

当前结论：

- 评测数据质量显著提升，系统表现从“几乎不可解释”进入“可分析、可回归”的阶段
- 当前系统的最大瓶颈仍然不在 LLM，而在 `RAG 检索链路`
- 具体来说，瓶颈主要集中在：
  - 知识切分质量不足
  - OCR 噪声仍然污染 embedding
  - hybrid retrieval 贡献偏低
  - `rag` 节点耗时存在明显长尾

---

## 2. 本次产物

### 数据集

- `seed dataset`：
  - `backend/data/eval/rag_eval_dataset_v1.jsonl`
  - 样本数：`48`
- `gold dataset`：
  - `backend/data/eval/rag_eval_dataset_gold_v1.jsonl`
  - 样本数：`19`

### 脚本

- `seed -> gold` 清洗脚本：
  - `backend/scripts/build_rag_gold_dataset.py`
- RAG 评测脚本：
  - `backend/scripts/evaluate_rag_pipeline.py`
- Agent Profiling 脚本：
  - `backend/scripts/profile_rag_agents.py`

### 原始输出

- Gold 评测结果：
  - `backend/data/eval/rag_eval_result_gold_v1_20260323.json`
- Gold Profiling 结果：
  - `backend/data/eval/rag_agent_profile_gold_v1_20260323.json`

---

## 3. 为什么要从 Seed 升级到 Gold

`seed dataset` 是系统自动从知识库中逆向生成的问题集合，优点是构建快，缺点是噪声大。

主要问题有三类：

1. 原始医学教材来自 `EPUB + OCR`，部分 chunk 本身质量不高
2. 自动抽题会生成不自然的问题，甚至带有目录页或版权页噪声
3. 自动 gold 匹配标准偏粗，导致“系统其实答得还行，但评测判成错”

所以正确做法不是直接用 `seed` 做最终结论，而是：

1. 先自动生成一批种子样本
2. 再人工审核、重写、冻结成 `gold dataset`
3. 后续所有优化都在这份 `gold` 上做回归

这也是更符合面试和比赛答辩逻辑的一种说法：我不是盲调系统，而是先把评测基线做扎实。

---

## 4. 核心指标对比：Seed vs Gold

| 指标 | Seed（48） | Gold（19） | 变化 |
| --- | ---: | ---: | ---: |
| Top1 Accuracy | 0.0208 | 0.1053 | +0.0845 |
| Recall@5 | 0.0417 | 0.1579 | +0.1162 |
| MRR | 0.0278 | 0.1316 | +0.1038 |
| Judge Correctness Avg | 1.0208 | 1.5789 | +0.5581 |
| Judge Faithfulness Avg | 3.2917 | 4.8947 | +1.6030 |
| Judge Relevance Avg | 2.2708 | 3.5789 | +1.3081 |
| Judge Pass Rate | 0.0208 | 0.1053 | +0.0845 |

### 结果解读

- `Top1 / Recall@5 / MRR` 都有明显提升，说明清洗后的数据集更能真实反映系统能力
- `Faithfulness` 提升最明显，说明模型在有证据时能较好地“据实回答”
- `Correctness` 仍然偏低，说明根本问题还在前面的检索和证据组织阶段

一句话概括：

当前系统的回答风格是“相对老实，但还不够准”。

---

## 5. 按评测层次看系统现状

### 第一层：检索层

当前最核心的三个指标是：

- `Top1 Accuracy`
- `Recall@5`
- `MRR`

在医疗场景里，检索层是整个系统的地基。因为如果前 5 个 chunk 里都没有正确证据，后面的 LLM 再强也只能谨慎地回答“资料不足”或者产生幻觉。

当前表现说明：

- 系统已经能在部分问题上命中 gold 证据
- 但整体召回率仍偏低，说明知识切分和召回策略还有较大优化空间

### 第二层：回答层

使用 `LLM-as-Judge` 打三个维度：

- `correctness`：答得对不对
- `faithfulness`：有没有脱离证据乱说
- `relevance`：有没有答到点上

当前表现说明：

- `faithfulness = 4.8947`，已经很高
- `relevance = 3.5789`，中等偏上
- `correctness = 1.5789`，偏低

这组结果很有解释性，因为它说明：

- 不是模型胡说八道
- 而是系统多数时候没有拿到真正正确的医学证据

这恰好把瓶颈定位到了检索链路，而不是生成链路。

---

## 6. Gold 数据集下的分科室结果

| 科室 | 样本数 | Top1 | Recall@5 | MRR | Correctness | Faithfulness | Relevance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dermatology | 3 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 5.0000 | 3.3333 |
| ent | 2 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 4.5000 | 3.5000 |
| general_medical | 3 | 0.0000 | 0.0000 | 0.0000 | 1.3333 | 5.0000 | 3.0000 |
| general_surgery | 2 | 0.0000 | 0.0000 | 0.0000 | 1.5000 | 5.0000 | 3.5000 |
| infectious_disease | 2 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 5.0000 | 3.0000 |
| neurology | 2 | 0.5000 | 0.5000 | 0.5000 | 3.0000 | 5.0000 | 4.5000 |
| ophthalmology | 3 | 0.3333 | 0.3333 | 0.3333 | 2.3333 | 5.0000 | 4.0000 |
| pediatrics | 2 | 0.0000 | 0.5000 | 0.2500 | 1.5000 | 4.5000 | 4.0000 |

### 分析

- 当前效果相对较好的科室是：
  - `neurology`
  - `ophthalmology`
  - `pediatrics`
- 效果较差的科室主要是：
  - `dermatology`
  - `ent`
  - `infectious_disease`
  - `general_medical`
  - `general_surgery`

这说明不同科室知识库的文档质量和可检索性差异很大，后续不应该只做全局优化，而要做“按科室分治”。

---

## 7. 典型样本观察

### 表现最好样本

1. `neurology_001`
   - 问题：`TIA患者在什么情况下建议住院治疗？ABCD2评分怎么用？`
   - 指标：`Top1=1, Recall=1, MRR=1.0`
   - Judge：`5 / 5 / 5`

2. `ophthalmology_001`
   - 问题：`ETDRS视力检查法有什么特点，临床上怎么使用？`
   - 指标：`Top1=1, Recall=1, MRR=1.0`
   - Judge：`5 / 5 / 5`

这些样本说明：当文档质量较好、问题表达明确、gold 锚点稳定时，当前系统是可以形成“检索命中 + 回答正确”的闭环的。

### 表现较差样本

1. `dermatology_004`
2. `dermatology_006`
3. `ent_002`
4. `infectious_disease_002`
5. `infectious_disease_005`

这些样本大多呈现出相同模式：

- 检索没有命中 gold
- 模型没有乱答，而是保守作答
- Judge 的 `faithfulness` 高，但 `correctness` 低

这进一步证明：当前系统最主要的短板仍然是“找不到对的内容”。

---

## 8. 节点级 Profiling 结果

### 8.1 LangSmith 状态

| 项目 | 数值 |
| --- | --- |
| LANGSMITH_TRACING | false |
| LANGSMITH_PROJECT | medigenius |

说明：

- 本轮实际跑分时，`LangSmith tracing` 没有开启
- 也就是说当前 profiling 结果来自本地脚本埋点，而不是 LangSmith 云端 trace
- 但 LangSmith 接入位已经预留，后续打开环境变量即可采集更完整的链路信息

### 8.2 节点耗时

| 节点 | Avg (ms) | P50 (ms) | P95 (ms) |
| --- | ---: | ---: | ---: |
| query_rewriter | 0.46 | 0.39 | 0.69 |
| rag | 3233.26 | 356.87 | 8129.18 |
| reranker | 0.12 | 0.12 | 0.16 |
| total pipeline | 3233.83 | 357.37 | 8129.66 |

### 8.3 结果解读

- 绝对瓶颈是 `rag` 节点
- `query_rewriter` 和 `reranker` 几乎可以忽略不计
- `P95` 远高于 `P50`，说明系统存在明显长尾延迟

这代表两件事：

1. 平均值并不能真实反映用户体验，因为一部分请求非常慢
2. 优化重点应落在检索与召回链路，而不是先去纠结 prompt 微调

---

## 9. 检索行为统计

| 指标 | 数值 |
| --- | ---: |
| Avg Context Count | 5.63 |
| Avg Retrieval Query Count | 2.79 |
| Avg Vector Hits | 8.26 |
| Avg Keyword Hits | 0.58 |

### 结果解读

- 平均每个问题会拆成约 `2.79` 条检索 query
- 向量召回贡献明显高于关键词召回
- `keyword hits` 只有 `0.58`，说明当前 hybrid retrieval 还没有真正形成有效增益

这意味着：

- query rewrite 已经在扩大召回范围
- 但 BM25 / 关键词检索分支还比较弱
- 后续可以重点增强：
  - 医学术语标准化
  - 别名词典
  - 关键词检索召回池

---

## 10. Token 成本

### 回答生成

| 指标 | 数值 |
| --- | ---: |
| Avg Prompt Tokens | 150.53 |
| Avg Completion Tokens | 60.11 |
| Avg Total Tokens | 210.63 |

### LLM Judge

| 指标 | 数值 |
| --- | ---: |
| Avg Prompt Tokens | 304.79 |
| Avg Completion Tokens | 13.00 |
| Avg Total Tokens | 317.79 |

### 合计

| 指标 | 数值 |
| --- | ---: |
| Combined Avg Total Tokens | 528.42 |

### 结果解读

- 当前评测链路里，`LLM Judge` 比“正式回答”更耗 token
- 所以在大规模回归时，不能每次都全量跑 Judge

建议的成本控制策略：

1. 先跑检索指标
2. 只对关键样本或命中样本跑 Judge
3. 对 Judge 使用更便宜的小模型
4. 压缩 Judge prompt

---

## 11. 当前最重要的瓶颈

### 瓶颈 1：知识切分质量还不够好

现有 chunk 仍然可能存在：

- OCR 噪声
- 语义边界断裂
- 医学定义、适应证、禁忌证被切散

这会直接影响 embedding 和召回质量。

### 瓶颈 2：混合召回没有真正发挥效果

虽然链路中存在 query rewrite 和关键词召回，但统计上看 `keyword hits` 很低，说明：

- 关键词通道权重偏低
- 医学术语词表不足
- 规则侧补召回还没形成有效覆盖

### 瓶颈 3：RAG 节点延迟长尾严重

`rag p95 = 8129.18 ms`，已经足够影响交互体验。

这意味着：

- 不能只看平均值
- 必须对慢样本单独排查
- 需要做更细粒度的节点 trace 和缓存策略

---

## 12. 下一阶段优化优先级

### P0：先把评测闭环固定住

1. 冻结 `gold dataset`
2. 后续每次优化都只和这版 gold 对比
3. 在报告里长期跟踪：
   - `Top1`
   - `Recall@5`
   - `MRR`
   - `Correctness`
   - `Faithfulness`
   - `Latency`

### P1：优化切分和召回

1. 引入更强的结构化 chunking
2. 对目录页、版权页、低质量 OCR 页做更严格过滤
3. 增强 `vector + BM25` 混合召回
4. 按科室构建别名词典和关键词扩展

### P2：优化排序与上下文打包

1. 加强 reranker
2. 做证据去重和段落合并
3. 提升 context packing 的证据密度

### P3：优化监控与成本

1. 打开 LangSmith tracing
2. 将节点 trace 纳入常规回归
3. 分层执行 Judge，控制 token 成本

---

## 13. 适合比赛或汇报时的一句话总结

如果要在答辩现场用一句话概括这次工作，可以这样说：

> 我们没有盲目调 RAG，而是先建立了一套可复现的评测与监控闭环：先从自动种子集清洗出 gold 数据集，再从检索、回答、系统耗时三个层次做量化评估，并用节点级 profiling 找到真正瓶颈。目前结果表明，系统的核心短板不是大模型生成，而是医学知识的召回质量和检索链路长尾延迟，这为下一步优化提供了明确方向。
