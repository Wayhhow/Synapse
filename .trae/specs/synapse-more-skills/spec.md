# Synapse 更多真实技能示例 Spec

## Why

当前仓库只有一个天气技能，显得项目很单薄。添加多个实用的真实技能示例可以：
1. 展示 Synapse 的扩展能力
2. 为用户提供即开即用的功能
3. 让 Meta-Evolution 有更多参考模板

## What Changes

- **新增翻译技能**: `skills/translation_skill.py`，调用免费翻译 API
- **新增股票查询技能**: `skills/stock_skill.py`，调用免费股票 API
- **新增计算器技能**: `skills/calculator_skill.py`，纯本地计算，不依赖外部 API
- **新增新闻查询技能**: `skills/news_skill.py`，调用免费新闻 API
- **修改 tests**: 为新增技能添加测试

## Impact

- Affected specs: 技能库、自动发现
- Affected code:
  - `skills/translation_skill.py` — 新增
  - `skills/stock_skill.py` — 新增
  - `skills/calculator_skill.py` — 新增
  - `skills/news_skill.py` — 新增
  - `tests/test_more_skills.py` — 新增

## ADDED Requirements

### Requirement: 翻译技能

The system SHALL 提供 `TranslationSkill`，支持将文本翻译成指定语言。

#### Scenario: 翻译文本
- **WHEN** 用户调用 `TranslationSkill.execute(text="Hello", target_language="zh")`
- **THEN** 返回翻译后的文本（使用免费 API 如 MyMemory 或 LibreTranslate）

### Requirement: 股票查询技能

The system SHALL 提供 `StockSkill`，支持查询股票实时价格。

#### Scenario: 查询股价
- **WHEN** 用户调用 `StockSkill.execute(symbol="AAPL")`
- **THEN** 返回苹果公司的最新股价（使用免费 API 如 Yahoo Finance 或 Alpha Vantage）

### Requirement: 计算器技能

The system SHALL 提供 `CalculatorSkill`，支持数学表达式计算。

#### Scenario: 计算表达式
- **WHEN** 用户调用 `CalculatorSkill.execute(expression="2 + 2 * 3")`
- **THEN** 返回计算结果 `8`
- **AND** 使用 `ast` 安全解析表达式，禁止危险操作（如 `__import__`）

### Requirement: 新闻查询技能

The system SHALL 提供 `NewsSkill`，支持查询最新新闻。

#### Scenario: 查询新闻
- **WHEN** 用户调用 `NewsSkill.execute(query="technology", count=3)`
- **THEN** 返回 3 条科技相关新闻的标题和链接（使用免费 API 如 NewsAPI 或 GNews）

## MODIFIED Requirements

无

## REMOVED Requirements

无
