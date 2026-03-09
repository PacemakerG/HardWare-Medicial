# 架构更新与变更日志 (Changelog)

## 2026-03-08: ECG 引导式监听闭环（前端按钮 + 后端后台任务）

### 1. 新增 ECG 监听任务服务
- **修改文件:** `backend/app/services/ecg_monitor_service.py`, `backend/app/core/config.py`, `backend/app/schemas/ecg.py`
- **变更内容:** 新增后台任务管理，支持登录医生站点、监听新 ECG 记录、自动下载 XLS、解析并接入 ECG 报告生成。
- **设计初衷:** 将“手动上传 JSON”改为“用户填基础信息后自动监听并生成报告”的闭环流程。

### 2. ECG API 扩展
- **修改文件:** `backend/app/api/v1/endpoints/ecg.py`
- **变更内容:** 新增接口：
  - `POST /api/v1/ecg/monitor/start`
  - `GET /api/v1/ecg/monitor/{task_id}`
- **设计初衷:** 支持前端异步启动监听任务并轮询状态。

### 3. 前端交互改造
- **修改文件:** `frontend/src/App.jsx`, `frontend/src/index.css`
- **变更内容:** 将输入区按钮改为 ECG 引导入口，新增基础信息弹窗与任务轮询，任务完成后自动回填 ECG 专家报告到聊天区。
- **设计初衷:** 让用户无需手动拼 JSON 文件，按流程操作即可获得报告。

### 4. 测试更新
- **修改文件:** `backend/tests/test_ecg_api.py`
- **变更内容:** 增加监听任务启动与状态查询接口测试。
- **设计初衷:** 保证新增 API 的可回归性。

### 5. 监听超时兜底与 I/O 契约对齐
- **修改文件:** `backend/app/services/ecg_monitor_service.py`, `backend/app/schemas/ecg.py`, `backend/tests/test_ecg_monitor_service.py`
- **变更内容:** 监听窗口固定为 60 秒；超时后不报错，自动使用当前最新一条 ECG；新增 `llm_input/llm_output` 字段并保证输出仅比输入多 `report`。
- **设计初衷:** 降低等待失败率并统一模型输入输出数据结构。

### 6. Phase 1: ECG PDF 报告（波形 + 文字）
- **修改文件:** `backend/app/services/ecg_pdf_service.py`, `backend/app/services/ecg_report_service.py`, `backend/app/api/v1/endpoints/ecg.py`, `backend/app/schemas/ecg.py`, `frontend/src/App.jsx`
- **变更内容:** 新增 PDF 生成能力，输出 Lead II 波形图 + 结构化文字报告；新增 `GET /api/v1/ecg/report/{report_id}/pdf`；响应增加 `pdf_url`。
- **设计初衷:** 提供可归档和可下载的医学报告载体，替代仅文本回传。

## 2026-03-08: Memory 偏好驱动的个性化表达（Phase H 子项）

### 1. Executor 接入结构化用户偏好
- **修改文件:** `backend/app/core/state.py`, `backend/app/agents/memory.py`, `backend/app/agents/executor.py`
- **变更内容:** 新增 `user_preferences` 状态字段；`MemoryReadAgent` 读取画像后注入偏好；`ExecutorAgent` 在系统提示词中显式加入“称呼/语气/详略”约束。
- **设计初衷:** 让回答风格可由长期画像稳定控制，而不是仅依赖模型随机发挥。

### 2. 偏好 schema 扩展
- **修改文件:** `backend/app/services/profile_service.py`
- **变更内容:** `preferences` 新增 `preferred_name`、`detail_level`（`brief | balanced | detailed`）。
- **设计初衷:** 支持“称呼”和“详细程度”两类长期偏好可持久化写入与读取。

### 3. 后处理追问模板个性化
- **修改文件:** `backend/app/agents/executor.py`
- **变更内容:** 回答末尾自动追问在可用时带上偏好称呼（如“王女士，…”），并保持高风险急诊提醒逻辑不变。
- **设计初衷:** 提升连续对话的“个人助手感”，同时不削弱安全边界。

### 4. 新增/更新测试
- **修改文件:** `backend/tests/test_agents.py`, `backend/tests/test_profile_service.py`
- **变更内容:** 增加 Memory 偏好注入测试、Executor 个性化提示词测试、称呼追问测试，并补充 profile 偏好字段归一化与持久化测试。
- **设计初衷:** 保证二开能力可回归、可维护。

## 2026-03-05: RAG 检索链路“自信心质检”与智能路由增强

### 1. 引入专属轻量级 LLM (Lightweight LLM)
- **修改文件:** `backend/app/tools/llm_client.py`
- **变更内容:** 新增了 `get_light_llm()` 函数，专门调用阿里云的 `qwen-turbo-latest` 模型。
- **设计初衷:** 将 `temperature` 设定为 `0.0`，`max_tokens` 设定为 `50`。作为“判卷官”，该小模型能够在极短的时间内、以极低的成本提供绝对理性、稳定的 YES/NO 二元判断，避免大模型幻觉。

### 2. 检索环节拦截与“自信心质检”
- **修改文件:** `backend/app/agents/retriever.py`
- **变更内容:** 在从向量数据库查找到初步文档后，介入大模型判卷机制。
- **设计初衷:** 将用户问题与检索到的本地文档组装为严格的 Prompt 交给轻量级 LLM 评估。如果判断结果不包含 `YES`（即文档不足以回答问题），则强行拦截并清空文档列表 (`valid_docs = []`)，同时标记 `rag_success = False`，拒绝使用无关的本地文档强行回答。

### 3. LangGraph 动态路由重定向
- **修改文件:** `backend/app/agents/retriever.py` & `backend/app/core/langgraph_workflow.py`
- **变更内容:** 依托原有的 `_route_after_rag` LangGraph 条件路由自动生效。
- **设计初衷:** 当 retriever 节点的 `rag_success` 因自信心不足被置为 `False` 时，工作流会自动跳转到 `llm_agent` 节点。让主干大模型依靠其强大的预训练知识库直接尝试作答，实现无缝兜底。

### 4. 修复潜藏的路由死循环Bug
- **修改文件:** `backend/app/core/langgraph_workflow.py`
- **变更内容:** 修正了 `_route_after_llm` 退路（Fallback）的指向，将其从 `retriever` 明确改为 `wikipedia`。
- **设计初衷:** 防止出现“检索失败 -> 推给主模型 -> 主模型失败 -> 退回给检索 -> 再次推给主模型”的互相踢皮球死循环。确保工作流在主模型自我解释失败后，能够单向、健康地推进到外部百科搜索等下一级兜底工具。

### 5. 多语言关键词扩展 (Multilingual Keyword Expansion)
- **修改文件:** `backend/app/agents/planner.py`
- **变更内容:** 将原来的纯英文医疗关键词列表扩展为中英双语对照列表。
- **设计初衷:** 确保系统能够同时识别中英文的医疗症状、疾病和术语，从而在全球化语境（尤其是中文提问）下也能准确触发 RAG 检索流程，提高系统的实用性。
