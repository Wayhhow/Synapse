# Tasks

- [x] Task 1: 创建网页搜索技能（核心，优先级最高）
  - [x] SubTask 1.1: 在 `requirements.txt` 中添加 `duckduckgo-search>=4.0.0`
  - [x] SubTask 1.2: 创建 `skills/web_search_skill.py`，使用 `duckduckgo_search` 异步搜索
  - [x] SubTask 1.3: 返回搜索结果列表（标题、摘要、链接）
  - [x] SubTask 1.4: 处理 API 失败场景
  - [x] SubTask 1.5: 运行 `pytest tests/test_skills_url_encoding.py -v` (URL 编码集成测试覆盖)

- [x] Task 2: 创建数据分析技能（核心，优先级最高）
  - [x] SubTask 2.1: 创建 `skills/data_analysis_skill.py`
  - [x] SubTask 2.2: 支持输入逗号分隔的数据或 JSON 数组 **(Bug-14 fix: 修复后真正支持 JSON 数组)**
  - [x] SubTask 2.3: 计算描述性统计（均值、中位数、标准差、最大值、最小值）
  - [x] SubTask 2.4: 纯本地计算，不依赖外部 API
  - [x] SubTask 2.5: 集成测试覆盖 (见 `tests/test_skills_routing.py`)

- [x] Task 3: 创建计算器技能
  - [x] SubTask 3.1: 创建 `skills/calculator_skill.py`
  - [x] SubTask 3.2: 使用 `ast` 安全解析数学表达式
  - [x] SubTask 3.3: 禁止危险操作
  - [x] SubTask 3.4: 集成测试覆盖

- [x] Task 4: 创建翻译技能
  - [x] SubTask 4.1: 创建 `skills/translation_skill.py`，调用 MyMemory 免费 API
  - [x] SubTask 4.2: 处理 API 失败场景
  - [x] SubTask 4.3: 运行 `pytest tests/test_skills_url_encoding.py -v` (URL 编码集成测试覆盖)

- [x] Task 5: 创建新闻技能
  - [x] SubTask 5.1: 创建 `skills/news_skill.py`，~~调用 GNews 免费 API~~ **(决策修订: 改用 Google News RSS, 见下方"决策记录")**
  - [x] SubTask 5.2: 处理 API 失败场景 (HTTP 错误、网络错误、XML 解析错误)
  - [x] SubTask 5.3: 运行 `pytest tests/test_skills_url_encoding.py -v` (URL 编码集成测试覆盖)

- [x] Task 6: 更新导出和集成测试
  - [x] SubTask 6.1: 更新 `skills/__init__.py` 导出所有新增技能
  - [x] SubTask 6.2: 运行 `pytest tests/ -v` 确保全部测试通过

# 决策记录: 新闻技能为何从 GNews 改为 Google News RSS
原始 spec 计划调用 GNews 免费 API。实现阶段经调研后改用 Google News RSS (`https://news.google.com/rss/search?q=...`),理由如下:
- **零 Key 零注册**: GNews "免费"档仍要求在 gnews.io 注册获取 API key,且有每日请求上限。Google News RSS 完全匿名,无需任何注册,真正开箱即用,与项目"零配置"理念一致。
- **稳定性**: GNews 是第三方包装服务,历史上有过下线/限流变动;Google News RSS 是 Google 一等公民端点,可用性更高。
- **数据同等**: RSS 同样返回标题 + 链接,足以支撑"最新新闻"用例;若未来需要正文摘要,再评估升级到带 key 的 API。
- **依赖更轻**: 不需要 `gnews` 这个非主流第三方包,标准库 `xml.etree.ElementTree` + `httpx` 已足够。
- 详见 `synapse-more-skills/spec.md` 中的"Decision Log"修订。

# 额外完成(实现过程中发现并修复)
- [x] Bug-13: Calculator 添加表达式长度上限(≤200 字符)和指数右操作数上限(≤1e6),堵住 `2**99999999` 类 DoS
- [x] Bug-14: DataAnalysis 优先尝试 JSON 数组解析,失败再回退到逗号分隔,真正支持 spec 要求的 `[1,2,3]` 输入
- [x] Bug-15: Weather 移除未使用的 `date` 参数,description 诚实声明仅支持当前天气
- [x] Bug-6 (URL): Translation / News 用 `urllib.parse.quote` 编码 query,避免 `&`/`#`/空格破坏 URL

# Task Dependencies

- Task 1、2 优先级最高，可以并行
- Task 3、4、5 互相独立，可以并行
- Task 6 依赖 Task 1-5
