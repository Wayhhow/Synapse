# Tasks

- [ ] Task 1: 创建计算器技能
  - [ ] SubTask 1.1: 创建 `skills/calculator_skill.py`
  - [ ] SubTask 1.2: 使用 `ast` 安全解析数学表达式
  - [ ] SubTask 1.3: 支持 `+ - * / ** ()` 等基本运算
  - [ ] SubTask 1.4: 禁止危险操作（如函数调用、属性访问）
  - [ ] SubTask 1.5: 运行 `pytest tests/test_calculator_skill.py -v`

- [ ] Task 2: 创建翻译技能
  - [ ] SubTask 2.1: 调研免费翻译 API（MyMemory / LibreTranslate）
  - [ ] SubTask 2.2: 创建 `skills/translation_skill.py`，使用 `httpx` 异步调用
  - [ ] SubTask 2.3: 处理 API 失败场景
  - [ ] SubTask 2.4: 运行 `pytest tests/test_translation_skill.py -v`

- [ ] Task 3: 创建股票查询技能
  - [ ] SubTask 3.1: 调研免费股票 API（Yahoo Finance 替代方案）
  - [ ] SubTask 3.2: 创建 `skills/stock_skill.py`，使用 `httpx` 异步调用
  - [ ] SubTask 3.3: 处理 API 失败场景
  - [ ] SubTask 3.4: 运行 `pytest tests/test_stock_skill.py -v`

- [ ] Task 4: 创建新闻查询技能
  - [ ] SubTask 4.1: 调研免费新闻 API（NewsAPI / GNews）
  - [ ] SubTask 4.2: 创建 `skills/news_skill.py`，使用 `httpx` 异步调用
  - [ ] SubTask 4.3: 处理 API 失败场景
  - [ ] SubTask 4.4: 运行 `pytest tests/test_news_skill.py -v`

- [ ] Task 5: 更新 skills/__init__.py 和集成测试
  - [ ] SubTask 5.1: 更新 `skills/__init__.py` 导出新增技能
  - [ ] SubTask 5.2: 运行 `pytest tests/ -v` 确保全部测试通过

# Task Dependencies

- Task 1 不依赖其他任务，可以最先完成
- Task 2、3、4 互相独立，可以并行
- Task 5 依赖 Task 1-4
