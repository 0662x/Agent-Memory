# Quickstart: Memory Activation And Context Injection

This quickstart validates the implemented `002-memory-activation` feature. It assumes the `001-life-memory-plugin` prototype is already working.

## 1. Repository

```bash
cd /Users/oliver/Projects/hermes-life-memory
```

Feature branch:

```bash
git branch --show-current
# expected: 002-memory-activation
```

## 2. Unit Checks

Run activation unit tests:

```bash
uv run python -m pytest tests/unit/test_activation.py
```

Latest validation:

```text
2026-06-03 Australia/Sydney
13 passed
```

Covered behavior:

- personal-life request activates;
- technical/project request skips;
- profile-only instruction skips;
- temporary/current-task request skips;
- malformed hook payload skips;
- official Hermes `pre_llm_call` payloads using `user_message` and `conversation_history` are normalized;
- injection formatter includes data-only boundary and memory metadata;
- deleted/archived/expired/restricted/unauthorized sensitive/superseded memories are filtered;
- low-confidence young memories are filtered;
- block budget and max memory count are enforced.

## 3. Integration Checks

Run activation hook integration tests:

```bash
uv run python -m pytest tests/integration/test_activation_hook.py
```

Latest validation:

```text
2026-06-03 Australia/Sydney
9 passed
```

Covered behavior:

- direct activation pipeline injects relevant memories;
- no matching safe memory produces no context;
- deleted, archived, expired, restricted, sensitive, and superseded memories are not injected;
- activation traces record outcomes without leaking restricted raw content;
- fake plugin context captures `pre_llm_call` registration;
- fake hook payload uses the official Hermes `user_message`/`conversation_history` shape;
- routing guidance is preserved;
- activated memory context is appended only for relevant personal-life requests;
- malformed payload and activation failure fail closed to routing guidance only;
- large memory set smoke remains bounded and injects no more than the configured maximum.

## 4. Full Suite

```bash
uv run python -m pytest
```

Latest validation:

```text
2026-06-03 Australia/Sydney
112 passed in 0.60s
Python 3.11.15, pytest 9.0.3
```

## 5. Manual Hermes Smoke Test

Mount and enable the plugin as in the `001` quickstart, then run Hermes normally:

```bash
hermes -z
```

Store a unique life memory:

```text
请记住：我周末跑步后通常买一瓶椰子水，测试标记是 ACTIVATION_MARKER。
```

Ask a relevant question without explicitly calling `life_memory_recall`:

```text
我周末运动后一般会买什么饮品？
```

Expected behavior:

- Hermes can use the stored life memory during the answer;
- the response does not reveal internal trace data unless asked;
- no memory content is written to native technical memory;
- `$HERMES_HOME/life_memory.db` contains an activation trace with the injected memory id.

Latest manual result:

```text
2026-06-03 Australia/Sydney
Hermes CLI: /Users/oliver/.local/bin/hermes
Plugin mount: /Users/oliver/.hermes/plugins/life_memory -> /Users/oliver/Projects/hermes-life-memory/plugins/life_memory
Marker: ACTIVATION_MARKER_20260603_191541
Stored memory_id: mem_e4ef8aed99a544218aacc1f54072ff47
Prompt: 我周末跑步后通常买什么饮品？请直接回答。
Response: 你周末跑步后通常买一瓶椰子水
Activation trace_id: trace_c8630e38414740378b53ed04607db3ef
Activation outcome: injected
Injected memory ids: ["mem_e4ef8aed99a544218aacc1f54072ff47"]
Context chars: 540
Cleanup trace_id: trace_cf46753684ba40c9a4ff0d4466067d9f
Cleanup outcome: smoke memory soft-deleted after verification
```

Observation: the first manual pass showed Hermes could use `life_memory_recall`, but no `activation` trace was written because the hook normalizer did not recognize the official `user_message` payload. The implementation was fixed to support `user_message`, `conversation_history`, and nested `extra`; the second manual pass produced the activation trace above.

## 6. Negative Smoke Test

Ask a technical question:

```text
这个 pytest fixture 为什么没有生效？
```

Expected behavior:

- no life-memory context is injected;
- technical memory routing guidance still remains available;
- no irrelevant personal memory appears in the answer.

## 7. Safety Smoke Test

Create or seed a restricted/sensitive memory, then ask a broad related question.

Expected behavior:

- restricted raw content is not injected;
- automatic context omits unauthorized sensitive/restricted memories;
- trace records filter counts/reasons, not raw restricted content.

## 8. Git Review

Latest `git status --short` review:

```text
M .specify/feature.json
M README.md
M plugins/life_memory/models.py
?? plugins/life_memory/activation.py
?? plugins/life_memory/routing.py
?? specs/001-life-memory-plugin/project-report.md
?? specs/002-memory-activation/
?? tests/fixtures/activation_cases.json
?? tests/integration/test_activation_hook.py
?? tests/unit/test_activation.py
?? tests/unit/test_routing.py
```

Commit boundary recommendation:

- Include the `002-memory-activation` files, `activation.py`, `models.py`, README updates, activation fixture, and activation tests in the activation commit.
- Include `routing.py` and `test_routing.py` with this commit or land them first as a 001 catch-up commit; activation depends on the composed routing hook.
- Keep `specs/001-life-memory-plugin/project-report.md` with the 001 documentation/report commit if separating history.
