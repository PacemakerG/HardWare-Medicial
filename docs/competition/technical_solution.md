# 医枢智疗 技术方案文档

队伍名称：**心脉智航队（PulsePilot）**

## 1. 项目简介
医枢智疗是一个面向真实医疗咨询与心电数据分析场景的多Agent智能系统。  
系统目标：
1. 提供多科室可解释问答能力。  
2. 在保证速度的前提下提升检索与生成质量。  
3. 将ECG数据自动转化为可交付的PDF专家报告。  
4. 支持多用户隔离，具备落地部署潜力。

---

## 2. 与评审标准的对应关系

### 2.1 技术维度（50%）

#### （1）创新性（20%）
1. 采用 LangGraph 多Agent工作流，将安全判断、路由、检索、生成拆分解耦。  
2. 提供“手动科室强制路由 + 自动路由”双模式，兼顾可控性和智能化。  
3. ECG流程形成“抓取-分析-生成-交付”闭环，支持波形+文字PDF输出。

#### （2）效率（15%）
1. 聊天链路采用SSE流式返回，降低首屏等待感。  
2. 关键能力可通过 `.env` 开关调优（联网搜索、QueryRewriter、轻量决策路径）。  
3. Chroma向量库采用持久化加载，减少重启重建成本。

#### （3）鲁棒性（15%）
1. 各Agent节点具备异常降级路径，避免流程崩溃。  
2. 检索失败、搜索失败、模型失败时均能回退到可用回答。  
3. ECG任务支持状态事件流和失败反馈，保证结果可追踪。

---

## 3. 系统架构

### 3.1 总体架构
1. 前端：React + Vite（中文化UI、SSE渲染、科室选择、ECG引导）。  
2. 后端：FastAPI（会话、流式聊天、ECG任务、鉴权）。  
3. Agent编排：LangGraph。  
4. 检索增强：ChromaDB + 医学知识库。  
5. 数据存储：SQLite（会话历史）、JSON（用户画像）、向量库持久化目录、ECG报告PDF目录。

### 3.2 Agent工作流（详细）
系统采用“单汇聚执行器（Executor）”设计，所有分支最终都汇聚到 `ExecutorAgent`，确保回答风格与安全策略一致。

标准工作流（LangGraph定义）：

`MemoryRead -> HealthConcierge(=KeywordRouter) -> [MedicalRouter / JudgeNeedRAG / QueryRewriter / Executor] -> Retriever -> Reranker -> Executor -> MemoryWriteAsync`

各节点职责如下：

1. `MemoryReadAgent`
- 读取最近会话历史、用户画像和长期记忆摘要。
- 初始化本轮 `AgentState`（tenant/user/session 隔离上下文）。

2. `HealthConciergeAgent (KeywordRouterAgent)`
- 做安全分级：`SAFE / CLARIFY / EMERGENCY`。
- 做领域判断（medical/general...）与是否优先用 RAG 的初判。
- 识别前端是否手动锁定科室（`selected_department_forced`）。

3. `MedicalRouterAgent`
- 仅在 medical 场景触发（且非强制科室时）。
- 输出主科室与检索范围：`primary_department`、`retrieval_scopes`、`routing_reason`。

4. `JudgeNeedRAGAgent`
- 在 `use_rag=False` 的情况下二次判断是否仍需检索（`need_rag`）。
- 避免“该检索未检索”与“过度检索”。

5. `QueryRewriterAgent`
- 生成更适配检索库的查询表达：`retrieval_query`。
- 支持规则重写或 LLM 重写（由 `.env` 开关控制）。

6. `RetrieverAgent + RerankerAgent`
- 按科室范围进行多库召回，聚合候选片段。
- 重排后生成最终 `rag_context` 供执行器引用。

7. `ExecutorAgent`
- 统一生成最终回答，执行工具决策与容错降级。
- 处理 ECG JSON 快捷 skill 分支（若用户消息中包含 ECG payload）。

8. `MemoryWriteAsyncAgent`
- 异步写回画像与长期记忆，不阻塞前端响应。

### 3.3 Agent路由决策过程（条件分支）
后端核心路由逻辑可归纳为以下规则：

1. 安全优先
- 若 `safety_level in {EMERGENCY, CLARIFY}`，直接进入 `Executor` 输出风险提示，不再走检索链路。

2. 手动科室优先
- 若 `selected_department_forced=true`，直接进入 `QueryRewriter -> Retriever -> Reranker -> Executor`。
- 检索范围强制限定到用户点击的科室知识库。

3. 医疗域自动路由
- 若 `domain=medical` 且未手动锁定科室，先走 `MedicalRouter` 确定科室范围，再决定是否检索。

4. 非强检索场景兜底
- 若 `use_rag=false`，进入 `JudgeNeedRAG`：
- `need_rag=true` 则补走检索链路；
- `need_rag=false` 则直达 `Executor`。

5. 非医疗域但需要检索
- 若 `domain!=medical` 且 `use_rag=true`，可直接进入 `QueryRewriter -> Retriever -> Reranker`。

### 3.4 在线流式执行路径（SSE）
在线接口 `/api/v1/chat/stream` 采用与主工作流对齐的“前置节点 + 流式执行器”模式：

1. 前置执行：`MemoryRead -> KeywordRouter`，按条件决定是否追加 `MedicalRouter / JudgeNeedRAG / QueryRewriter / Retriever / Reranker`。
2. 进入执行器计划阶段：`build_executor_plan`。
3. LLM 通过 `astream` 按 token 推送 `delta` 事件。
4. 结束后推送 `done`，并调用 `MemoryWriteAsync` 异步持久化。
5. 同时记录 `flow_trace`，用于可解释性展示和日志追踪。

---

## 4. 核心功能说明

### 4.1 多科室专业问答
1. 首页提供8个科室按钮（7个专业+general）。  
2. 用户点击后，检索仅在对应知识库进行。  
3. 用户不点击时，系统自动路由。

### 4.2 流式交互
1. 后端接口：`/api/v1/chat/stream`  
2. 通过SSE分段返回 `delta`，前端实时渲染。  
3. 结果完成后返回 `done`，实现完整流式体验。

### 4.3 ECG专家报告生成
1. 前端引导输入姓名、年龄、性别等基础信息。  
2. 系统按后端 `.env` 配置选择数据来源（网站抓取或模拟正常信号）。  
3. 数据标准化后进入报告生成链路。  
4. 输出ECG专家结论并生成PDF（波形图+文字报告+风险等级+免责声明）。

---

## 5. 性能与可配置化

### 5.1 关键环境变量
1. `WEB_SEARCH_ENABLED`：是否启用联网搜索。  
2. `WEB_SEARCH_USE_LLM_DECIDER`：联网决策是否走轻量模型。  
3. `QUERY_REWRITER_ENABLED`：是否启用QueryRewriter。  
4. `QUERY_REWRITER_USE_LLM`：QueryRewriter是否调用轻量模型。  
5. `OPENAI_WIRE_API`：`chat` 或 `responses` 协议切换。  

### 5.2 启动优化策略
1. 优先加载已持久化向量库。  
2. 仅在向量库缺失/无效时重建。  
3. 通过配置开关降低不必要的外部调用时延。

---

## 6. 鲁棒性设计
1. API边界做请求参数校验，避免脏数据进入流程。  
2. Agent内部统一异常捕获与日志记录，保证可观测。  
3. 模型不可用时回退固定提示，避免空响应。  
4. ECG失败路径返回明确状态信息，不阻塞主系统。

---

## 7. 人机交互与体验设计
1. 全中文UI与医疗语境文案，降低使用门槛。  
2. 科室选择显式化，支持“锁定科室/自动路由”切换。  
3. 流式输出提升感知速度。  
4. 对话导出与PDF报告交付提升实际可用性。

---

## 8. 应用价值
1. 可用于门诊前置咨询与分诊辅助。  
2. 可用于慢病随访中的连续问答与健康建议。  
3. 可用于可穿戴/监护设备ECG结果快速解读与报告自动化。  
4. 具备多用户隔离能力，满足团队试用与演示部署。

---

## 9. Demo展示设计（与视频对应）
1. 专业科室强制路由演示。  
2. 自动路由+SSE流式演示。  
3. ECG一键生成PDF报告演示。  
4. 多用户隔离演示。  
5. 后台日志作为流程可解释性证据。

---

## 10. 后续计划
1. 扩展科室知识库规模与质量评估。  
2. 增加结构化评测指标（准确率、召回率、幻觉率、时延）。  
3. 完善权限、审计和隐私合规能力。  
4. 增强报告模板可配置能力，支持更多设备类型。

---

## 11. 团队信息
1. 队伍名称：**心脉智航队（PulsePilot）**
2. 队伍成员：
- ElonGe（工程实现 / 架构整合）
  GitHub: https://github.com/PacemakerG
- xhforever（协同开发 / 功能迭代）
  GitHub: https://github.com/xhforever
3. 项目地址：
- 主仓库: https://github.com/PacemakerG/HardWare-Medicial
- 协作仓库: https://github.com/xhforever/HardWare-Medicial
---

## 12. 提交说明（建议）
1. 文档命名：`医枢智疗队_技术方案文档.md`
2. 视频命名：`医枢智疗队_Demo视频.mp4`  
3. 邮件主题：`AI Agent大赛报名+医枢智疗队`  
4. 收件邮箱：`elon2ge@gmail`
