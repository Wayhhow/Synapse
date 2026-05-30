# Synapse 技能评估与反馈闭环 Spec

## Why

当前 Meta-Evolution 只会生成新技能，从不评估质量。借鉴 darwin-skill 2.0 的 9 维度评估体系和棘轮机制（只保留改进、自动回滚退步），以及微软 SkillLens 论文的实证 rubric 设计，构建 Synapse 的自评估闭环。

## What Changes

- **新增 SkillRegistry**: `core/skill_registry.py`，JSON 持久化技能元数据（使用次数、成功率、错误信息）
- **新增 SkillEvaluator**: `meta/skill_evaluator.py`，借鉴 darwin-skill 的评估维度（简化为 5 维度：结构质量、执行成功率、错误处理、具体性、反模式），计算技能健康度
- **修改 SkillRouter**: 执行后记录结果到 Registry
- **修改 SkillCreator**: 生成前检查相似技能；低质量技能触发重新生成
- **棘轮机制**: 重新生成的技能必须比旧版本评分高才替换，否则回滚

## Impact

- Affected code:
  - `core/skill_registry.py` — 新增
  - `meta/skill_evaluator.py` — 新增
  - `router/router.py` — 记录执行结果
  - `meta/skill_creator.py` — 集成评估闭环
  - `tests/test_skill_eval.py` — 新增

## ADDED Requirements

### Requirement: 技能注册表

The system SHALL 提供 `SkillRegistry` 类，持久化存储技能元数据：名称、描述、使用次数、成功次数、失败次数、最后错误。

### Requirement: 技能健康度评估

The system SHALL 提供 `SkillEvaluator`，按 5 维度评估技能健康度（0-100分）：
1. 结构质量（20分）：是否有完整的 name/description/args/response
2. 执行成功率（30分）：success_count / total_count
3. 错误处理（20分）：是否有 error 字段和 fallback
4. 具体性（15分）：description 是否包含触发词
5. 反模式检测（15分）：是否包含危险操作黑名单

#### Scenario: 低质量技能识别
- **WHEN** 某技能健康度 < 50
- **THEN** 标记为 `needs_improvement`

### Requirement: 避免重复生成

The system SHALL 在 Meta-Evolution 触发前，检查已有技能的名称和描述相似度。

### Requirement: 棘轮机制

The system SHALL 在重新生成技能时，新版本必须比旧版本评分高才替换文件，否则保留旧版本。

#### Scenario: 技能改进验证
- **WHEN** `weather_skill` 被重新生成
- **THEN** 评估新版本分数，如果 > 旧版本则替换，否则丢弃新版本

## MODIFIED Requirements

无

## REMOVED Requirements

无
