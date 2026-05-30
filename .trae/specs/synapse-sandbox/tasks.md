# Tasks

- [ ] Task 1: 创建 Sandbox 核心模块
  - [ ] SubTask 1.1: 创建 `core/sandbox.py`，实现 `Sandbox` 类
  - [ ] SubTask 1.2: 使用 `multiprocessing.Process` + `Queue` 在子进程执行技能
  - [ ] SubTask 1.3: 实现超时控制（默认 10 秒），超时后 `terminate()`
  - [ ] SubTask 1.4: 捕获子进程异常并通过 Queue 返回错误信息
  - [ ] SubTask 1.5: 运行 `pytest tests/test_sandbox.py -v`

- [ ] Task 2: 修改 BaseSkill 和 SkillRouter 集成沙箱
  - [ ] SubTask 2.1: 在 `BaseSkill` 中添加 `use_sandbox` 属性（默认 True）
  - [ ] SubTask 2.2: 在 `SkillRouter` 中初始化 `Sandbox` 实例
  - [ ] SubTask 2.3: 修改 `process_query` 中的技能执行逻辑：如果 `skill.use_sandbox` 为 True，使用沙箱
  - [ ] SubTask 2.4: 运行 `pytest tests/test_skills_routing.py -v` 确保无回归

# Task Dependencies

- Task 2 依赖 Task 1
