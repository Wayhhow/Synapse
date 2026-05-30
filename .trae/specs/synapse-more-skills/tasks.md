# Tasks

- [ ] Task 1: 创建网页搜索技能（核心，优先级最高）
  - [ ] SubTask 1.1: 在 `requirements.txt` 中添加 `duckduckgo-search>=4.0.0`
  - [ ] SubTask 1.2: 创建 `skills/web_search_skill.py`，使用 `duckduckgo_search` 异步搜索
  - [ ] SubTask 1.3: 返回搜索结果列表（标题、摘要、链接）
  - [ ] SubTask 1.4: 处理 API 失败场景
  - [ ] SubTask 1.5: 运行 `pytest tests/test_web_search_skill.py -v`

- [ ] Task 2: 创建数据分析技能（核心，优先级最高）
  - [ ] SubTask 2.1: 创建 `skills/data_analysis_skill.py`
  - [ ] SubTask 2.2: 支持输入逗号分隔的数据或 JSON 数组
  - [ ] SubTask 2.3: 计算描述性统计（均值、中位数、标准差、最大值、最小值）
  - [ ] SubTask 2.4: 纯本地计算，不依赖外部 API
  - [ ] SubTask 2.5: 运行 `pytest tests/test_data_analysis_skill.py -v`

- [ ] Task 3: 创建计算器技能
  - [ ] SubTask 3.1: 创建 `skills/calculator_skill.py`
  - [ ] SubTask 3.2: 使用 `ast` 安全解析数学表达式
  - [ ] SubTask 3.3: 禁止危险操作
  - [ ] SubTask 3.4: 运行 `pytest tests/test_calculator_skill.py -v`

- [ ] Task 4: 创建翻译技能
  - [ ] SubTask 4.1: 创建 `skills/translation_skill.py`，调用 MyMemory 免费 API
  - [ ] SubTask 4.2: 处理 API 失败场景
  - [ ] SubTask 4.3: 运行 `pytest tests/test_translation_skill.py -v`

- [ ] Task 5: 创建新闻技能
  - [ ] SubTask 5.1: 创建 `skills/news_skill.py`，调用 GNews 免费 API
  - [ ] SubTask 5.2: 处理 API 失败场景
  - [ ] SubTask 5.3: 运行 `pytest tests/test_news_skill.py -v`

- [ ] Task 6: 更新导出和集成测试
  - [ ] SubTask 6.1: 更新 `skills/__init__.py` 导出所有新增技能
  - [ ] SubTask 6.2: 运行 `pytest tests/ -v` 确保全部测试通过

# Task Dependencies

- Task 1、2 优先级最高，可以并行
- Task 3、4、5 互相独立，可以并行
- Task 6 依赖 Task 1-5
