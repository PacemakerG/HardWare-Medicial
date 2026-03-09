# Agent 路由重构 TODO（执行版）

## 0. 目标

将当前多段决策链重构为“单一收口 + Executor 内部工具决策”架构：

`MemoryRead -> KeywordRouter -> (RAG | Judge1) -> Executor -> Async MemoryWrite`

约束：

- 所有主链路最终收口到 `ExecutorAgent`
- 移除 `Judge-2` 与 `ToolSelector` 节点
- `RAG Node` 仅执行检索，不做决策
- `MemoryWrite` 异步执行，不阻塞首字响应
- 防止 Executor 工具循环（严格 Stop Condition）

## 1. 目标架构（To-Be）

1. `MemoryAgent(Read)`
- 从用户画像 JSON 读取：`basic_info`, `preferences`, `current_context`
- 组装 `memory_context` 注入系统提示词

2. `KeywordRouter`
- 命中领域词（医疗/代码等） -> `RAG`
- 未命中 -> `JudgeAgent-1`

3. `JudgeAgent-1 (need_rag)`
- 输出严格 JSON：`{"need_rag": true|false, "reason": "..."}`
- `yes -> RAG`
- `no -> Executor(空 RAG_Context)`

4. `RAG Node`
- 仅检索并产出 `rag_context`
- 不做“是否足够回答”的判断

5. `ExecutorAgent`（唯一收口）
- 输入：`query + memory_context + rag_context(optional)`
- 内部按需工具调用：`WebSearch` 等
- 流式输出最终答案

6. `MemoryAgent(Async Write)`
- 后台异步解析 `(query, final_answer)`
- 有长期价值信息时触发 `update_profile`
- 原子覆盖写回 JSON

## 2. 任务拆解（按执行顺序）

### Phase A: 状态与路由重构
- [ ] 更新 `AgentState` 字段，新增/统一：
  - `memory_context`
  - `rag_context`
  - `need_rag`
  - `tool_budget_used`
  - `tool_calls`
- [ ] 重写 `langgraph_workflow.py` 节点与边：
  - 保留：`memory_read`, `keyword_router`, `judge_need_rag`, `rag`, `executor`, `memory_write_async_trigger`
  - 移除：`judge_rag_sufficiency`, `tool_selector`（如当前存在）
- [ ] 删除或下线路由中不再使用的旧分支函数

验收标准：
- [ ] 图中所有路径都能到达 `executor`
- [ ] 无无效分支键/返回值不一致问题

### Phase B: MemoryAgent 改造（读/写分离）
- [ ] 新增画像存储结构与读写工具（JSON 版）
- [ ] `MemoryRead`：将 JSON 转为可拼接的 `memory_context` 文本
- [ ] `MemoryWrite`：实现 `update_profile` 的 merge/覆盖策略
- [ ] 增加文件锁或原子写（防并发覆盖）

验收标准：
- [ ] 同一用户连续多轮后，画像字段按预期累积
- [ ] 并发写不出现 JSON 损坏

### Phase C: KeywordRouter + Judge1
- [ ] 抽离关键词词库与匹配器（可配置）
- [ ] 实现 `JudgeAgent-1` 轻量判断
- [ ] 固化 Judge 输出 schema（强约束解析）

验收标准：
- [ ] 关键词命中问题直达 RAG
- [ ] 非命中问题经 Judge1 后只产生 yes/no 两类分流

### Phase D: RAG Node 纯执行化
- [ ] 清理 RAG 内部决策逻辑（不再做足够性判断）
- [ ] 输出统一 `rag_context` 结构（chunks + metadata）

验收标准：
- [ ] RAG 失败/空结果时仍能进入 Executor
- [ ] RAG 成功时上下文可被 Executor 稳定消费

### Phase E: Executor（局部 ReAct + 停止条件）
- [ ] 统一三类输入模式：
  - 仅 memory + query
  - memory + rag
  - memory + rag + websearch result
- [ ] Executor 工具调用策略与停止条件：
  - `max_tool_calls = 2`
  - `max_same_tool_repeat = 1`
  - `tool_timeout_budget_sec = 10`（可配置）
  - 无新增信息则停止并回答
- [ ] 支持流式输出，并与后台 MemoryWrite 解耦

验收标准：
- [ ] 不出现工具无限循环
- [ ] 在工具失败/超时时仍返回稳定答案

### Phase F: Memory 异步写入接入
- [ ] 在 Executor 输出完成后触发异步 MemoryWrite
- [ ] 不阻塞用户响应（TTFB 不受影响）
- [ ] 写入失败仅记录日志，不影响主流程

验收标准：
- [ ] MemoryWrite 失败时用户仍得到完整回答
- [ ] 响应延迟相比同步写显著降低

### Phase G: 测试与回归
- [ ] 单测：路由、Judge1 schema、Executor stop condition、memory read/write
- [ ] 集成测试：关键词命中链路、非命中链路、RAG空结果链路、websearch链路
- [ ] 回归测试：API `/chat`, `/history`, `/sessions`

验收标准：
- [ ] 关键路径测试全部通过
- [ ] 新增测试覆盖到重构后的核心分支

### Phase H: 对话体验升级（中文 + 有温度 + 主动引导）
- [x] 将 Executor 主提示词改为“默认中文输出”，并引入个人医疗助手人格设定：
  - 温和、共情、尊重用户感受
  - 医疗建议谨慎，不做过度诊断
  - 以“可执行下一步”为目标
- [x] 固化回答结构（Response Contract）：
  - 先简短回应用户核心问题
  - 再给 1-3 条可执行建议
  - 最后一行必须主动追问“下一步问题”（引导继续对话）
- [x] 增加输出兜底规则（轻量后处理）：
  - 若模型输出非中文占比过高 -> 触发一次简短中文重述
  - 若结尾缺少追问句 -> 自动补一条安全追问模板
- [x] 与 Memory 结合的个性化表达：
  - 从 `preferences` 中读取称呼、表达风格、详细程度
  - 在不改变医学准确性的前提下调整语气
- [x] 安全边界模板：
  - 高风险症状（胸痛、呼吸困难、意识障碍等）优先急诊建议
  - 非紧急问题给出“居家观察 + 就医阈值”双轨建议

验收标准：
- [ ] 20 条中文用例中，回答末尾主动追问覆盖率 >= 95%
- [ ] 默认全中文回答（英文/拼写术语仅在必要场景出现）
- [ ] 用户主观体验评估中“更像个人助手”评分显著提升
- [ ] 高风险问题不会被“温和语气”掩盖紧急处置建议

### Phase I: ECG 报告 Skill 集成
- [x] 新增 ECG 报告数据契约（Request/Response Schema）
- [x] 新增 ECG 报告服务（参数整合 + 报告生成 + 风险分层）
- [x] 新增 API：`POST /api/v1/ecg/report`
- [x] 新增 API：`GET /api/v1/ecg/report/{id}`（历史查询）
- [x] 接入 Executor 轻量 Skill 触发（用户消息中携带 ECG JSON 时）
- [x] 报告摘要写入 Profile `current_context`（上次 ECG 结论可复用）
- [x] 高风险场景强制急诊提示 + 报告免责声明
- [x] 补充单测（服务、接口、Executor 触发路径）

验收标准：
- [x] 可用结构化 ECG 参数直接生成中文报告
- [x] LLM 不可用时仍能输出结构化 fallback 报告
- [x] ECG 接口支持直接生成与按 `report_id` 查询
- [x] ECG 写回 Profile 后可在后续对话中引用
- [x] 关键测试通过

## 3. 风险与控制

1. 风险：Executor 工具调用循环  
控制：硬预算 + 重复调用限制 + 超时限制 + 强制 final answer。

2. 风险：Memory JSON 并发覆盖  
控制：原子写 + 锁 + 失败重试（有限次数）。

3. 风险：Judge1 漂移导致误分流  
控制：关键词优先 + 二元 schema + 离线样本回归。

4. 风险：RAG 低质量召回影响答案  
控制：Executor 内部自主判断并按需触发 WebSearch。

5. 风险：只改 Prompt 仍会偶发跑偏（英文输出、无追问）  
控制：Prompt 约束 + 轻量输出后处理双保险。

6. 风险：过度“有温度”导致医学建议不够明确  
控制：先结论后关怀；高风险场景强制急诊模板优先。

## 4. 执行状态

- [x] 架构方向确认（当前会话）
- [x] TODO 文档落地
- [x] 进入 Phase A（代码改造）
- [x] Phase A 完成（State + Workflow 主链）
- [x] Phase B 完成（Profile JSON 读写 + Async 更新调度）
- [x] Phase C 完成（KeywordRouter + Judge1）
- [x] Phase D 完成（RAG 纯执行化）
- [x] Phase F 完成（Executor 后异步 MemoryWrite 触发）
- [ ] Phase E 持续完善（流式输出与工具策略细化）
- [ ] Phase G 全量回归（API 测试存在超时，需单独处理）
- [~] Phase H 进行中（中文体验与主动引导升级）
- [x] Phase I 完成（ECG 报告 Skill MVP）
- [x] ECG API + Memory + Safety 扩展完成（对应 4/5/6/7 条）
