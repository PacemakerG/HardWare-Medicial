# Flow Trace Record

用于记录每次提问，以及该问题在后端工作流中实际经过的节点。

说明：
- 该文档会在每次调用聊天接口时由后端自动追加一条记录。
- 机器可读副本会同时写入 `docs/flow-trace-record.jsonl`。

## 字段说明

| 字段 | 说明 |
| --- | --- |
| `timestamp` | 提问时间 |
| `session_id` | 会话 ID |
| `question` | 用户提问原文 |
| `flow_trace` | 流程追踪字段，建议使用节点数组，例如 `["memory_read", "health_concierge", "rag", "executor", "memory_write_async"]` |
| `source` | 最终响应来源，例如 `Safety Guard`、`Medical Literature Database`、`Fitness AI Coach` |
| `notes` | 补充观察，例如 `触发了 CLARIFY`、`未命中 RAG` |

## 记录模板

```json
{
  "timestamp": "",
  "session_id": "",
  "question": "",
  "flow_trace": [],
  "source": "",
  "notes": ""
}
```

## 记录示例

```json
[
  {
    "timestamp": "2026-03-07 16:00:00",
    "session_id": "test-session-001",
    "question": "我最近跑步后心率有点高，怎么调整训练强度？",
    "flow_trace": [
      "memory_read",
      "health_concierge",
      "rag",
      "executor",
      "memory_write_async"
    ],
    "source": "Fitness Database",
    "notes": "domain=fitness, use_rag=True"
  },
  {
    "timestamp": "2026-03-07 16:05:00",
    "session_id": "test-session-002",
    "question": "我现在胸痛还有点呼吸困难，怎么办？",
    "flow_trace": [
      "memory_read",
      "health_concierge",
      "executor",
      "memory_write_async"
    ],
    "source": "Safety Guard",
    "notes": "safety_level=EMERGENCY"
  }
]
```

## 测试记录

| timestamp | session_id | question | flow_trace | source | notes |
| --- | --- | --- | --- | --- | --- |
| 2026-03-07 16:03:23 | trace-test-001 | hello | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, use_rag=False, need_rag=False |
| 2026-03-07 16:06:09 | 0d446a11-e75e-4ed2-8adf-ff8b02183c9f | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, use_rag=False, need_rag=False |
| 2026-03-07 16:06:19 | 0d446a11-e75e-4ed2-8adf-ff8b02183c9f | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, use_rag=False, need_rag=False |
| 2026-03-07 16:13:34 | trace-test-greeting-fix | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, use_rag=False, need_rag=False |
| 2026-03-07 16:14:05 | 30690947-1cb6-43b4-9698-c58ca4ed7b32 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, use_rag=False, need_rag=False |
| 2026-03-07 16:14:20 | 30690947-1cb6-43b4-9698-c58ca4ed7b32 | 睡眠问题 | `["memory_read", "health_concierge", "rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=sleep, use_rag=True, need_rag=False |
| 2026-03-07 16:23:23 | conda-env-check-001 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, use_rag=False, need_rag=False |
| 2026-03-07 16:28:20 | qwen-config-check-001 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, use_rag=False, need_rag=False |
| 2026-03-07 16:29:40 | 30690947-1cb6-43b4-9698-c58ca4ed7b32 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, use_rag=False, need_rag=False |
| 2026-03-07 16:33:02 | 30690947-1cb6-43b4-9698-c58ca4ed7b32 | 我今天睡眠不是很好，半夜老醒 | `["memory_read", "health_concierge", "rag", "executor", "memory_write_async"]` | Sleep AI Coach | safety_level=SAFE, domain=sleep, use_rag=True, need_rag=False |
| 2026-03-07 16:34:55 | 30690947-1cb6-43b4-9698-c58ca4ed7b32 | 我肚子好痛怎么办 | `["memory_read", "health_concierge", "executor", "memory_write_async"]` | Safety Clarification | safety_level=CLARIFY, domain=general, use_rag=False, need_rag=False |
| 2026-03-07 16:36:31 | 30690947-1cb6-43b4-9698-c58ca4ed7b32 | 两个小时了，很难受 | `["memory_read", "health_concierge", "rag", "executor", "memory_write_async"]` | Medical AI Coach | safety_level=SAFE, domain=medical, use_rag=True, need_rag=False |
| 2026-03-08 14:56:19 | 68de1802-39a3-46b3-9bc9-efa5f776d209 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-08 14:56:28 | 68de1802-39a3-46b3-9bc9-efa5f776d209 | 肚子不舒服 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-08 14:57:08 | ae041318-b48a-4532-bcd5-4ef4cb12f6f1 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-08 14:59:22 | 68de1802-39a3-46b3-9bc9-efa5f776d209 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-08 15:08:52 | 8095ce7f-a7af-47af-bae3-8f89028900c9 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-08 15:12:28 | 7dc6d512-81fc-4653-9bb4-297f398c32d2 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-08 15:14:22 | 7dc6d512-81fc-4653-9bb4-297f398c32d2 | 肚子不舒服 | `["memory_read", "health_concierge", "medical_router", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | Medical AI Coach | safety_level=SAFE, domain=medical, primary_department=gastroenterology, use_rag=True, need_rag=False |
| 2026-03-08 15:23:00 | 7dc6d512-81fc-4653-9bb4-297f398c32d2 | 小孩子肚子不舒服 | `["memory_read", "health_concierge", "medical_router", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | Current Medical Research & News | safety_level=SAFE, domain=medical, primary_department=pediatrics, use_rag=True, need_rag=False |
| 2026-03-08 15:33:28 | 06d8e936-fa7c-4afd-9a91-9c92a2b94738 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-08 15:36:55 | 06d8e936-fa7c-4afd-9a91-9c92a2b94738 | 小孩子肚子不舒服 | `["memory_read", "health_concierge", "medical_router", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | Current Medical Research & News | safety_level=SAFE, domain=medical, primary_department=pediatrics, use_rag=True, need_rag=False |
| 2026-03-09 07:58:24 | c9844aa7-4a9b-43fb-9e66-0e363d2cb758 | Hello AI | `[]` | Mock Brain | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 07:58:24 | test-session | Hello | `[]` | Test Source | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 07:58:24 | test-session | Hello | `[]` | Test Source | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 07:58:24 | test-session | Hello | `[]` | Sync Source | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 08:19:11 | 60928150-0f56-46a2-85fb-476926a00d5e | 我上次有哪里不舒服你还记得吗 | `["memory_read", "health_concierge", "medical_router", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | Medical AI Coach | safety_level=SAFE, domain=medical, primary_department=general_surgery, use_rag=True, need_rag=False |
