# MediGenius RAG 测评方案

本轮只评测 `RAG` 系统，不评测 `ECG` 流程。

目标分成两层：

1. `检索层`
   - 看知识库是否把正确证据召回回来
2. `回答层`
   - 在召回结果基础上，用 `LLM Judge` 判断回答是否正确、忠于证据、是否答到点上

## 一、评测数据集怎么构建

### 1. 数据来源

数据集直接来自当前知识库文档：

- `backend/data/knowledge/departments/*`
- `backend/data/knowledge/medical/*`

当前仓库已经提供了一个“基于文档自动生成的种子评测集”：

- `backend/data/eval/rag_eval_dataset_v1.jsonl`

它不是人工精标的最终版，而是第一版 `seed dataset`。

### 2. 构建思路

自动构建脚本：

- `backend/scripts/build_rag_eval_dataset.py`

脚本流程：

1. 遍历知识库文档并切 chunk
2. 过滤明显低质量 chunk
   - 前言 / 版权页 / 目录页
   - OCR 噪声特别重的页
   - 过短或过长的 chunk
3. 从正文 chunk 中抽取主题词
4. 按模板生成问题
5. 保存 gold 信息
   - 期望科室
   - 期望来源书籍
   - 期望锚点文本
   - 期望关键词
   - 参考答案片段

### 3. 数据集字段

每条样本包含：

- `id`
- `question`
- `selected_department`
- `expected_department`
- `expected_source_book`
- `expected_anchor_text`
- `expected_keywords`
- `reference_answer`
- `source_path`
- `page`

这些字段里：

- `expected_*` 用于做检索命中判断
- `reference_answer` 用于做 `LLM Judge correctness`

### 4. 正确的数据集构建方式

推荐采用“两阶段”：

1. `自动生成 seed`
   - 用现有脚本批量从教材文档里生成 50~200 条样本
2. `人工审核冻结`
   - 删除 OCR 噪声太重的样本
   - 修改不自然的问题表达
   - 确认 gold 锚点确实正确

建议最终冻结一版 `golden dataset`，不要每次评测都临时重建。

## 二、关键指标看什么

### 1. 检索指标

当前只保留最关键的三个：

- `Top1 Accuracy`
  - 第一条返回结果是否命中正确证据
- `Recall@K`
  - 前 `K` 条结果里是否包含正确证据
- `MRR`
  - 正确证据排位越靠前，分数越高

对于你的项目，最重要的是：

- `Recall@5`
- `Top1 Accuracy`
- `MRR`

因为医疗问答里，证据必须先“找得到”，再谈回答质量。

### 2. LLM Judge 指标

当前保留三个：

- `correctness`
  - 回答和参考答案是否一致，核心结论是否答对
- `faithfulness`
  - 回答是否忠于检索证据，有没有编造
- `relevance`
  - 回答是否直接回应用户问题

评分范围：

- `1 ~ 5`

推荐重点看：

- `judge_correctness_avg`
- `judge_faithfulness_avg`
- `judge_relevance_avg`
- `judge_pass_rate`

其中 `judge_pass_rate` 定义为：

- `correctness >= 4`
- `faithfulness >= 4`
- `relevance >= 4`

三者同时满足才算通过。

## 三、怎么跑评测

### 1. 生成数据集

```bash
/home/elon/miniconda3/envs/medigenius/bin/python \
  backend/scripts/build_rag_eval_dataset.py \
  --output backend/data/eval/rag_eval_dataset_v1.jsonl \
  --per-department 6
```

### 2. 跑纯检索评测

```bash
/home/elon/miniconda3/envs/medigenius/bin/python \
  backend/scripts/evaluate_rag_pipeline.py \
  --dataset backend/data/eval/rag_eval_dataset_v1.jsonl \
  --top-k 5
```

### 3. 跑检索 + LLM Judge

```bash
/home/elon/miniconda3/envs/medigenius/bin/python \
  backend/scripts/evaluate_rag_pipeline.py \
  --dataset backend/data/eval/rag_eval_dataset_v1.jsonl \
  --top-k 5 \
  --with-judge
```

### 4. 小样本调试

```bash
/home/elon/miniconda3/envs/medigenius/bin/python \
  backend/scripts/evaluate_rag_pipeline.py \
  --dataset backend/data/eval/rag_eval_dataset_v1.jsonl \
  --top-k 5 \
  --with-judge \
  --limit 10
```

## 四、怎么理解结果

### 1. 如果 `Recall@5` 低

优先排查：

- chunk 质量是否太差
- OCR 噪声是否污染 embedding
- query rewrite 是否无效
- 向量模型是否不适合中文医学教材
- 是否需要启用混合检索

### 2. 如果 `Recall@5` 高但 `correctness` 低

优先排查：

- reranker 排序不稳
- context packing 把关键证据裁掉了
- 生成 prompt 不够约束
- 模型没有严格依据证据回答

### 3. 如果 `faithfulness` 高但 `relevance` 低

说明模型很“老实”，但没有答到点上。
此时优先优化：

- query rewrite
- 回答模板
- prompt 中的任务指令

## 五、针对你项目最建议的流程

建议固定成下面这套节奏：

1. 先生成 `seed dataset`
2. 人工审核，冻结成 `golden dataset`
3. 每次改 `chunking / retriever / reranker / prompt` 后都回归
4. 每次只比较：
   - `Top1 Accuracy`
   - `Recall@5`
   - `MRR`
   - `judge_correctness_avg`
   - `judge_faithfulness_avg`
5. 只接受“指标提升或至少不退化”的改动

## 六、当前版本的注意事项

当前知识库主要来自 `EPUB + OCR` 文档，因此自动构建的数据集会有两个天然问题：

1. 部分 chunk 存在 OCR 噪声
2. 自动抽取的问题有时不够自然

因此当前 `rag_eval_dataset_v1.jsonl` 更适合作为：

- `第一版自动种子集`

而不是最终比赛或论文里的正式 gold set。

如果要做严肃评测，下一步应该是：

1. 从这份 `seed dataset` 中人工筛出高质量样本
2. 另存为 `rag_eval_dataset_gold_v1.jsonl`
3. 后续所有版本都对这份 gold 数据集做回归
