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
| 2026-03-09 20:00:43 | fea999e7-2b78-487b-a805-5c3af7a66c67 | Hello AI | `[]` | Mock Brain | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:01:57 | e860cbdb-57e7-4181-b962-50d33338bc7c | Hello stream | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:01:57 | test-session | Hello | `[]` | Test Source | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:01:57 | test-session | Hello | `[]` | Test Source | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:01:57 | test-session | Hello | `[]` | Sync Source | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:01:57 | test-session | Hello | `[]` | Mock Brain | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:04:43 | e71e3bf9-d7e2-4625-8d5e-c05791ba0f06 | Hello AI | `[]` | Mock Brain | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:04:43 | test-session | Hello | `[]` | Test Source | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:04:43 | test-session | Hello | `[]` | Test Source | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:04:43 | test-session | Hello | `[]` | Sync Source | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:04:43 | test-session | Hello | `[]` | Mock Brain | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:06:15 | e142b920-6cf8-4df2-872e-1fa189cb4e53 | Hello stream | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:15:18 | 0f912b1c-ffde-45b4-9605-5179bb785b9c | hello | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:46:09 | 7ab61604-e9fc-44ab-8961-872e3c7f21a1 | Hello AI | `[]` | Mock Brain | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:47:43 | 66e7c695-d248-47ac-8a6f-07b620e741d8 | Hello stream | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:50:11 | 7220d62d-962d-44e8-923f-19037b4f782a | Hello AI | `[]` | Mock Brain | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:51:46 | 19576b20-b410-47af-8ce5-69cf5fa177c5 | Hello stream | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 20:52:51 | 67622e4d-defe-4921-8647-f6d52c1ad3c2 | Common cold remedies | `["memory_read", "health_concierge", "medical_router", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | Current Medical Research & News | safety_level=SAFE, domain=medical, primary_department=respiratory, use_rag=True, need_rag=False |
| 2026-03-09 21:03:36 | 63eded84-c864-413a-83ae-e44bef400626 | 我皮肤痒 | `["memory_read", "health_concierge", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | Current Medical Research & News | safety_level=SAFE, domain=medical, primary_department=dermatology, use_rag=True, need_rag=False |
| 2026-03-09 21:09:25 | 3f8f725c-90ff-45f6-bd0e-138c4334577f | 我眼睛干怎么办 | `["memory_read", "health_concierge", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | Current Medical Research & News | safety_level=SAFE, domain=medical, primary_department=ophthalmology, use_rag=True, need_rag=False |
| 2026-03-09 21:25:42 | 0be78b23-fb25-4b95-b91e-ae5afd33c5f5 | Hello AI | `[]` | Mock Brain | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 21:26:45 | 77b357b0-de3b-4a87-9536-ddcb59e1cc15 | Hello stream | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 21:32:02 | 0f912b1c-ffde-45b4-9605-5179bb785b9c | hello | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 21:34:51 | e5eafb90-1656-4b35-940f-8a896121665b | 我眼镜有点红肿，怎么办 | `["memory_read", "health_concierge", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | Current Medical Research & News | safety_level=SAFE, domain=medical, primary_department=ophthalmology, use_rag=True, need_rag=False |
| 2026-03-09 21:37:51 | e5eafb90-1656-4b35-940f-8a896121665b | 我的右眼做过角膜移植手术，现在又看不清了 | `["memory_read", "health_concierge", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | Current Medical Research & News | safety_level=SAFE, domain=medical, primary_department=ophthalmology, use_rag=True, need_rag=False |
| 2026-03-09 22:08:15 | 8356ed22-99df-4250-88f1-a86918ed9d96 | 你好 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 22:20:42 | 3f3ae506-bb1b-4f5d-9528-e574c9867685 | hello | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 22:21:03 | 3f3ae506-bb1b-4f5d-9528-e574c9867685 | 你是什么模型 | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | System Message | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 22:32:58 | 0df2927f-3416-4f9e-b5a8-ae3c04442002 | hello | `["memory_read", "health_concierge", "judge_need_rag", "executor", "memory_write_async"]` | General AI Coach | safety_level=SAFE, domain=general, primary_department=, use_rag=False, need_rag=False |
| 2026-03-09 22:33:48 | 3599f117-865a-4249-a0e5-0ef52e848eba | 我在冬天皮肤会很干，怎么办 | `["memory_read", "health_concierge", "query_rewriter", "rag", "reranker", "executor", "memory_write_async"]` | 皮肤科 知识库 | safety_level=SAFE, domain=medical, primary_department=dermatology, use_rag=True, need_rag=False |
