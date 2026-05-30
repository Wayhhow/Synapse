# Tasks

- [ ] Task 1: 创建 SkillRegistry 模块
  - [ ] SubTask 1.1: 创建 `core/skill_registry.py`，实现 `SkillRegistry` 类
  - [ ] SubTask 1.2: 实现 `register(skill_name, description)` 方法
  - [ ] SubTask 1.3: 实现 `record_execution(skill_name, success, execution_time, error=None)` 方法
  - [ ] SubTask 1.4: 实现 `get_stats(skill_name)` 方法
  - [ ] SubTask 1.5: 使用 JSON 文件持久化（`data/skill_registry.json`）
  - [ ] SubTask 1.6: 运行 `pytest tests/test_skill_registry.py -v`

- [ ] Task 2: 创建 SkillEvaluator 模块（借鉴 darwin-skill 评估体系）
  - [ ] SubTask 2.1: 创建 `meta/skill_evaluator.py`，实现 `SkillEvaluator` 类
  - [ ] SubTask 2.2: 实现 5 维度评估：结构质量(20)、执行成功率(30)、错误处理(20)、具体性(15)、反模式(15)
  - [ ] SubTask 2.3: 实现 `evaluate(skill_name)` 方法，返回 0-100 分
  - [ ] SubTask 2.4: 实现 `find_low_quality_skills(threshold=50)` 方法
  - [ ] SubTask 2.5: 运行 `pytest tests/test_skill_evaluator.py -v`

- [ ] Task 3: 修改 SkillRouter 记录执行结果
  - [ ] SubTask 3.1: 在 `router/router.py` 的 `__init__` 中初始化 `SkillRegistry`
  - [ ] SubTask 3.2: 技能执行成功后调用 `registry.record_execution(skill_name, success=True, ...)`
  - [ ] SubTask 3.3: 技能执行失败后调用 `registry.record_execution(skill_name, success=False, error=...)`
  - [ ] SubTask 3.4: 运行 `pytest tests/test_skills_routing.py -v` 确保无回归

- [ ] Task 4: 修改 SkillCreator 集成棘轮机制
  - [ ] SubTask 4.1: 在 `generate_skill` 前检查 Registry 是否已有相似技能
  - [ ] SubTask 4.2: 生成新技能后自动 `registry.register()`
  - [ ] SubTask 4.3: 重新生成技能时，评估新版本分数，高于旧版才替换（棘轮机制）
  - [ ] SubTask 4.4: 运行 `pytest tests/test_meta_evolution.py -v` 确保无回归

# Task Dependencies

- Task 2 依赖 Task 1
- Task 3 依赖 Task 1
- Task 4 依赖 Task 1 和 Task 2
