# AGENTS.md — MediGenius 开发者指南

本文件面向在此仓库中工作的 AI 编程代理。
更多项目背景和当前阶段状态请参见 `CLAUDE.md`。

---

## 项目概述

MediGenius 是一款个人医疗 AI 助手，包含以下功能：
- 日常医学问答（LangGraph RAG + LLM + 可选联网搜索）
- 结构化心电图参数分析，生成中文专业报告

技术栈：Python/FastAPI 后端、React/Vite 前端、LangGraph 工作流、ChromaDB RAG、SQLite 聊天记录。

---

## 构建 / 代码检查 / 测试命令

### 全栈启动

```bash
# 同时启动后端（端口 8000）和前端（端口 5173+）
python run.py
```

### 后端（Python）

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 运行全部测试
pytest -v

# 运行单个测试文件
pytest tests/test_agents.py -v

# 运行单个测试函数
pytest tests/test_agents.py::test_memory_read_agent -v

# 显示标准输出（print 内容）
pytest tests/test_agents.py::test_executor_agent_with_docs -v -s

# 带覆盖率运行
pytest --cov=app -v
pytest --cov=app --cov-report=html

# 代码检查与格式化
black .
isort .
flake8 .
```

也可从项目根目录运行测试：
```bash
pytest backend/tests/test_agents.py::test_memory_read_agent -v
```

### 前端（Node/Vite）

```bash
cd frontend

npm install         # 安装依赖
npm run dev         # 开发服务器（端口 5173）
npm run build       # 生产构建 → dist/
npm run lint        # ESLint 检查
npm run preview     # 预览生产构建

# 测试（Vitest）
npm test                                  # 单次运行（无监听）
npx vitest                                # 监听模式
npx vitest run src/App.test.jsx           # 运行单个测试文件
npx vitest run --coverage                 # 带覆盖率
```

---

## 架构

### LangGraph 工作流（单汇聚节点模式）

```
MemoryReadAgent → KeywordRouterAgent
    ├─[use_rag=True]──► RetrieverAgent ────────────────────┐
    └─[use_rag=False]─► JudgeNeedRAGAgent                  │
                            ├─[need_rag=True]──► RAG ──────┤
                            └─[need_rag=False]─────────────┤
                                                           ▼
                                                   ExecutorAgent
                                                         │
                                                 MemoryWriteAsyncAgent
                                                         │
                                                        END
```

所有 Agent 节点函数签名为 `(state: AgentState) -> AgentState`。
节点通过函数引用注册：`workflow.add_node("executor", ExecutorAgent)`。

### 核心目录结构

```
backend/app/
├── agents/         # LangGraph 节点函数（PascalCase 命名）
├── api/v1/         # FastAPI 路由和接口处理
├── core/           # 配置、状态定义、工作流图、日志
├── services/       # 业务逻辑（类单例）
├── tools/          # LLM 客户端、向量存储、搜索工具
├── schemas/        # Pydantic 请求/响应模型
├── models/         # SQLAlchemy ORM 模型
└── db/             # SQLAlchemy 会话工厂

frontend/src/
└── App.jsx         # 单体 React 应用（组件内联定义）

backend/storage/
├── profiles/       # 按会话存储的 JSON 用户画像
├── chat_db/        # SQLite 数据库
├── vector_store/   # ChromaDB 向量嵌入
└── ecg_reports/    # 生成的 PDF 报告
```

---

## Python 代码风格

### 导入规范

使用 `isort`（profile = `"black"`）。顺序：
1. 标准库（`import os`、`import json`、`import threading`）
2. 第三方库（`from fastapi import ...`、`from langchain_core import ...`）
3. 本地模块（`from app.core.config import ...`、`from app.core.logging_config import logger`）

在函数内部使用延迟导入，以避免循环导入或减少启动开销：
```python
def get_llm():
    from langchain_openai import ChatOpenAI   # 延迟导入
    ...
```

### 格式化

- `black`：`line-length = 88`，`target-version = ['py310']`
- `flake8`：`max-line-length = 140`（允许较长的提示词/关键词列表不报错）
- 忽略 `E203`、`W503`（兼容 black）；`__init__.py` 中忽略 `F401`
- 使用 `# ── 段落名称 ─────` 注释横幅在文件内分隔逻辑区域

### 命名规范

| 模式 | 用途 |
|---|---|
| `snake_case` | 函数、变量、模块级路径/配置常量 |
| `UPPER_SNAKE_CASE` | 真常量（`MAX_TOOL_CALLS`、`HIGH_RISK_KEYWORDS`、`LOG_DIR`） |
| `PascalCase` | 类和 Agent 节点函数（`ExecutorAgent`、`ChatService`） |
| `_单下划线前缀` | 模块私有辅助函数（`_extract_json_block`、`_atomic_save_profile`） |
| `_双下划线前缀` | 模块级单例，不对外导出（`_llm_instance`、`_vectorstore`） |

Agent 节点函数使用 `PascalCase`，因为 LangGraph 通过函数引用注册为命名节点。
向后兼容别名写法：`PlannerAgent = KeywordRouterAgent`。

### 类型注解

- `AgentState` 使用 `TypedDict`
- 所有 API schema 使用 `Pydantic BaseModel` 配合显式 `Field` 校验器
- 所有函数标注返回类型：`-> str`、`-> AgentState`、`-> Dict[str, Any]`
- 代码中同时存在 `Optional[str]` 和 `str | None` 两种写法；为保持一致性，优先使用 `Optional`

### 错误处理

**绝不向上抛出异常导致工作流崩溃。** 始终记录日志并返回降级但有效的状态：

```python
try:
    response = llm.invoke(prompt)
    answer = response.content.strip()
except Exception as exc:
    logger.error("Executor: LLM 生成失败: %s", exc)
    answer = "服务暂时不可用，请稍后再试。"
    state["llm_success"] = False
```

使用可选资源前先做 `None` 检查：
```python
llm = get_llm()
if not llm:
    state["generation"] = "当前医疗助手服务暂时不可用..."
    return state
```

用户画像持久化使用 `threading.Lock` + 原子文件写入：
```python
with _profile_lock:
    profile = load_profile(session_id)
    _atomic_save_profile(session_id, profile)   # 先写 .tmp 再 os.replace()
```

在 API 边界抛出 `HTTPException`；内部吞掉错误：
```python
if not chat_service.workflow_app:
    raise HTTPException(status_code=503, detail="System not initialized")
```

### 单例模式

所有昂贵资源（LLM 客户端、向量存储）使用模块级 `None` 单例，首次调用时懒加载：
```python
_llm_instance = None

def get_llm():
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatOpenAI(...)
    return _llm_instance
```

所有服务在模块级创建类实例，作为单例导入：
```python
chat_service = ChatService()   # 模块底部
```

### 异步处理

后台用户画像更新使用守护线程（而非 `asyncio.create_task`），避免阻塞响应：
```python
thread = threading.Thread(target=_worker, daemon=True)
thread.start()
```

异步工作流调用始终提供同步回退：
```python
try:
    result = await self.workflow_app.ainvoke(state)
except AttributeError:
    result = self.workflow_app.invoke(state)
```

---

## JavaScript / JSX 代码风格

### 命名规范

| 模式 | 用途 |
|---|---|
| `camelCase` | 变量、函数、状态、事件处理器（`sidebarOpen`、`handleKeyDown`） |
| `PascalCase` | React 组件（`App`、`Sidebar`、`MessageBubble`） |
| `UPPER_SNAKE_CASE` | 模块级常量（`API_BASE`、`QUICK_QUESTIONS`） |
| `camelCase` | Props（`onNewChat`、`onLoadSession`、`isTyping`） |

### 组件结构

子组件以具名函数形式定义在默认导出之上。Hooks 放在每个组件顶部。所有事件处理器和回调使用 `useCallback` 包裹。

### 错误处理

所有网络请求使用 `try/catch/finally`。`finally` 中始终重置加载状态。显示用户可见的错误提示，不允许静默失败：

```javascript
try {
    const res = await fetch(`${API_BASE}/chat`, { ... });
    const data = await res.json();
    ...
} catch {
    showToast('连接错误', 'error');
    setMessages(prev => [...prev, errorMsg]);
} finally {
    setIsTyping(false);   // 始终清理加载状态
}
```

对于真正的静默降级场景，允许空 `catch` 块（不绑定变量）：
```javascript
try { ... } catch { setSessions([]); }
```

### 代码检查

ESLint v9 扁平配置（`eslint.config.js`）。关键规则：`no-unused-vars` 允许 `^[A-Z_]`（UPPER_SNAKE_CASE 常量）。无 Prettier 配置，格式化未自动化。

---

## 测试规范

### 后端

测试使用 `unittest.mock.patch` 和 `MagicMock`。**始终在被测模块的导入位置打补丁**（如 `app.agents.executor.get_llm`，而非 `app.tools.llm_client.get_llm`）。

```python
def test_executor_with_rag():
    state = initialize_conversation_state()
    state["question"] = "What is X?"
    state["rag_context"] = [{"content": "X is Y."}]

    with patch('app.agents.executor.get_llm') as mock_get_llm, \
         patch('app.agents.executor._decide_web_search', return_value=(False, "")):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.content = "根据资料，X 与 Y 相关。"
        mock_get_llm.return_value = mock_llm

        result = ExecutorAgent(state)
        assert "Y" in result["generation"]
```

每个测试文件顶部通过 `sys.path.insert(0, ...)` 添加 `backend/` 到路径。异步测试使用 `pytest-asyncio`（`asyncio_mode = auto`），无需显式标注 `@pytest.mark.asyncio`。

### 前端

使用 Vitest + Testing Library。Mock 配置在 `src/setupTests.js` 中。

---

## 环境变量

运行前需将 `backend/.env.example` 复制为 `backend/.env`。

| 变量 | 是否必填 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | 是 | LLM API 密钥 |
| `OPENAI_BASE_URL` | 是 | LLM 基础 URL |
| `LLM_MODEL` | 是 | 主模型（默认：`gpt-4o-mini`） |
| `LIGHT_LLM_MODEL` | 否 | 用于路由的轻量模型 |
| `TAVILY_API_KEY` | 否 | 联网搜索（缺失则禁用） |
| `EMBEDDING_MODEL_NAME` | 否 | RAG 嵌入模型 |
| `RAG_ENABLED` | 否 | 启用/禁用 RAG（默认：`true`） |
| `ECG_SITE_URL` | 否 | 远程心电监护站点 |
| `ECG_SITE_USER` | 否 | 心电站点用户名 |
| `ECG_SITE_PASS` | 否 | 心电站点密码 |

---

## 语言与语气（AI 回复）

- 所有 LLM 回复默认使用**简体中文**
- 语气根据用户画像偏好进行个性化调整
- 医疗建议措辞谨慎；高风险关键词触发紧急提示
- 回复末尾始终附带一个主动的追问问题

---

## 重要约束

- **工具调用预算：** 每次查询最多 2 次工具调用；同一工具最多重复 1 次
- **记忆写入** 为异步/后台操作——失败仅记录日志，不阻塞响应
- **RAG 初始化失败** 在启动时被吞掉；服务器在无 RAG 的情况下继续运行
- **心电报告** 可通过在用户消息中嵌入 `{"ecg": {...}}` JSON 块触发
- 后端端口 8000 被占用时启动失败；前端从 5173 开始自动递增
