# Synapse Bug 修复与加固 Spec

## Why

Synapse 的 6 个前置 spec 已全部完成,8 个测试通过,但通读代码后发现**几个核心承诺在实现上是失效的**:沙箱静默失败被记为成功、棘轮机制因评估逻辑错误而永不触发、skill 注册名错配、meta-evolution retry 丢失会话上下文、Web UI 误报技能名、URL 未编码。这些问题让 README 宣传的关键能力(安全隔离、棘轮不倒退、多轮记忆)在真实运行时并不成立。本 spec 修复这些 bug,并补齐若干让项目更完整可用的工程化能力。

## What Changes

### Bug 修复
- **修复 Bug**: `Sandbox` 在超时/异常/空结果时返回空 `BaseModel()`,导致 `SkillRouter` 误记 `success=True` 且用户无报错
- **修复 Bug**: `SkillCreator` 棘轮机制失效——`evaluate()` 只读 stats,新代码未执行时 `new_score == old_score`,永不 revert
- **修复 Bug**: `SkillCreator` 用文件名注册 skill,与 `SkillRouter` 用 `skill.name` 注册不一致,导致棘轮查找 0 分
- **修复 Bug**: `SkillRouter.process_query` 在 meta-evolution retry 时丢弃 `session_id`,上下文断裂
- **修复 Bug**: `web/app.py` 的 `skill_used` 对文本响应返回 `"str"` 而非 `None`
- **修复 Bug**: `TranslationSkill` / `NewsSkill` 直接拼接 URL,未对 query 做 URL 编码

### 加固增强
- **增强评估**: `SkillEvaluator` 实现「结构质量」和「反模式」两个维度的真实代码检查(当前硬编码 20 / 15 分)
- **增强日志**: 在 `cli.py` 和 `web/app.py` 中配置 `logging.basicConfig`,让分散的 `logger` 调用真正输出
- **增强 Web API**: 新增 `GET /health`、`GET /stats`、`GET /history/{session_id}` 端点
- **增强 CLI**: `cli.py` 支持 `--skills` 参数列出已注册技能

## Impact

- Affected specs: synapse-sandbox(Sandbox 契约)、synapse-skill-eval(评估维度)、synapse-memory(history 暴露)、synapse-web-ui(新端点)
- Affected code:
  - `core/sandbox.py` — 失败时返回带 error 信息的可识别结果
  - `router/router.py` — 检测沙箱失败、retry 透传 session_id、记录失败
  - `meta/skill_creator.py` — 修复 skill_name、棘轮基于代码质量评估
  - `meta/skill_evaluator.py` — 实现真实结构/反模式检查
  - `web/app.py` — 修复 skill_used、新增端点、配置日志
  - `skills/translation_skill.py` — URL 编码
  - `skills/news_skill.py` — URL 编码
  - `cli.py` — 配置日志、`--skills` 参数
  - `tests/` — 新增覆盖 bug 修复的回归测试

## ADDED Requirements

### Requirement: 沙箱失败可识别

The system SHALL 在 `Sandbox` 超时、子进程异常或无结果时,返回一个可被 `SkillRouter` 识别为失败的结果(含 error 字段或抛出异常),而非空 `BaseModel()`。

#### Scenario: 沙箱超时被识别为失败
- **WHEN** 一个技能在沙箱中执行超时
- **THEN** `Sandbox.execute` 返回的结果被 `SkillRouter` 识别为失败
- **AND** `SkillRegistry.record_execution` 记录 `success=False` 并写入 error
- **AND** 用户收到包含错误信息的回复

#### Scenario: 沙箱子进程异常被识别为失败
- **WHEN** 技能在沙箱子进程中抛出异常
- **THEN** 异常信息透传回主进程,`SkillRouter` 记录失败并返回错误信息

### Requirement: 棘轮机制基于代码质量

The system SHALL 在 `SkillCreator` 生成新版本技能时,基于**代码本身的质量评估**(结构、反模式)与**运行时统计**综合对比新旧版本,新版本分数必须高于旧版本才替换。

#### Scenario: 新代码质量低于旧版本时回滚
- **WHEN** `SkillCreator` 为已存在的技能生成新版本
- **AND** 新代码的结构/反模式评分低于旧版本
- **THEN** 新文件被删除,旧文件保留,返回 `False`

#### Scenario: 新代码质量高于旧版本时替换
- **WHEN** 新代码的综合评分高于旧版本
- **THEN** 新文件保留,旧版本被覆盖,返回 `True`

### Requirement: 真实的 5 维度技能评估

The system SHALL 在 `SkillEvaluator` 中实现「结构质量」和「反模式检测」两个维度的真实代码检查,而非硬编码分数。

#### Scenario: 结构质量维度检查代码完整性
- **WHEN** 评估一个技能
- **THEN** 检查技能代码是否包含完整的 `name`、`description`、`expected_args`、`expected_response_type`、`execute` 定义
- **AND** 每缺失一项扣减对应分数

#### Scenario: 反模式维度检查危险操作
- **WHEN** 评估一个技能
- **THEN** 检查代码是否包含危险操作(`eval`、`exec`、`os.system`、`subprocess`、`__import__` 等)
- **AND** 检测到危险操作时扣减反模式分数

### Requirement: Web API 健康与状态端点

The system SHALL 提供以下只读端点用于运维和调试:

#### Scenario: 健康检查
- **WHEN** 访问 `GET /health`
- **THEN** 返回 `{"status": "ok", "skills_count": N}`

#### Scenario: 技能统计
- **WHEN** 访问 `GET /stats`
- **THEN** 返回所有技能的健康度评分和执行统计

#### Scenario: 会话历史
- **WHEN** 访问 `GET /history/{session_id}`
- **THEN** 返回该 session 的对话历史列表

### Requirement: 日志可见性

The system SHALL 在 CLI 和 Web 入口配置 `logging.basicConfig`,使所有模块的 `logger` 调用输出到 stderr。

#### Scenario: CLI 启动后日志可见
- **WHEN** 用户运行 `python cli.py`
- **THEN** 技能发现、路由、meta-evolution 等操作的 INFO/WARNING/ERROR 日志输出到控制台

### Requirement: CLI 列出技能

The system SHALL 支持 `python cli.py --skills` 列出所有已注册技能。

#### Scenario: 列出技能
- **WHEN** 用户执行 `python cli.py --skills`
- **THEN** 输出所有技能的 name 和 description,然后退出(不进入交互循环)

## MODIFIED Requirements

### Requirement: SkillRouter.process_query 透传 session_id

**原实现**: meta-evolution 触发后重试调用 `self.process_query(user_query, is_retry=True)`,丢失 `session_id`。

**修改后**: 重试时透传 `session_id`,保持会话上下文连续性。

### Requirement: Web ChatResponse.skill_used 类型识别

**原实现**: `skill_used = getattr(result, '__class__', None).__name__ if result else None`,文本响应返回 `"str"`。

**修改后**: 仅当 result 为 Pydantic BaseModel 实例时返回其类名,否则返回 `None`。

### Requirement: SkillCreator skill 注册名一致

**原实现**: `registry.register(safe_filename.replace('.py', ''), ...)`,用文件名做 key。

**修改后**: 通过加载新生成的模块获取 `skill.name`,用真实 skill name 注册,与 `SkillRouter` 保持一致。

### Requirement: Translation / News 技能 URL 编码

**原实现**: 直接 f-string 拼接 query 到 URL。

**修改后**: 使用 `urllib.parse.quote(query)` 对 query 部分编码,避免 `&`/`#`/空格破坏 URL。

## REMOVED Requirements

无移除需求。
