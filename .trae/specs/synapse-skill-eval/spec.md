# Synapse 技能评估与反馈闭环 Spec

## Why

当前 Meta-Evolution 只会生成新技能，但从不评估已有技能的质量。这导致：
1. 生成的技能可能根本不可用（代码有 bug、API 调用错误等）
2. 相似技能重复生成，造成冗余
3. 没有反馈机制告诉 Meta-Evolution 如何改进

技能评估闭环让系统能够自我诊断、自我优化，真正实现「自进化」。

## What Changes

- **新增 SkillEvaluator 模块**: 在 `meta/` 下添加 `skill_evaluator.py`
- **新增 SkillRegistry 模块**: 在 `core/` 下添加 `skill_registry.py`，管理技能的元数据（评分、使用次数、错误率等）
- **修改 SkillRouter**: 在技能执行后记录执行结果（成功/失败）到 Registry
- **修改 SkillCreator**: 生成新技能前检查 Registry，避免重复生成；生成后自动触发评估
- **新增测试**: 覆盖评估逻辑、Registry 操作

## Impact

- Affected specs: Meta-Evolution、技能路由、技能执行
- Affected code:
  - `core/skill_registry.py` — 新增
  - `meta/skill_evaluator.py` — 新增
  - `router/router.py` — 记录执行结果
  - `meta/skill_creator.py` — 集成 Registry 和 Evaluator
  - `tests/test_skill_eval.py` — 新增

## ADDED Requirements

### Requirement: 技能注册表

The system SHALL 提供 `SkillRegistry` 类，持久化存储每个技能的元数据：名称、描述、创建时间、使用次数、成功次数、失败次数、平均执行时间、最后一次错误信息。

#### Scenario: 技能元数据记录
- **WHEN** 一个技能被创建或执行
- **THEN** 其元数据被更新到 `SkillRegistry`

### Requirement: 技能执行结果记录

The system SHALL 在每次技能执行后，自动记录执行结果到 `SkillRegistry`。

#### Scenario: 成功与失败记录
- **WHEN** 技能执行成功
- **THEN** `success_count` +1，`avg_execution_time` 更新
- **WHEN** 技能执行失败
- **THEN** `failure_count` +1，`last_error` 记录错误信息

### Requirement: 技能质量评估

The system SHALL 提供 `SkillEvaluator` 类，定期（或按需）评估技能质量：
- 计算成功率（success_rate = success / total）
- 识别低质量技能（成功率 < 50%）
- 生成改进建议

#### Scenario: 低质量技能识别
- **WHEN** 某个技能的成功率低于 50%
- **THEN** `SkillEvaluator` 将其标记为 `needs_improvement`，并生成报告

### Requirement: 避免重复生成

The system SHALL 在 Meta-Evolution 触发前，检查是否已有相似技能存在（基于名称或描述相似度）。

#### Scenario: 相似技能检测
- **WHEN** 用户请求"查股价"，但已有 `stock_price_skill`
- **THEN** 系统优先使用现有技能，而不是生成新的

### Requirement: 自动改进触发

The system SHALL 在检测到低质量技能时，自动触发 Meta-Evolution 重新生成该技能。

#### Scenario: 自动修复坏技能
- **WHEN** `weather_skill` 连续失败 3 次
- **THEN** 系统自动触发 `SkillCreator` 重新生成 `weather_skill`

## MODIFIED Requirements

无

## REMOVED Requirements

无
