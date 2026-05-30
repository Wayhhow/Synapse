# Tasks

- [ ] Task 1: 添加 FastAPI 依赖并创建后端
  - [ ] SubTask 1.1: 在 `requirements.txt` 中添加 `fastapi>=0.100.0` 和 `uvicorn>=0.23.0`
  - [ ] SubTask 1.2: 创建 `web/app.py`，初始化 FastAPI 应用
  - [ ] SubTask 1.3: 实现 `POST /chat` 端点，调用 `SkillRouter.process_query`
  - [ ] SubTask 1.4: 实现 `GET /skills` 端点，返回技能列表
  - [ ] SubTask 1.5: 实现 `POST /skills/{name}/execute` 端点，直接执行技能
  - [ ] SubTask 1.6: 配置静态文件服务，提供前端页面
  - [ ] SubTask 1.7: 运行 `python -m py_compile web/app.py` 检查语法

- [ ] Task 2: 创建前端聊天界面
  - [ ] SubTask 2.1: 创建 `web/static/index.html`，包含聊天界面结构
  - [ ] SubTask 2.2: 创建 `web/static/style.css`，美化界面
  - [ ] SubTask 2.3: 创建 `web/static/app.js`，实现前端逻辑（发送消息、接收回复、显示技能标签）
  - [ ] SubTask 2.4: 手动测试 `uvicorn web.app:app --reload` 并访问 `http://localhost:8000`

# Task Dependencies

- Task 2 依赖 Task 1
