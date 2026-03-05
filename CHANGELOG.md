# 架构更新与变更日志 (Changelog)

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
