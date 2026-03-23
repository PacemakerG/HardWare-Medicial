# MediGenius RAG 数据集测评结果（2026-03-22）

## 1. 测评范围

- 数据集：`backend/data/eval/rag_eval_dataset_v1.jsonl`
- 样本量：`48`
- 测评目标：仅评测 `RAG` 系统，不包含 `ECG`
- 评测方式：
  - 检索层：`Top1 Accuracy`、`Recall@5`、`MRR`
  - 回答层：`LLM Judge` 打分 `correctness / faithfulness / relevance`
- 详细原始结果：`backend/data/eval/rag_eval_result_full_20260322.json`

## 2. 总体结果

| 指标 | 数值 |
| --- | ---: |
| Top1 Accuracy | 0.0208 |
| Recall@5 | 0.0417 |
| MRR | 0.0278 |
| Judge Correctness Avg | 1.0208 / 5 |
| Judge Faithfulness Avg | 3.2917 / 5 |
| Judge Relevance Avg | 2.2708 / 5 |
| Judge Pass Rate | 0.0208 |

## 3. 分科室结果

| 科室 | 样本数 | Top1 | Recall@5 | MRR | Correctness | Faithfulness | Relevance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dermatology | 6 | 0.0000 | 0.0000 | 0.0000 | 0.8333 | 3.0000 | 1.8333 |
| ent | 6 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| general_medical | 6 | 0.0000 | 0.0000 | 0.0000 | 1.1667 | 5.0000 | 3.0000 |
| general_surgery | 6 | 0.0000 | 0.0000 | 0.0000 | 0.8333 | 4.0000 | 2.3333 |
| infectious_disease | 6 | 0.0000 | 0.1667 | 0.0556 | 1.1667 | 3.6667 | 2.8333 |
| neurology | 6 | 0.0000 | 0.0000 | 0.0000 | 1.1667 | 3.3333 | 2.3333 |
| ophthalmology | 6 | 0.1667 | 0.1667 | 0.1667 | 1.6667 | 3.6667 | 3.0000 |
| pediatrics | 6 | 0.0000 | 0.0000 | 0.0000 | 1.3333 | 3.6667 | 2.8333 |

## 4. 结果解读

### 检索层

- 当前 `Recall@5 = 4.17%`，说明系统在这版数据集上几乎无法稳定召回 gold 证据。
- 最好科室是 `ophthalmology` 和 `infectious_disease`，但也只达到 `16.67%` 的 `Recall@5`。
- `Top1 Accuracy` 只有 `2.08%`，说明第一条结果几乎总是错的。

### 回答层

- `Faithfulness` 明显高于 `Correctness`，说明模型经常“基于召回内容老实回答”，但召回内容本身就不对。
- `Correctness` 很低，说明答案核心事实通常没有答对。
- `Relevance` 也偏低，说明自动生成的问题中存在不少噪声，且 query rewrite 不能稳定把问题转成有效检索查询。

## 5. 典型样本观察

### 相对较好样本

- `infectious_disease_004`
  - Recall 命中
  - Judge：`correctness=2, faithfulness=3, relevance=4`
- `ophthalmology_006`
  - Recall 命中
  - Judge：`correctness=1, faithfulness=4, relevance=2`
- `ophthalmology_003`
  - Recall 未命中，但 Judge 给出 `5/5/5`
  - 说明自动 gold 匹配规则和检索内容之间仍存在偏差，当前数据集还不是最终 `golden set`

### 最差样本集中区

- `ent_*` 6 条样本全部为 `0` 分段
- `dermatology_005`、`dermatology_006` 等样本也完全失效
- 这说明当前自动种子集里仍有明显 OCR 噪声和问题模板不自然的问题

## 6. 当前结论

- 这份 `rag_eval_dataset_v1.jsonl` 可以作为第一版 `seed dataset`。
- 但它还不能直接当最终比赛或论文用的 `golden dataset`。
- 当前最主要瓶颈不是 LLM，而是：
  - 文档 OCR 噪声重
  - 自动抽题质量不足
  - gold 匹配规则仍然偏粗
  - 检索召回能力对噪声文本较弱

## 7. 下一步建议

1. 先人工清洗这 `48` 条样本，冻结成 `gold dataset`
2. 每个科室优先保留 `10~20` 条高质量样本
3. 再用这份 `gold dataset` 做后续 query rewrite / hybrid retrieval / reranker 的版本对比
4. 若继续自动构造数据集，需要进一步强化：
   - 正文 chunk 过滤
   - 主题词抽取
   - 问题模板自然度
   - gold 证据匹配标准
