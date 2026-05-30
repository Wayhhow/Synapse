# Synapse 真实可调用技能集 Spec

## Why

当前只有天气技能，项目单薄。用户特别要求技能都要能真正调用，尤其是搜索资料和分析类技能。整合免费开源 API，确保每个技能开箱即用。

## What Changes

- **新增搜索技能**: `skills/web_search_skill.py`，调用 DuckDuckGo 免费 API（无需 API Key）
- **新增分析技能**: `skills/data_analysis_skill.py`，本地 Python 执行数据分析（pandas 描述性统计）
- **新增计算器技能**: `skills/calculator_skill.py`，安全 AST 解析数学表达式
- **新增翻译技能**: `skills/translation_skill.py`，调用 MyMemory 免费 API
- **新增新闻技能**: `skills/news_skill.py`，调用 GNews 免费 API
- **修改 tests**: 为新增技能添加测试

## Impact

- Affected code:
  - `skills/web_search_skill.py` — 新增（核心！用户最需要的搜索能力）
  - `skills/data_analysis_skill.py` — 新增（核心！用户最需要的分析能力）
  - `skills/calculator_skill.py` — 新增
  - `skills/translation_skill.py` — 新增
  - `skills/news_skill.py` — 新增
  - `requirements.txt` — 添加 `duckduckgo-search>=4.0.0`
  - `tests/test_more_skills.py` — 新增

## ADDED Requirements

### Requirement: 网页搜索技能（核心）

The system SHALL 提供 `WebSearchSkill`，支持搜索互联网信息。

#### Scenario: 搜索资料
- **WHEN** 用户调用 `WebSearchSkill.execute(query="Python asyncio best practices")`
- **THEN** 返回搜索结果列表（标题、摘要、链接），使用 DuckDuckGo 免费 API，无需 API Key
- **AND** 如果 API 失败，返回友好的错误信息

### Requirement: 数据分析技能（核心）

The system SHALL 提供 `DataAnalysisSkill`，支持对 CSV 数据进行描述性统计分析。

#### Scenario: 分析数据
- **WHEN** 用户调用 `DataAnalysisSkill.execute(data="1,2,3,4,5", analysis_type="describe")`
- **THEN** 返回均值、中位数、标准差、最大值、最小值等统计信息
- **AND** 纯本地计算，不依赖外部 API

### Requirement: 计算器技能

The system SHALL 提供 `CalculatorSkill`，支持数学表达式计算，使用 AST 安全解析，禁止危险操作。

### Requirement: 翻译技能

The system SHALL 提供 `TranslationSkill`，调用 MyMemory 免费 API 翻译文本。

### Requirement: 新闻技能

The system SHALL 提供 `NewsSkill`，调用 GNews 免费 API 查询最新新闻。

## MODIFIED Requirements

无

## REMOVED Requirements

无
