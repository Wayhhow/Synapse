# Synapse 真实可调用技能集 Spec

## Why

当前只有天气技能，项目单薄。用户特别要求技能都要能真正调用，尤其是搜索资料和分析类技能。整合免费开源 API，确保每个技能开箱即用。

## What Changes

- **新增搜索技能**: `skills/web_search_skill.py`，调用 DuckDuckGo 免费 API（无需 API Key）
- **新增分析技能**: `skills/data_analysis_skill.py`，本地 Python 执行数据分析（pandas 描述性统计）
- **新增计算器技能**: `skills/calculator_skill.py`，安全 AST 解析数学表达式
- **新增翻译技能**: `skills/translation_skill.py`，调用 MyMemory 免费 API
- **新增新闻技能**: `skills/news_skill.py`，~~调用 GNews 免费 API~~ **改为调用 Google News RSS**(见 Decision Log)
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

The system SHALL 提供 `NewsSkill`，调用 Google News RSS (`https://news.google.com/rss/search?q=...`) 查询最新新闻。

#### Scenario: 获取新闻
- **WHEN** 用户调用 `NewsSkill.execute(query="AI")`
- **THEN** 返回格式化的新闻列表（序号 + 标题 + 链接），使用 `xml.etree.ElementTree` 解析 RSS
- **AND** 如果 HTTP/网络/XML 解析失败，返回友好的错误信息

## MODIFIED Requirements

无

## REMOVED Requirements

无

## Decision Log

### 2026-07-26: 新闻技能从 GNews API 改为 Google News RSS

**背景**: 原 spec 计划调用 GNews 免费 API。实现阶段经调研后改用 Google News RSS (`https://news.google.com/rss/search?q=...`)。

**理由**:
1. **零 Key 零注册**: GNews "免费"档仍要求在 gnews.io 注册获取 API key,且有每日请求上限。Google News RSS 完全匿名,无需任何注册,真正开箱即用,与项目"零配置"理念一致。
2. **稳定性**: GNews 是第三方包装服务,历史上有过下线/限流变动;Google News RSS 是 Google 一等公民端点,可用性更高。
3. **数据同等**: RSS 同样返回标题 + 链接,足以支撑"最新新闻"用例;若未来需要正文摘要,再评估升级到带 key 的 API。
4. **依赖更轻**: 不需要 `gnews` 这个非主流第三方包,标准库 `xml.etree.ElementTree` + `httpx` 已足够。

**Bug-14 修订**: 数据分析技能的 spec 原本要求"支持输入逗号分隔的数据或 JSON 数组",但实现只支持逗号分隔。Bug-14 fix 后,`_parse_numbers` 优先尝试 JSON 数组解析,失败再回退到逗号分隔,真正支持 `[1,2,3]` 输入。

**验证**: `tests/test_skills_url_encoding.py` 覆盖 URL 编码;集成测试在 `tests/test_skills_routing.py` 中。
