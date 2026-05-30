# Synapse 改进 Spec

## Why

Synapse 是一个具有自进化（Meta-Evolution）能力的 AI Agent 架构，核心概念很有前瞻性，但当前实现存在多个 bug 和工程缺陷：模块热重载失效、文件名安全过滤不严谨、缺乏日志系统、示例技能是 Mock 数据、空的 `__init__.py` 导致 API 不友好等。这些问题让项目无法在生产环境使用，也降低了新用户的上手体验。

## What Changes

- **修复 Bug**: `importlib.import_module` 缓存导致新技能无法热重载
- **修复 Bug**: `safe_filename` 过滤逻辑误删合法字符且无法阻止路径遍历
- **修复 Bug**: `process_query` 中 `_is_retry` 参数命名不规范（下划线前缀通常表示未使用/私有）
- **增强工程化**: 添加 `logging` 日志系统替代 `print`
- **增强工程化**: 填充所有 `__init__.py`，导出公共 API
- **增强示例**: 将 `WeatherSkill` 改为调用真实天气 API（使用 Open-Meteo 免费 API，无需 API Key）
- **增强可用性**: 添加 `.env.example` 和 `cli.py` 入口脚本
- **增强健壮性**: `BaseSkill` 添加默认参数校验方法 `validate_args`

## Impact

- Affected specs: 技能自动发现、Meta-Evolution 生成技能、LLM 路由、技能执行
- Affected code:
  - `core/base.py` — 添加 `validate_args` 默认实现
  - `router/router.py` — 修复热重载、添加日志、规范参数命名
  - `meta/skill_creator.py` — 修复文件名安全、添加日志
  - `skills/weather_skill.py` — 替换为真实天气 API 调用
  - `core/__init__.py`, `router/__init__.py`, `skills/__init__.py`, `meta/__init__.py` — 导出公共 API
  - `tests/` — 更新测试以适配改动
  - 新增 `.env.example`
  - 新增 `cli.py`

## ADDED Requirements

### Requirement: 模块热重载

The system SHALL 在 `_discover_skills` 中正确处理 `importlib` 缓存，使得运行中生成的新技能文件能够被加载，已修改的技能文件能够被刷新。

#### Scenario: 新技能生成后自动加载
- **WHEN** `meta.skill_creator` 生成一个新的技能文件到 `skills/` 目录
- **THEN** `SkillRouter._discover_skills()` 能够正确加载该新模块，无需重启进程

#### Scenario: 已存在模块的刷新
- **WHEN** `skills/` 目录中某个技能文件被修改
- **THEN** 下次调用 `_discover_skills()` 时，该模块被重新加载，使用最新代码

### Requirement: 文件名安全校验

The system SHALL 对 LLM 生成的文件名进行严格的安全校验，防止路径遍历攻击，同时保留合法字符（如连字符 `-`）。

#### Scenario: 路径遍历攻击防护
- **WHEN** LLM 生成的文件名包含 `../` 或绝对路径
- **THEN** 系统提取 `basename` 并拒绝包含路径分隔符的文件名

#### Scenario: 合法文件名保留连字符
- **WHEN** LLM 生成的文件名为 `crypto-price-skill.py`
- **THEN** 文件名被保留为 `crypto-price-skill.py`，不会变成 `cryptopriceskill.py`

### Requirement: 日志系统

The system SHALL 使用 Python 标准库 `logging` 模块替代所有 `print` 语句，支持不同日志级别。

#### Scenario: 运行时日志输出
- **WHEN** 系统执行技能路由、Meta-Evolution、技能发现等操作
- **THEN** 输出结构化日志，包含级别（INFO/WARNING/ERROR）、模块名、消息

### Requirement: 公共 API 导出

The system SHALL 在所有 `__init__.py` 中导出公共类和函数，使得用户可以通过 `from core import BaseSkill` 等方式导入。

#### Scenario: 简化导入路径
- **WHEN** 用户写 `from core import BaseSkill`
- **THEN** 成功导入 `BaseSkill`
- **WHEN** 用户写 `from router import SkillRouter`
- **THEN** 成功导入 `SkillRouter`

### Requirement: 真实天气 API 示例

The system SHALL 将 `WeatherSkill` 从 Mock 数据改为调用真实的 Open-Meteo 免费天气 API。

#### Scenario: 查询真实天气
- **WHEN** 用户调用 `WeatherSkill.execute(location="Beijing")`
- **THEN** 返回北京市的实时天气数据（温度、天气状况等）
- **AND** 如果 API 调用失败，返回友好的错误信息

### Requirement: CLI 入口

The system SHALL 提供 `cli.py` 命令行入口，允许用户直接运行交互式会话。

#### Scenario: 交互式运行
- **WHEN** 用户执行 `python cli.py`
- **THEN** 启动交互式循环，接收用户输入，调用 `SkillRouter.process_query`，输出结果
- **AND** 输入 `exit` 或 `quit` 时退出

### Requirement: BaseSkill 默认参数校验

The system SHALL 在 `BaseSkill` 中提供 `validate_args` 方法，自动完成 `expected_args(**kwargs)` 的校验逻辑。

#### Scenario: 子类复用校验逻辑
- **WHEN** 子类调用 `self.validate_args(**kwargs)`
- **THEN** 返回校验后的 Pydantic 模型实例
- **AND** 子类 `execute` 方法不再需要重复写 `args = self.expected_args(**kwargs)`

## MODIFIED Requirements

### Requirement: SkillRouter.process_query 参数命名

**原实现**: 使用 `_is_retry` 作为参数名，以下划线开头暗示未使用/私有。

**修改后**: 参数名改为 `is_retry`，并在 docstring 中说明其用途。下划线前缀仅用于内部方法或真正未使用的变量。

## REMOVED Requirements

无移除需求。
