# Synapse 关键 Bug 修复 + Spec 对齐 + 文档校正

> 范围:**A. 关键 bug + spec 对齐**(用户已选)。一次性完整推进,不分阶段确认。
> 审查者已亲自验证全部 bug,本计划基于真实代码而非子代理推测。

## 摘要

Synapse 是一个"自进化 AI Agent 框架"——LLM 在运行时生成新 Python 技能文件、加载、执行,辅以 5 维评估和棘轮机制。代码审查发现 **4 个严重 bug、6 个高优先级 bug、若干中低优先级问题**,以及 **7 项 spec 与实现脱节**。本计划修复所有关键问题,使项目真正达到 README 宣称的"可用"状态,并把 spec/README 与实际代码对齐。**不引入新功能、不重写架构、不做学术化改造**。

---

## 当前状态分析

### 项目本质(给可能不熟悉这个领域的用户)

Synapse 的核心循环:
1. 用户提问 → LLM 用 OpenAI tool-calling 决定调用哪个技能
2. 命中技能 → 在子进程沙箱里执行(10s 超时)→ 返回结果 + 记忆入库
3. 没命中 → LLM 触发 `request_new_skill` → SkillCreator 让 LLM 生成 Python 代码 → 写文件 → 加载模块 → 重新路由
4. 技能有 5 维健康度评估,新生成版本必须比旧版本分高才替换(棘轮机制)

**项目独特价值**:运行时生成可执行 Python 技能 + 5 维量化评估 + 棘轮 + 进程沙箱。这是真实实现的差异化,不是 mock。

**项目核心风险**:声称的"安全沙箱"有致命漏洞(见 Bug-1),"棘轮"评估维度名不副实(见 Bug-7/8),并发场景下数据会丢(见 Bug-9)。

### 审查者已验证的 Bug 清单

| ID | 严重度 | 文件 | 一句话描述 |
|----|--------|------|-----------|
| Bug-1 | 🔴 严重 | `meta/skill_creator.py` | LLM 生成代码在 `_load_skill_name` 时通过 `exec_module` 执行顶层代码,**在反模式检查之前**——沙箱形同虚设 |
| Bug-2 | 🔴 严重 | `core/sandbox.py`,`router/router.py` | `Sandbox.execute` 同步 `process.join`,在 async `process_query` 中阻塞整个 FastAPI 事件循环 |
| Bug-3 | 🔴 严重 | `router/router.py:198-202` | meta-evolution 重试前先 `add_message(user)`,递归 `process_query` 又记一次 → 用户消息重复 |
| Bug-4 | 🔴 严重 | `router/router.py:211-221` | skill `execute` 内部捕获异常返回带 `error` 的 response,Router 仍记 `success=True`,统计/评估失真 |
| Bug-5 | 🟠 高 | `core/skill_registry.py:15-27` | `register()` 对已存在技能是 no-op,description 永远为空(影响 dim4 评分) |
| Bug-6 | 🟠 高 | `router/router.py:61-91` | `_discover_skills` 从不清理 `self.skills`,已删除技能永久残留 |
| Bug-7 | 🟠 高 | `meta/skill_evaluator.py:149` | `dim3` 检查 `last_error is None`,但 `last_error` 失败后永不清除 → 失败一次永久扣分 |
| Bug-8 | 🟠 高 | `meta/skill_evaluator.py:150` | spec 要求"description 是否包含触发词",实际只检查 `len > 10` |
| Bug-9 | 🟠 高 | `core/memory.py`,`core/skill_registry.py` | 每次 `add_message`/`record_execution` 全量重写 JSON,无锁,多请求并发会丢数据 |
| Bug-10 | 🟠 高 | `meta/skill_creator.py` | spec 要求"生成前检查相似技能",**完全未实现** |
| Bug-11 | 🟡 中 | `web/app.py:84-86` | 用相对路径 `web/static/...`,工作目录外启动会 404 |
| Bug-12 | 🟡 中 | `core/sandbox.py:34-38` | `terminate` 后 1s 仍存活未 `kill`,Queue 未 close → 僵尸进程/资源泄漏 |
| Bug-13 | 🟡 中 | `skills/calculator_skill.py:52` | 允许 `ast.Pow`,`2 ** 99999999` 可耗尽 CPU(虽有超时) |
| Bug-14 | 🟡 中 | `skills/data_analysis_skill.py:42` | spec 要求支持 JSON 数组,实际只 `split(",")`,传 `[1,2,3]` 失败 |
| Bug-15 | 🟡 中 | `skills/weather_skill.py:8,33-76` | `WeatherArgs.date` 字段存在但 `execute` 完全不用,问"明天"返回今天 |
| Bug-16 | 🟡 中 | `router/router.py:179` | `json.loads(arguments)` 未校验为 dict,非 dict 时 `**arguments` 崩溃 |
| Bug-17 | 🟡 中 | `core/memory.py:34`,`core/skill_registry.py:53` | `os.makedirs(os.path.dirname("memory.json"))` → `os.makedirs("")` 崩溃 |
| Bug-19 | 🟡 中 | `core/skill_registry.py:25` | `health_score` 持久化但 `record_execution` 从不更新,永远是 100.0 |
| Bug-20 | 🟡 中 | `web/app.py:45` | `str(result.model_dump())` 输出 `{'location': 'Seattle', ...}` 这种 Python dict repr |
| Bug-24 | 🟡 中 | `cli.py:44` | `print(result)` 对 Pydantic 模型输出 repr,用户难读 |
| Bug-27 | 🟡 中 | `router/router.py:177` | `message.tool_calls[0]` 只处理第一个,LLM 并行调用其余被忽略 |
| Bug-28 | 🟡 中 | `meta/skill_evaluator.py:17-26` | 反模式用子串匹配,可被 `eval  ("1")` 绕过;只覆盖 8 个模式,`os.remove`/`shutil.rmtree` 等未覆盖 |
| Bug-29 | 🟡 中 | `router/router.py:38`,`meta/skill_creator.py:38` | **最终验证阶段发现**:`SkillRouter.__init__` 和 `SkillCreator.__init__` 都在构造时立即创建 `AsyncOpenAI(api_key=None)`,导致 `python cli.py --skills` 和 `/health` 端点在未设 `OPENAI_API_KEY` 时直接 `OpenAIError` 崩溃。修复:把 `self.client` 改为 `@property` 懒构造,仅在 `process_query`/`generate_skill` 实际需要 LLM 时才创建。新增 `test_router_boots_without_openai_api_key` 回归测试。 |

### Spec 与实现脱节清单

| Spec | 声明 | 实际 | 处理 |
|------|------|------|------|
| `synapse-skill-eval` | "生成前检查相似技能" | 未实现 | **代码补齐**(Bug-10) |
| `synapse-skill-eval` | dim4 "description 是否包含触发词" | 只检查长度 | **代码修正**(Bug-8) |
| `synapse-memory` | "整合 mem0 库" | 自研 Memory | **更新 spec 说明决策**(自研更轻量,无新依赖) |
| `synapse-more-skills` | "NewsSkill 调用 GNews" | 用 Google News RSS | **更新 spec 说明决策**(RSS 无需 Key,更稳) |
| `synapse-more-skills` | "DataAnalysis 支持 JSON 数组" | 只支持逗号分隔 | **代码补齐**(Bug-14) |
| 6/7 个 spec | `tasks.md` 全 `[ ]` 但 `checklist.md` 全 `[x]` | 不一致 | **更新 tasks.md 反映实际完成状态** |
| README | 称 arxiv 2605.23899 为 "SkillLens" | 论文实际标题 "From Raw Experience to Skill Consumption",业界代号 SkillLens;另有 arxiv 2605.08386 官方叫 SkillLens(不同论文) | **修正 README 引用** |

### 调研中已核实的事实(避免误改)

- arxiv `2605.23899` 和 `2605.23904` **真实存在**(2026-05-22 提交),非伪造
- 不在本次范围内:对齐 SkillOpt 学术叙事、AST 审计层、SQLite 迁移、技能 embedding 检索、Docker 沙箱——这些属于范围 B/C,用户已选 A

---

## 假设与决策

1. **不引入新依赖**:`mem0`、`aiosqlite`、`bandit` 等都不加。所有修复用 Python 标准库完成。
2. **不破坏现有测试 API**:`SkillRouter`、`BaseSkill`、`Sandbox` 的公开签名保持不变。
3. **测试中编码 bug 行为的,同步修正断言**:如 `test_process_query_meta_evolution` 第 189 行 `assert len(user_messages) == 2` 是把 Bug-3 当预期,修复 bug 时改为 `== 1`。
4. **spec 文档与代码冲突时,代码是真相源**:更新 spec 反映实际实现,而非反过来(除非 spec 要求明显合理且代码缺失,如 Bug-10/14)。
5. **README 修订只做准确性校正,不做学术化包装**:不添加与 SkillOpt/SkillLens 的对齐叙事(那是范围 C),只修正错误引用和过度宣传。
6. **保留 `route()` deprecated 方法**:仍被 `test_weather_skill_execution` 使用,删除会破坏测试。仅添加 deprecation 警告。
7. **WeatherSkill 的 date 参数**:简化为移除该字段(避免误导),description 改为"current weather only"。实现 daily 预报是范围 B 的事。

---

## 提议的改动(按阶段)

### 阶段 1:安全修复( Critical )

#### 1.1 `meta/skill_creator.py` — 修复 Bug-1 + Bug-10 + Bug-28

**问题**:第 117 行 `_load_skill_name()` 调用 `spec.loader.exec_module(module)` 执行模块顶层代码,在第 128 行 `evaluate_code_quality()` 反模式检查**之前**。LLM 生成 `import os; os.system("rm -rf /")` 在顶层代码中,会先执行,沙箱无效。

**改法**:
- 把 `evaluate_code_quality(generated_skill.code)` 提前到 `_load_skill_name()` **之前**(第 116 行之前)
- 增加新方法 `_check_top_level_safety(code) -> Optional[str]`,用 AST 解析,拒绝顶层含 `ast.Expr`/`ast.Call`(函数调用)的代码,只允许 `Import`/`ImportFrom`/`ClassDef`/`Assign`/`FunctionDef`/`AsyncFunctionDef`。返回拒绝原因或 None。
- 在写文件前调用 `_check_top_level_safety`,失败则 `return False`。
- 实现 `_find_similar_skill(intent) -> Optional[str]`(Bug-10):用关键词重叠(Jaccard 相似度 ≥ 0.5)对比 `self.registry.get_all_stats()` 中的 description,返回相似技能名。在 `generate_skill` 开头调用,若存在相似技能则 `return False` 并 log warning "已存在相似技能 X,跳过生成"。

**为什么**:这是项目最严重的安全漏洞。LLM 生成的代码本应在沙箱内执行,但模块加载阶段就在主进程执行了顶层代码,任何 `import os; os.system(...)` 都会直接生效。

#### 1.2 `meta/skill_evaluator.py` — 修复 Bug-28

**改法**:把 `_ANTIPATTERN_PATTERNS` 从子串匹配改为 AST 检查。新增 `_check_antipattern_ast(code)`:遍历 AST,检查 `Call` 节点的函数是否为危险调用(`eval`/`exec`/`compile`/`os.system`/`subprocess.Popen`/`__import__`/`os.popen`/`os.remove`/`os.unlink`/`shutil.rmtree`)。同时保留对 `globals()`/`locals()` 字符串引用的检查。

---

### 阶段 2:正确性修复( Critical/High )

#### 2.1 `core/sandbox.py` + `router/router.py` — 修复 Bug-2 + Bug-12

**问题**:`Sandbox.execute` 是同步方法,`process.join(timeout=10)` 阻塞。在 `async def process_query` 中直接 `self.sandbox.execute(skill, **arguments)` 阻塞 FastAPI 事件循环。

**改法**:
- 在 `Sandbox` 中新增 `async def execute_async(...)`,内部用 `await asyncio.get_event_loop().run_in_executor(None, self._execute_sync, skill_instance, kwargs)` 包裹现有的同步逻辑。保留 `execute` 同步方法(向后兼容 + 测试用)。
- `execute_async` 实际执行 `_execute_sync`,后者是当前 `execute` 的实现重命名。
- 改 `Sandbox.execute` 在超时后 `if process.is_alive(): process.kill(); process.join(timeout=1)`(Bug-12),并在返回前 `queue.close(); queue.join_thread()`(Bug-12)。
- `router/router.py` 第 213-214 行改为 `sandbox_result = await self.sandbox.execute_async(skill, **arguments)`。

#### 2.2 `router/router.py` — 修复 Bug-3 + Bug-4 + Bug-16 + Bug-27

**Bug-3 改法**:删除第 198-199 行 meta-evolution 重试前的 `self.memory.add_message(session_id, "user", user_query)`。用户消息只在递归调用里成功执行技能后记录一次(第 234 行)。如果 meta-evolution 失败(第 204-205 行),则记录一次 user + 一次 assistant error。

**Bug-4 改法**:在第 220 行 `self.registry.record_execution(function_name, success=True, ...)` 之前,检查 `result` 是否是 `BaseModel` 且有 `error` 字段非空。若是,改为 `success=False, error=result.error`。

**Bug-16 改法**:第 179 行 `arguments = json.loads(tool_call.function.arguments)` 后,加 `if not isinstance(arguments, dict): return f"Error: invalid tool arguments: expected object, got {type(arguments).__name__}"`。

**Bug-27 改法**:第 177 行改为遍历 `message.tool_calls`,但只对 `request_new_skill` 类型严格单次,其他工具可顺序执行(为了简单,本次只加 warning log "Multiple tool calls received, processing first" 并保持单次处理)。完整多工具支持属范围 B。

#### 2.3 `tests/test_skills_routing.py` — 修复 Bug-3 测试断言

**改法**:第 189 行 `assert len(user_messages) == 2` 改为 `assert len(user_messages) == 1`,因为修复 Bug-3 后用户消息只记录一次。添加注释说明历史。

---

### 阶段 3:评估维度修正( High - spec 对齐 )

#### 3.1 `meta/skill_evaluator.py` — 修复 Bug-7 + Bug-8

**Bug-7 改法**:`dim3_error_handling` 改为检查代码中是否有 `try`/`except` 块和 `error` 字段定义。新增 `_check_error_handling_from_code(code)`:遍历 AST,若找到 `Try` 节点且 response 模型有 `error` 字段(简单检查 `error: Optional` 字符串),给 20 分;只有其一给 15 分;都没有给 5 分。不再依赖运行时 `last_error`。

**Bug-8 改法**:`dim4_specificity` 改为检查 description 是否包含 "Trigger words:" 后跟关键词(spec 原意)。新增 `_check_specificity_from_description(description)`:解析 "Trigger words: a, b, c" 模式,若至少 2 个触发词则给 15 分,1 个给 10 分,无给 5 分。所有 6 个内置技能的 description 都已含 "Trigger words:",可拿满分。

#### 3.2 `core/skill_registry.py` — 修复 Bug-5 + Bug-19

**Bug-5 改法**:`register(skill_name, description)` 改为:若技能已存在且新 description 非空,更新 description。若不存在,正常创建。

**Bug-19 改法**:移除 `register()` 中的 `health_score` 字段(它从不更新,误导)。`get_stats()` 返回时实时调用 `SkillEvaluator.evaluate()` 计算(注入 evaluator 引用),或在 `generate_improvement_report` 中明确说明 health_score 是实时计算的。简化:直接移除持久化的 `health_score`,所有展示走 `SkillEvaluator`。

#### 3.3 `data/skill_registry.json` — 数据迁移

**改法**:删除所有 `health_score` 字段。补充 6 个技能的 `description` 字段(从代码里读实际值)。

---

### 阶段 4:可靠性修复( High )

#### 4.1 `core/memory.py` + `core/skill_registry.py` — 修复 Bug-9 + Bug-17

**Bug-9 改法**:两个类各加 `threading.Lock()`。`Memory._save` 和 `SkillRegistry._save` 在锁内执行 `load→modify→write` 完整周期。`add_message`/`record_execution`/`clear`/`get_history`/`get_stats` 都加锁。注意:`_save` 加锁后,`add_message` 调用 `_save` 时不能再持有锁(可重入锁 `RLock`,或重构 `_save_locked` 内部方法)。

**Bug-17 改法**:`dir_path = os.path.dirname(self.persist_path); if dir_path: os.makedirs(dir_path, exist_ok=True)`。两处都改。

#### 4.2 `router/router.py` — 修复 Bug-6

**Bug-6 改法**:`_discover_skills()` 开头加 `self.skills = {}`(清空),但保留 `self._loaded_modules`(用于 reload 判断)。这样已删除文件不再残留。

---

### 阶段 5:Skill 修正( Medium - spec 对齐 )

#### 5.1 `skills/data_analysis_skill.py` — 修复 Bug-14

**改法**:第 42 行 `numbers = [float(x.strip()) for x in args.data.split(",") if x.strip()]` 改为先尝试 `json.loads(args.data)`,若返回 list 则用之,否则 fallback 到 `split(",")`。文档说明支持 `1,2,3` 和 `[1,2,3]` 两种格式。

#### 5.2 `skills/weather_skill.py` — 修复 Bug-15

**改法**:移除 `WeatherArgs.date` 字段(避免误导)。`description` 改为 "Get the current weather for a specific location. Trigger words: weather, temperature, forecast, 天气, 温度"。更新 [tests/test_skills_routing.py](file:///workspace/tests/test_skills_routing.py) 第 71/83 行去掉 `date` 参数。

#### 5.3 `skills/calculator_skill.py` — 修复 Bug-13

**改法**:在 AST 检查前加 `if len(args.expression) > 200: return error "expression too long"`。在 `eval` 前,若 AST 含 `ast.Pow`,检查左右操作数是否为 `ast.Constant` 且右值 ≤ 1e6,否则拒绝。

---

### 阶段 6:工程化修复( Medium )

#### 6.1 `web/app.py` — 修复 Bug-11 + Bug-20

**Bug-11 改法**:
```python
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
# index():
return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
# mount:
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
```

**Bug-20 改法**:`reply = str(result.model_dump())` 改为格式化输出。在 `BaseSkill` 中加默认 `__str__` 方法,或在 router 中:若 result 是 BaseModel,优先用 `result.model_dump_json(indent=2)`(JSON 友好),或检查是否有 `to_user_message()` 方法。最简方案:web/app.py 里 `reply = result.model_dump_json(indent=2) if isinstance(result, PydanticModel) else str(result)`。

#### 6.2 `cli.py` — 修复 Bug-24

**改法**:第 44 行 `print(result)` 改为:若 result 是 BaseModel,`print(result.model_dump_json(indent=2))`,否则 `print(result)`。

---

### 阶段 7:Spec 文档对齐

#### 7.1 更新 7 个 spec 的 `tasks.md`

把所有 `[ ]` 改为 `[x]`(对照实际完成情况),与 `checklist.md` 一致。对于部分完成的项(如 synapse-memory 的 mem0 整合),保留 `[ ]` 并注明"决策:改用自研,见 spec 修订"。

#### 7.2 更新 `synapse-memory/spec.md`

在 "What Changes" 中加 "Decision: 不整合 mem0,改用自研轻量 Memory 类,避免引入新依赖。原因:mem0 增加重型依赖,与项目'零额外依赖'哲学冲突"。

#### 7.3 更新 `synapse-more-skills/spec.md`

把 "调用 GNews 免费 API" 改为 "调用 Google News RSS(无需 API Key,比 GNews 更稳定)"。把 DataAnalysis 要求改为"支持逗号分隔或 JSON 数组"。

---

### 阶段 8:测试补全

#### 8.1 新增 `tests/test_memory.py`(spec 要求但缺失)

覆盖:
- `add_message`/`get_history` 基本读写
- `max_history * 2` 截断
- `clear` 删除 session
- `persist_path` 持久化 + reload
- `persist_path=None` 纯内存模式
- **Bug-17 回归**:`persist_path="memory.json"`(无目录)不崩溃
- **Bug-9 并发**:用 `threading.Thread` 起 10 个线程同时 `add_message`,验证无数据丢失(JSON load 后条数正确)

#### 8.2 新增 `tests/test_skill_registry.py`

覆盖:
- `register` 新建/已存在(Bug-5:已存在时 description 更新)
- `record_execution` 累计统计
- `record_execution(success=True)` 不写 `last_error`(Bug-7 相关)
- `get_stats`/`get_all_stats`
- 持久化 round-trip
- **Bug-17 回归**

#### 8.3 新增 `tests/test_skill_creator_security.py`

覆盖:
- **Bug-1 回归**:LLM 生成代码顶层含 `os.system("rm -rf /")`,被 `_check_top_level_safety` 拒绝,`generate_skill` 返回 False,文件未写入
- 顶层含函数调用 `print("hi")` 被拒绝
- 顶层只有 `Import`/`ClassDef`/`Assign` 通过
- **Bug-10 回归**:registry 中已有 description 相似的技能,`generate_skill` 返回 False 并 log warning
- **Bug-28 回归**:代码含 `getattr(builtins, "eval")("1")` 这种 AST 检测能挡(子串匹配挡不住)

#### 8.4 新增 `tests/test_skill_evaluator_dimensions.py`

覆盖:
- **Bug-7**:有 try/except + error 字段 → dim3 = 20;无 → 5(不再依赖 last_error)
- **Bug-8**:description 含 "Trigger words: a, b, c" → dim4 = 15;无 → 5
- **Bug-28**:代码含 AST-level 危险调用 → dim5 扣分
- 整合 `evaluate()` 端到端

#### 8.5 扩展 `tests/test_skills_routing.py`

- **Bug-3 回归**:meta-evolution 成功后,`user_messages` 数 == 1(不是 2)
- **Bug-4 回归**:skill 返回带 `error` 的 response,registry 记 `success=False`
- **Bug-16 回归**:LLM 返回非 dict arguments,Router 返回 error string 而非崩溃
- **Bug-6 回归**:模拟技能文件删除,`_discover_skills` 后 `self.skills` 不含已删除技能

#### 8.6 新增 `tests/test_sandbox_async.py`

- **Bug-2 回归**:`Sandbox.execute_async` 在 async 上下文中可 await,期间其他协程可推进(用 `asyncio.sleep` 验证不阻塞)

---

### 阶段 9:README 与文档校正

#### 9.1 `README.md` 修正

**修正点**:
1. **arxiv 引用修正**(第 126、345-347 行):
   - `2605.23899` 标题改为 "From Raw Experience to Skill Consumption"(注明"业界报道代号 SkillLens"),避免与 arxiv 2605.08386(官方标题 SkillLens,不同论文)混淆
   - `2605.23904` (SkillOpt) 引用正确,保留
2. **沙箱安全宣传校正**(第 156-174 行):
   - 把"✅ 技能异常不影响主进程"改为"✅ 技能执行异常不影响主进程(注:技能代码加载阶段已加 AST 顶层安全检查)"
   - 不再宣称"完全隔离",改为"进程级隔离 + AST 顶层检查"
3. **对比表诚实化**(第 332-340 行):
   - Synapse 沙箱行加脚注"进程级 + AST,非容器级"
   - 移除"过度宣传"嫌疑的表述
4. **新增"已知限制"section**:
   - 单进程 OpenAI 调用(非流式)
   - Sandbox 不可用于 CPU 密集型技能(子进程开销)
   - Memory 持久化基于 JSON+锁,适合中小规模会话(<10000)
   - Web API 默认无认证(开发模式)
5. **更新项目结构**反映实际(已无变化,核对一遍)
6. **更新"如何写新技能"**示例:补 `validate_args` 用法(子类可不写 `self.expected_args(**kwargs)`,直接 `args = self.validate_args(**kwargs)`)

#### 9.2 不做的事(明确说明)

- 不添加 SkillOpt/SkillLens 学术对齐叙事(范围 C)
- 不添加技能 embedding 检索(范围 B)
- 不迁移 SQLite(范围 B,本次用 Lock 解决并发)
- 不添加 Docker 沙箱后端(范围 B/C)
- 不重写 `route()` deprecated 方法(避免破坏测试)

---

## 验证步骤

### 单元测试

```bash
cd /workspace
pytest tests/ -v
```

预期:所有现有测试 + 新增测试通过。特别关注:
- `test_process_query_meta_evolution` 中 `len(user_messages) == 1`(Bug-3 修复后)
- `test_skill_creator_security.py` 全部通过(Bug-1/10/28)
- `test_memory.py` 并发测试通过(Bug-9)
- `test_skill_evaluator_dimensions.py` 全部通过(Bug-7/8)

### 手工验证

1. **沙箱安全验证**:
   ```python
   # 启动 CLI,问"帮我删除 /tmp 目录"
   # 预期:LLM 生成技能时被 _check_top_level_safety 拦截,返回错误,不执行
   ```

2. **Web UI 验证**:
   ```bash
   cd /workspace
   uvicorn web.app:app --reload
   # 访问 http://localhost:8000
   # 测试:北京天气、计算 2+3、分析数据 1,2,3
   # 验证 reply 是 JSON 格式而非 Python dict repr
   ```

3. **工作目录外启动验证**(Bug-11):
   ```bash
   cd /tmp
   uvicorn web.app:app --reload --app-dir /workspace
   # 访问 http://localhost:8000 应正常加载 index.html
   ```

### 静态检查

- `python -c "from core import BaseSkill; from router import SkillRouter; from meta import SkillCreator, SkillEvaluator"` — 验证导入正常
- `python cli.py --skills` — 列出 6 个技能,description 非空

---

## 改动文件清单(汇总)

| 文件 | 改动类型 | 涉及 Bug |
|------|---------|----------|
| `meta/skill_creator.py` | 重大修改 | Bug-1, 10, 28 |
| `meta/skill_evaluator.py` | 重大修改 | Bug-7, 8, 28 |
| `core/sandbox.py` | 重大修改 | Bug-2, 12 |
| `router/router.py` | 重大修改 | Bug-2, 3, 4, 6, 16, 27 |
| `core/memory.py` | 中等修改 | Bug-9, 17 |
| `core/skill_registry.py` | 中等修改 | Bug-5, 9, 17, 19 |
| `core/base.py` | 小修改 | 加 `__str__` 默认实现(可选) |
| `skills/data_analysis_skill.py` | 小修改 | Bug-14 |
| `skills/weather_skill.py` | 小修改 | Bug-15 |
| `skills/calculator_skill.py` | 小修改 | Bug-13 |
| `web/app.py` | 中等修改 | Bug-11, 20 |
| `cli.py` | 小修改 | Bug-24 |
| `data/skill_registry.json` | 数据迁移 | Bug-5, 19 |
| `tests/test_skills_routing.py` | 修改断言 + 新增 | Bug-3, 4, 6, 16 |
| `tests/test_memory.py` | **新增** | Bug-9, 17 |
| `tests/test_skill_registry.py` | **新增** | Bug-5, 9, 17 |
| `tests/test_skill_creator_security.py` | **新增** | Bug-1, 10, 28 |
| `tests/test_skill_evaluator_dimensions.py` | **新增** | Bug-7, 8, 28 |
| `tests/test_sandbox_async.py` | **新增** | Bug-2 |
| `README.md` | 文档校正 | arxiv 引用, 沙箱宣传, 对比表, 已知限制 |
| `.trae/specs/synapse-memory/spec.md` | spec 修订 | mem0 决策说明 |
| `.trae/specs/synapse-more-skills/spec.md` | spec 修订 | GNews→RSS, JSON 数组 |
| `.trae/specs/*/tasks.md` | 文档对齐 | 7 个 spec 的 tasks 勾选 |

---

## 风险与回滚

- **风险 1**:Bug-9 的锁可能引入死锁(若 `_save` 在已持锁时被调用)。**缓解**:用 `RLock` 或拆分 `_save_locked` 内部方法,加单元测试覆盖嵌套调用。
- **风险 2**:Bug-2 的 `execute_async` 改动可能影响测试 mock。**缓解**:`test_skills_routing.py` 第 20 行 `r.sandbox = None` 已禁用沙箱,且 router 用 `if skill.use_sandbox and self.sandbox is not None` 判断,改为 `await self.sandbox.execute_async(...)` 时需检查 sandbox 是否为 None。保留向后兼容的 `execute` 同步方法。
- **风险 3**:Bug-19 移除 `health_score` 字段可能破坏依赖该字段的代码。**缓解**:全代码搜索仅 `generate_improvement_report` 使用,且那里是实时计算 `score = self.evaluate(skill_name)`,不读 `health_score` 字段。安全。
- **风险 4**:Bug-15 移除 `WeatherArgs.date` 字段可能破坏 `test_weather_skill_execution`(第 71/83 行传了 `date`)。**缓解**:同步更新测试。

---

## 不做的事(明确边界)

- ❌ 不引入 `mem0`、`aiosqlite`、`bandit` 等新依赖
- ❌ 不重写 `route()` deprecated 方法
- ❌ 不实现技能 embedding 检索(范围 B)
- ❌ 不迁移 SQLite(范围 B,本次用 `threading.Lock` 解决并发)
- ❌ 不添加 Docker 沙箱后端(范围 C)
- ❌ 不添加 SkillOpt/SkillLens 学术叙事对齐(范围 C)
- ❌ 不实现多 tool_calls 并行执行(只加 warning)
- ❌ 不实现 WeatherSkill 的 daily 预报(只移除误导性 date 参数)
- ❌ 不重写技能评估架构(只修正现有维度逻辑)

---

## 执行顺序

1. 阶段 1(安全)→ 2. 阶段 2(正确性)→ 3. 阶段 3(评估)→ 4. 阶段 4(可靠性)→ 5. 阶段 5(skill 修正)→ 6. 阶段 6(工程化)→ 7. 阶段 7(spec 文档)→ 8. 阶段 8(测试)→ 9. 阶段 9(README)

实际上,阶段 8 的测试应**穿插在每个阶段后写**(TDD 风格),最后统一跑一次全测试。

每改一个 bug,立即跑相关测试验证。最后跑全测试 + 手工验证 + 静态检查。
