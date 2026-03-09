# HardWare-Medicial

一个面向个人医疗场景的智能助手项目，当前聚焦两条主线：

1. 日常医疗问答（RAG + LLM + 可选联网检索）
2. ECG 结构化参数生成专业中文报告（Skill 化能力）

项目目标是把“聊天问答 + 生理信号分析 + 长期用户记忆”整合成可持续迭代的个人医疗助手。

## 1. 项目现状（2026-03-08）

- 后端：FastAPI + LangGraph 工作流，核心链路已重构为单一收口 Executor。
- 前端：React + Vite，支持聊天与 ECG 引导式采集（基础信息 -> 自动监听站点 -> 报告回填）。
- 记忆：JSON 用户画像（非向量记忆），支持读写与异步更新。
- ECG Skill：已提供 API，支持生成/查询报告，并写回用户画像摘要。
- 运行入口：根目录 `python run.py` 一键拉起前后端。

当前主工作流（已落地）：

`MemoryRead -> KeywordRouter -> (RAG | JudgeNeedRAG) -> Executor -> MemoryWriteAsync`

说明：
- 所有主链路最终都进入 `ExecutorAgent`。
- `RAG` 节点只负责检索，不做“是否足够回答”决策。
- `Executor` 内部按需触发工具（如 WebSearch），并有停止条件避免循环。

## 2. 项目结构

```text
HardWare-Medicial/
├── backend/                       # FastAPI + LangGraph + 数据存储
│   ├── app/
│   │   ├── agents/                # memory / router / judge / rag / executor
│   │   ├── api/v1/endpoints/      # chat / session / ecg / health
│   │   ├── core/                  # workflow / config / state / logging
│   │   ├── schemas/               # Pydantic 请求响应定义
│   │   ├── services/              # chat / profile / ecg_report / database
│   │   └── tools/                 # llm / tavily / vector store / search tools
│   ├── storage/                   # db、vector_store、profiles（运行时）
│   ├── data/medical_book.pdf      # RAG 语料
│   └── .env.example               # 环境变量示例
├── frontend/                      # React 聊天界面（含 ECG 引导入口）
├── hardware/                      # 设备/云端数据抓取与 XLS->JSON 指标计算脚本
├── showcase/                      # ECG 样例输入与报告样例
├── docs/todolist-agent-routing-refactor.md
└── run.py                         # 一键启动脚本（后端健康检查 + 前端端口自适应）
```

## 3. 关键模块说明

### 3.1 路由与 Agent 职责

- `MemoryReadAgent`：读取 `storage/profiles/{session_id}.json`，拼接 `memory_context`
- `KeywordRouterAgent`：关键词命中直接走 RAG
- `JudgeNeedRAGAgent`：未命中时做二元判定（是否需要 RAG）
- `RetrieverAgent`：只做检索，输出 `rag_context`
- `ExecutorAgent`：唯一收口，融合 `query + memory + rag`，必要时调用 WebSearch
- `MemoryWriteAsyncAgent`：在回答完成后异步更新用户画像

### 3.2 记忆系统（Memory）

已实现轻量 JSON 画像（结构化、可持续）：

- `basic_info`: 年龄、性别、身高、体重
- `preferences`: 语言偏好、沟通风格
- `current_context`: 症状、用药、最近检查、最近 ECG 摘要等

存储位置：
- `backend/storage/profiles/*.json`

特性：
- 原子写入（防止文件损坏）
- schema 约束与类型归一化
- 异步写回（不阻塞首字响应）

### 3.3 ECG Skill（报告生成）

API：
- `POST /api/v1/ecg/report`：根据结构化参数生成 ECG 报告
- `GET /api/v1/ecg/report/{report_id}`：按 ID 查询历史报告
- `GET /api/v1/ecg/report/{report_id}/pdf`：下载 ECG PDF 报告（含波形 + 文字）
- `POST /api/v1/ecg/monitor/start`：启动“监听医生站点新数据并自动出报告”任务
- `GET /api/v1/ecg/monitor/{task_id}`：查询监听任务状态与最终报告

能力：
- 风险分层（low/medium/high）
- 高危强提醒（急诊阈值）
- 免责声明注入
- 报告摘要写回 Memory，支持后续对话引用
- 监听模式默认 60 秒：若 60 秒内无新上传，自动改用最新一条数据继续出报告
- 监听状态返回 `llm_input` / `llm_output`，两者结构对齐，仅 `llm_output` 额外包含 `report`

### 3.4 硬件侧数据流水线

脚本：
- `hardware/fetch_latest_ecg_and_convert.py`

目标流程：
1. 登录云端站点并拉取最新 ECG 记录
2. 下载 `.xls` 心电数据到 `hardware/ECGdata/`
3. 解析信号并计算关键指标（不保留原始 waveform/lead_stats）
4. 生成可直接喂给 ECG Skill/LLM 的 JSON
5. 若年龄/身高/体重等缺失，生成 `manual_input_template.json` 供人工补齐

## 4. 环境与运行

### 4.1 Conda 环境

```bash
conda activate medigenius
```

### 4.2 配置环境变量

建议先复制：

```bash
cp backend/.env.example backend/.env
```

核心变量（OpenAI 兼容）：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `LLM_MODEL`
- `LIGHT_LLM_MODEL`
- `TAVILY_API_KEY`（可选；不配则禁用 WebSearch）
- `ECG_SITE_URL` / `ECG_SITE_USER` / `ECG_SITE_PASS`（ECG 站点监听登录）

### 4.3 一键启动

在项目根目录：

```bash
python run.py
```

说明：
- 后端固定默认 `8000`，若占用会直接报错并退出
- 前端默认 `5173`，若占用会自动尝试 `5174/5175...`

## 5. 对外 API（当前）

- `GET /api/v1/health`
- `POST /api/v1/chat`
- `GET /api/v1/sessions`
- `GET /api/v1/history`
- `GET /api/v1/session/{session_id}`
- `POST /api/v1/ecg/report`
- `GET /api/v1/ecg/report/{report_id}`
- `GET /api/v1/ecg/report/{report_id}/pdf`
- `POST /api/v1/ecg/monitor/start`
- `GET /api/v1/ecg/monitor/{task_id}`

## 6. 下一步计划（执行优先级）

1. 完成 Executor 流式输出与工具策略细化（Phase E 收尾）
2. 完成全量回归测试稳定化（Phase G，解决超时与边界用例）
3. 优化“前端引导采集 -> 云端自动抓取 -> 本地计算 -> 一键生成报告”的闭环稳定性
4. 增加 ECG Skill 的可观测性（日志追踪、失败分类、重试策略）
5. 记忆个性化升级：从 `preferences` 精细控制语气/详略，而不影响医学严谨性
6. 为后续 skill 扩展预留统一 function-calling 协议层

详细任务清单见：
- `docs/todolist-agent-routing-refactor.md`

## 7. 整体愿景

这个项目的长期目标不是“问答机器人”，而是“个人医疗操作系统”：

- 前端像有温度的健康助手，能主动引导下一步
- 后端像可靠调度中枢，保证路由可控、响应稳定
- 记忆像可维护用户画像，持续积累长期健康上下文
- 技能层（Skill）可插拔，逐步覆盖 ECG、用药、随访、报告生成等场景

最终形态是：从“信息咨询”升级为“数据驱动 + 连续跟踪 + 可执行建议”的个人医疗助手。

## 8. 换账号/新会话交接清单

当你切换到新账号后，按下面步骤即可无缝接手：

1. 先读本 README（现状、架构、运行、路线图）
2. 再读 `docs/todolist-agent-routing-refactor.md`（任务细项与阶段状态）
3. `conda activate medigenius`
4. 检查 `backend/.env`（模型与 API key）
5. `python run.py` 启动并手测：
   - 普通聊天
   - RAG 命中问题
   - ECG 引导式监听生成报告
6. 从 `Phase E/G` 继续推进（Executor 策略 + 全量回归）


给新的agent的prompt
你现在接管项目 /home/elon/workspace/HardWare-Medicial，请严格按以下要求继续开发：

  1. 先阅读并理解这两个文档
  - README.md（项目总览、结构、运行、愿景、交接说明）
  - docs/todolist-agent-routing-refactor.md（当前改造阶段与待办）

  2. 当前代码基线
  - 分支：feat/agent-routing-ecg-skill
  - 最新提交：e4ca622 (docs: add root README for project handover and roadmap)
  - 已完成主流程：MemoryRead -> KeywordRouter -> (RAG | JudgeNeedRAG) -> Executor ->
  MemoryWriteAsync
  - ECG Skill 已实现：
    - POST /api/v1/ecg/report
    - GET /api/v1/ecg/report/{report_id}
  - 硬件脚本已实现：
    - hardware/fetch_latest_ecg_and_convert.py
    - 能从云端抓最新记录、下载 xls、计算关键指标并生成 JSON（含 manual input 模板）

  3. 运行方式
  - conda activate medigenius
  - 在仓库根目录运行：python run.py
  - 后端默认 8000，前端默认 5173（前端端口会自动顺延）

  4. 配置约束
  - 使用 OpenAI-compatible API 配置（见 backend/.env）
  - WebSearch 依赖 TAVILY_API_KEY
  - 不要把运行时产物提交到 git（如 backend/logs、backend/storage 下数据库/向量库等）

  5. 当前优先任务（按顺序）
  - 收尾 Phase E：Executor 的工具调用策略与停止条件继续细化（避免循环、失败可降级）
  - 推进 Phase G：补齐/修复全量测试回归（重点路由分支与 ECG 相关路径）
  - 打通“前端引导采集 -> 云端自动抓取 -> 本地计算 -> 生成 ECG 报告”完整闭环体验
  - 检查 ECG 输入 JSON 与目标报告风格字段的一致性，保持结构稳定

  6. 交付要求
  - 每次改动先说明计划，再实施，再跑测试
  - 汇报时给出：改动文件、关键逻辑、测试结果、剩余风险
  - 所有回答默认中文，简洁直接
