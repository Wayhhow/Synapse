# Tasks

- [ ] Task 1: 修复 Sandbox 失败可识别契约
  - [ ] SubTask 1.1: 在 `core/sandbox.py` 定义 `SandboxResult` 容器(或复用带 error 的 BaseModel),包含 `success: bool`、`result: Any`、`error: Optional[str]`
  - [ ] SubTask 1.2: `Sandbox.execute` 在超时/异常/空结果时返回 `SandboxResult(success=False, error=...)`,成功时返回 `SandboxResult(success=True, result=...)`
  - [ ] SubTask 1.3: 在 `router/router.py` 中更新沙箱调用处:检查 `success` 字段,失败时走异常分支记录 `success=False` 并返回错误信息
  - [ ] SubTask 1.4: 新增 `tests/test_sandbox.py` 覆盖超时、异常、成功三种场景
  - [ ] SubTask 1.5: 运行 `pytest tests/ -v` 确保无回归

- [ ] Task 2: 实现 SkillEvaluator 真实维度检查
  - [ ] SubTask 2.1: 在 `meta/skill_evaluator.py` 添加 `_check_structure(skill_name)` 方法,读取 `skills/<skill_name>.py` 源码,用 AST 检查是否包含 `name`/`description`/`expected_args`/`expected_response_type`/`execute` 定义,每缺一项扣 4 分(满分 20)
  - [ ] SubTask 2.2: 添加 `_check_antipattern(skill_name)` 方法,扫描源码中是否出现 `eval(`、`exec(`、`os.system`、`subprocess`、`__import__`、`open(` 写模式等危险调用,每命中一项扣 5 分(满分 15)
  - [ ] SubTask 2.3: 修改 `evaluate(skill_name)`:dim1 和 dim5 调用上述方法,而非硬编码 20.0 / 15.0
  - [ ] SubTask 2.4: 文件不存在或解析失败时返回 0.0 并 log warning
  - [ ] SubTask 2.5: 新增 `tests/test_skill_evaluator.py` 覆盖结构完整/缺失、有/无反模式场景

- [ ] Task 3: 修复 SkillCreator 棘轮与注册名
  - [ ] SubTask 3.1: 在 `meta/skill_creator.py` 中,写文件后用 `importlib` 加载新模块,获取真实 `skill.name`
  - [ ] SubTask 3.2: 用真实 skill name 调用 `registry.register()`,而非文件名
  - [ ] SubTask 3.3: 棘轮机制:写文件前评估旧代码(若文件存在)得 `old_score`,写文件后评估新代码得 `new_score`,对比决定保留或回滚。评估基于 Task 2 的真实维度 + 现有 stats
  - [ ] SubTask 3.4: 回滚时恢复旧文件内容(写文件前先备份),而非仅删除新文件
  - [ ] SubTask 3.5: 更新 `tests/test_meta_evolution.py` 添加棘轮回滚场景测试

- [ ] Task 4: 修复 Router retry 透传 session_id
  - [ ] SubTask 4.1: 在 `router/router.py` 的 `process_query` 中,meta-evolution retry 调用改为 `self.process_query(user_query, is_retry=True, session_id=session_id)`
  - [ ] SubTask 4.2: 在 `tests/test_skills_routing.py` 的 `test_process_query_meta_evolution` 中传入 `session_id`,断言 retry 后 memory 中有两条 user 消息
  - [ ] SubTask 4.3: 运行 `pytest tests/test_skills_routing.py -v`

- [ ] Task 5: 修复 Web UI skill_used 误判
  - [ ] SubTask 5.1: 在 `web/app.py` 的 `/chat` 端点,改为 `isinstance(result, BaseModel)` 判断,仅 BaseModel 实例返回类名,否则 `None`
  - [ ] SubTask 5.2: 在 `tests/` 新增 `test_web_app.py` 覆盖文本响应和技能响应两种场景

- [ ] Task 6: 修复 Translation / News URL 编码
  - [ ] SubTask 6.1: 在 `skills/translation_skill.py` 中用 `urllib.parse.quote(args.text)` 编码 query
  - [ ] SubTask 6.2: 在 `skills/news_skill.py` 中用 `urllib.parse.quote(args.query)` 编码 query
  - [ ] SubTask 6.3: 新增 `tests/test_skills_url_encoding.py` 验证含 `&`/`#`/空格的 query 不破坏 URL

- [ ] Task 7: 配置日志可见性
  - [ ] SubTask 7.1: 在 `cli.py` 的 `main()` 开头添加 `logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")`
  - [ ] SubTask 7.2: 在 `web/app.py` 的 `lifespan` 开头添加同样的 basicConfig
  - [ ] SubTask 7.3: 验证 `python cli.py --skills` 启动时能看到 INFO 日志

- [ ] Task 8: 新增 Web API 端点
  - [ ] SubTask 8.1: 在 `web/app.py` 添加 `GET /health` 返回 `{"status": "ok", "skills_count": len(router_instance.skills)}`
  - [ ] SubTask 8.2: 添加 `GET /stats` 返回 `router_instance.evaluator.generate_improvement_report()`
  - [ ] SubTask 8.3: 添加 `GET /history/{session_id}` 返回 `router_instance.memory.get_history(session_id)`
  - [ ] SubTask 8.4: 在 `tests/test_web_app.py` 添加端点覆盖测试

- [ ] Task 9: CLI 支持 --skills 参数
  - [ ] SubTask 9.1: 在 `cli.py` 用 `argparse` 解析 `--skills` flag
  - [ ] SubTask 9.2: 若 `--skills`,打印所有技能的 name + description 后退出
  - [ ] SubTask 9.3: 否则进入原有交互循环

# Task Dependencies

- Task 3 依赖 Task 2(棘轮使用真实评估)
- Task 8 依赖 Task 7(端点日志可见)
- Task 1、4、5、6 互相独立,可并行
- Task 9 独立
