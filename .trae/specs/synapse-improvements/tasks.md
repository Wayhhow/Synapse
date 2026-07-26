# Tasks

- [x] Task 1: 修复模块热重载和添加日志到 SkillRouter
  - [x] SubTask 1.1: 在 `router/router.py` 中引入 `logging` 和 `importlib.reload`
  - [x] SubTask 1.2: 修改 `_discover_skills()` 方法，已存在的模块使用 `importlib.reload()` 刷新
  - [x] SubTask 1.3: 将所有 `print` 替换为 `logger.info/warning/error`
  - [x] SubTask 1.4: 将 `process_query` 的 `_is_retry` 参数改为 `is_retry`
  - [x] SubTask 1.5: 运行 `pytest tests/test_skills_routing.py -v` 确保测试通过

- [x] Task 2: 修复文件名安全和添加日志到 SkillCreator
  - [x] SubTask 2.1: 在 `meta/skill_creator.py` 中引入 `logging`
  - [x] SubTask 2.2: 重写文件名安全校验逻辑：先用 `os.path.basename()` 提取，再拒绝包含 `/` 或 `\\` 的文件名，保留连字符 `-`
  - [x] SubTask 2.3: 将所有 `print` 替换为 `logger.info/warning/error`
  - [x] SubTask 2.4: 运行 `pytest tests/test_meta_evolution.py -v` 确保测试通过

- [x] Task 3: 增强 BaseSkill 并填充 `__init__.py`
  - [x] SubTask 3.1: 在 `core/base.py` 的 `BaseSkill` 中添加 `validate_args(self, **kwargs)` 方法
  - [x] SubTask 3.2: 填充 `core/__init__.py`，导出 `BaseSkill`
  - [x] SubTask 3.3: 填充 `router/__init__.py`，导出 `SkillRouter`
  - [x] SubTask 3.4: 填充 `skills/__init__.py`，导出 `WeatherSkill`（以及未来技能）
  - [x] SubTask 3.5: 填充 `meta/__init__.py`，导出 `SkillCreator`
  - [x] SubTask 3.6: 运行 `pytest` 确保无回归

- [x] Task 4: 将 WeatherSkill 改为调用真实天气 API
  - [x] SubTask 4.1: 调研 Open-Meteo API 的调用方式（地理编码 + 天气查询）
  - [x] SubTask 4.2: 修改 `skills/weather_skill.py`，使用 `httpx` 异步调用 Open-Meteo API
  - [x] SubTask 4.3: 处理 API 失败场景，返回友好的错误信息
  - [x] SubTask 4.4: 更新 `tests/test_skills_routing.py` 中 WeatherSkill 相关的测试（Mock API 调用）
  - [x] SubTask 4.5: 运行 `pytest tests/test_skills_routing.py -v` 确保测试通过

- [x] Task 5: 添加 CLI 入口和 .env.example
  - [x] SubTask 5.1: 创建 `.env.example`，包含 `OPENAI_API_KEY=your-api-key-here`
  - [x] SubTask 5.2: 创建 `cli.py`，实现交互式命令行循环
  - [x] SubTask 5.3: 手动测试 `python cli.py` 能够启动并响应输入

# 额外完成(实现过程中发现并修复)
- [x] Bug-6: `_discover_skills()` 开头清空 `self.skills`,避免已删除技能永久残留
- [x] Bug-3: meta-evolution 重试前移除冗余的 `add_message`,避免用户消息被重复记录
- [x] Bug-15: 移除 `WeatherArgs.date` 未使用字段,description 明确仅支持当前天气
- [x] Bug-16: 校验 `tool_calls` 的 `arguments` 必须为 dict,避免 `**non_dict` 崩溃
- [x] Bug-24: CLI 输出添加 `_format_result`,对 Pydantic 模型输出格式化 JSON
- [x] Bug-27: 多 `tool_calls` 时记录警告,明确只处理第一个
- [x] CLI 新增 `--skills` 参数列出所有已注册技能

# Task Dependencies

- Task 2 不依赖 Task 1，可以并行
- Task 3 不依赖 Task 1/2，可以并行
- Task 4 依赖 Task 3（因为可能需要 `validate_args`）
- Task 5 依赖 Task 1（因为 CLI 使用 `SkillRouter`）
