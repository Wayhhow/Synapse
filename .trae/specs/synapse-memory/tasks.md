# Tasks

- [ ] Task 1: 整合 mem0 并修改 SkillRouter
  - [ ] SubTask 1.1: 在 `requirements.txt` 中添加 `mem0ai>=0.1.0`
  - [ ] SubTask 1.2: 在 `router/router.py` 中导入 mem0，初始化 `Memory` 实例
  - [ ] SubTask 1.3: 修改 `process_query` 签名，添加 `session_id: Optional[str] = None`
  - [ ] SubTask 1.4: 在构建 LLM messages 时，如果有 `session_id`，从 mem0 获取历史并注入
  - [ ] SubTask 1.5: Agent 回复后，将用户输入和 Agent 回复存入 mem0
  - [ ] SubTask 1.6: 限制注入的历史消息为最近 10 轮
  - [ ] SubTask 1.7: 运行 `pytest tests/test_skills_routing.py -v` 确保无回归

- [ ] Task 2: 修改 CLI 支持 Session
  - [ ] SubTask 2.1: 在 `cli.py` 中导入 `uuid`，生成唯一 `session_id`
  - [ ] SubTask 2.2: 每次调用 `router.process_query(user_input, session_id=session_id)`
  - [ ] SubTask 2.3: 运行 `python -m py_compile cli.py` 检查语法

- [ ] Task 3: 编写记忆系统测试
  - [ ] SubTask 3.1: 创建 `tests/test_memory.py`，mock mem0 测试历史注入逻辑
  - [ ] SubTask 3.2: 运行 `pytest tests/test_memory.py -v`

# Task Dependencies

- Task 2 依赖 Task 1
- Task 3 依赖 Task 1
