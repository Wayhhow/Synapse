# Tasks

- [x] Task 1: 创建 SkillRegistry 模块
  - [x] SubTask 1.1: 创建 `core/skill_registry.py`，实现 `SkillRegistry` 类
  - [x] SubTask 1.2: 实现 `register(skill_name, description)` 方法
  - [x] SubTask 1.3: 实现 `record_execution(skill_name, success, execution_time, error=None)` 方法
  - [x] SubTask 1.4: 实现 `get_stats(skill_name)` 方法
  - [x] SubTask 1.5: 使用 JSON 文件持久化（`data/skill_registry.json`）
  - [x] SubTask 1.6: 运行 `pytest tests/test_skill_registry.py -v`

- [x] Task 2: 创建 SkillEvaluator 模块（借鉴 darwin-skill 评估体系）
  - [x] SubTask 2.1: 创建 `meta/skill_evaluator.py`，实现 `SkillEvaluator` 类
  - [x] SubTask 2.2: 实现 5 维度评估：结构质量(20)、执行成功率(30)、错误处理(20)、具体性(15)、反模式(15)
  - [x] SubTask 2.3: 实现 `evaluate(skill_name)` 方法，返回 0-100 分
  - [x] SubTask 2.4: 实现 `find_low_quality_skills(threshold=50)` 方法
  - [x] SubTask 2.5: 运行 `pytest tests/test_skill_evaluator.py -v`

- [x] Task 3: 修改 SkillRouter 记录执行结果
  - [x] SubTask 3.1: 在 `router/router.py` 的 `__init__` 中初始化 `SkillRegistry`
  - [x] SubTask 3.2: 技能执行成功后调用 `registry.record_execution(skill_name, success=True, ...)`
  - [x] SubTask 3.3: 技能执行失败后调用 `registry.record_execution(skill_name, success=False, error=...)`
  - [x] SubTask 3.4: 运行 `pytest tests/test_skills_routing.py -v` 确保无回归

- [x] Task 4: 修改 SkillCreator 集成棘轮机制
  - [x] SubTask 4.1: 在 `generate_skill` 前检查 Registry 是否已有相似技能
  - [x] SubTask 4.2: 生成新技能后自动 `registry.register()`
  - [x] SubTask 4.3: 重新生成技能时，评估新版本分数，高于旧版才替换（棘轮机制）
  - [x] SubTask 4.4: 运行 `pytest tests/test_meta_evolution.py -v` 确保无回归

# 额外完成(实现过程中发现并修复)
- [x] Bug-5: `register()` 现在会更新已存在技能的 description
- [x] Bug-9: 添加 `threading.RLock` 保证并发 `record_execution` 不丢增量
- [x] Bug-17: `persist_path` 为裸文件名时不再崩溃
- [x] Bug-19: 移除永不被更新的 `health_score` 字段,加载时迁移旧数据,改由 `SkillEvaluator` 实时计算
- [x] Bug-7: dim3 错误处理维度改为基于代码 try/except + response.error 字段评估(不再依赖永不清除的 last_error)
- [x] Bug-8: dim4 具体性维度改为基于 description 中的 "Trigger words:" 计数(不再仅看长度)
- [x] Bug-28: dim5 反模式从子串匹配升级为 AST 检查,堵住 `eval  ("1")` 等绕过方式
- [x] Bug-4: Router 检测技能返回的 `error` 字段并记录为失败
- [x] 新增 `tests/test_skill_evaluator_dimensions.py` 覆盖 dim3/dim4/dim5 的边界场景

# Task Dependencies

- Task 2 依赖 Task 1
- Task 3 依赖 Task 1
- Task 4 依赖 Task 1 和 Task 2
