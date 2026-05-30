# Tasks

- [ ] Task 1: 创建 Memory 核心模块
  - [ ] SubTask 1.1: 创建 `core/memory.py`，实现 `Memory` 类
  - [ ] SubTask 1.2: `Memory` 类包含 `add_message(session_id, role, content)` 方法
  - [ ] SubTask 1.3: `Memory` 类包含 `get_history(session_id)` 方法，返回消息列表
  - [ ] SubTask 1.4: `Memory` 类包含 `clear(session_id)` 方法
  - [ ] SubTask 1.5: 支持 `max_history` 参数，超出时丢弃最早消息
  - [ ] SubTask 1.6: 运行 `pytest tests/test_memory.py -v`（先写测试再实现）

- [ ] Task 2: 修改 SkillRouter 注入记忆上下文
  - [ ] SubTask 2.1: 在 `router/router.py` 的 `__init__` 中初始化 `Memory` 实例
  - [ ] SubTask 2.2: 修改 `process_query` 签名，添加可选 `session_id: Optional[str] = None`
  - [ ] SubTask 2.3: 在构建 LLM messages 时，如果有 `session_id`，先注入历史消息
  - [ ] SubTask 2.4: Agent 回复后，将用户输入和 Agent 回复存入记忆
  - [ ] SubTask 2.5: 运行 `pytest tests/test_skills_routing.py -v` 确保无回归

- [ ] Task 3: 修改 CLI 支持 Session
  - [ ] SubTask 3.1: 在 `cli.py` 中导入 `uuid`，为每次运行生成唯一 `session_id`
  - [ ] SubTask 3.2: 每次调用 `router.process_query(user_input, session_id=session_id)`
  - [ ] SubTask 3.3: 手动测试 CLI 多轮对话是否正常工作

# Task Dependencies

- Task 2 依赖 Task 1
- Task 3 依赖 Task 2
