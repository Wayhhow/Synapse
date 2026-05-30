# Synapse 技能执行沙箱 Spec

## Why

LLM 生成的技能代码直接在主进程执行有安全风险。使用 Python 标准库 `multiprocessing` 实现进程级隔离，参考 LightAgent 的轻量级设计哲学——不引入 Docker 等重量级依赖，保持 Synapse 的轻量特性。

## What Changes

- **新增 Sandbox 模块**: `core/sandbox.py`，使用 `multiprocessing` + `timeout` 实现隔离执行
- **修改 BaseSkill**: 添加 `use_sandbox` 属性
- **修改 SkillRouter**: 新技能默认沙箱执行

## Impact

- Affected code:
  - `core/sandbox.py` — 新增
  - `core/base.py` — 添加 `use_sandbox` 属性
  - `router/router.py` — 集成沙箱执行
  - `tests/test_sandbox.py` — 新增

## ADDED Requirements

### Requirement: 进程级沙箱隔离

The system SHALL 使用 `multiprocessing.Process` 在子进程中执行技能，通过 `Queue` 返回结果。

#### Scenario: 异常隔离
- **WHEN** 技能抛出未捕获异常
- **THEN** 主进程捕获错误并返回失败信息，不受影响

### Requirement: 执行超时控制

The system SHALL 对沙箱执行设置超时（默认 10 秒），超时后 `terminate()` 子进程。

### Requirement: 沙箱配置开关

The system SHALL 提供 `use_sandbox` 属性（默认 True），允许关闭沙箱。

## MODIFIED Requirements

无

## REMOVED Requirements

无
