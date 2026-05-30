# Tasks

- [ ] Task 1: 添加 FastAPI 依赖并创建后端
  - [ ] SubTask 1.1: 在 `requirements.txt` 中添加 `fastapi>=0.100.0` 和 `uvicorn>=0.23.0`
  - [ ] SubTask 1.2: 创建 `web/app.py`，初始化 FastAPI 应用
  - [ ] SubTask 1.3: 实现 `POST /chat` 端点
  - [ ] SubTask 1.4: 实现 `GET /skills` 端点
  - [ ] SubTask 1.5: 配置静态文件服务
  - [ ] SubTask 1.6: 运行 `python -m py_compile web/app.py` 检查语法

- [ ] Task 2: 创建前端聊天界面
  - [ ] SubTask 2.1: 创建 `web/static/index.html`
  - [ ] SubTask 2.2: 创建 `web/static/style.css`
  - [ ] SubTask 2.3: 创建 `web/static/app.js`
  - [ ] SubTask 2.4: 运行 `python -m py_compile` 检查后端语法

# Task Dependencies

- Task 2 依赖 Task 1
