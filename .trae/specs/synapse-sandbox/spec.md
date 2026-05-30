# Synapse 技能执行沙箱 Spec

## Why

当前 Meta-Evolution 生成的技能代码直接在主进程中执行，没有任何隔离机制。如果 LLM 生成了恶意代码（如删除文件、网络攻击、资源耗尽等），将直接危害宿主系统。沙箱机制是生产环境部署的必备安全防线。

## What Changes

- **新增 Sandbox 模块**: 在 `core/` 下添加 `sandbox.py`，提供技能代码的隔离执行环境
- **修改 BaseSkill**: 可选支持在沙箱中执行（通过配置开关）
- **修改 SkillRouter**: 在 `process_query` 中，对 Meta-Evolution 生成的新技能默认启用沙箱执行
- **新增测试**: 覆盖沙箱隔离、超时控制、资源限制

## Impact

- Affected specs: 技能执行、Meta-Evolution
- Affected code:
  - `core/sandbox.py` — 新增
  - `core/base.py` — 可选沙箱执行支持
  - `router/router.py` — 新技能默认沙箱执行
  - `tests/test_sandbox.py` — 新增

## ADDED Requirements

### Requirement: 进程级沙箱隔离

The system SHALL 使用 Python 的 `multiprocessing` 模块在独立进程中执行技能代码，与主进程隔离。

#### Scenario: 技能代码异常不影响主进程
- **WHEN** 某个技能执行时抛出未捕获异常或死循环
- **THEN** 主进程不受影响，能够优雅地捕获错误并返回失败信息

### Requirement: 执行超时控制

The system SHALL 对沙箱中的技能执行设置超时（默认 10 秒），超时后强制终止子进程。

#### Scenario: 技能死循环被终止
- **WHEN** 某个技能进入无限循环
- **THEN** 10 秒后子进程被强制终止，返回超时错误

### Requirement: 资源限制（可选）

The system SHALL 支持配置 CPU 时间限制和内存限制（通过 `resource` 模块，Linux only）。

#### Scenario: 资源耗尽型攻击防护
- **WHEN** 某个技能尝试分配大量内存或消耗大量 CPU
- **THEN** 子进程被限制在配置的资源范围内，超出时终止

### Requirement: 沙箱配置开关

The system SHALL 提供 `use_sandbox` 配置项（默认 True），允许在开发和测试环境中关闭沙箱以方便调试。

#### Scenario: 开发环境关闭沙箱
- **WHEN** 开发者设置 `use_sandbox=False`
- **THEN** 技能在主进程中直接执行，便于调试

## MODIFIED Requirements

无

## REMOVED Requirements

无
