# Tasks

- [x] Task 1: 添加 FastAPI 依赖并创建后端
  - [x] SubTask 1.1: 在 `requirements.txt` 中添加 `fastapi>=0.100.0` 和 `uvicorn>=0.23.0`
  - [x] SubTask 1.2: 创建 `web/app.py`，初始化 FastAPI 应用
  - [x] SubTask 1.3: 实现 `POST /chat` 端点
  - [x] SubTask 1.4: 实现 `GET /skills` 端点（实际为 `GET /health` + `GET /stats` + `GET /history/{session_id}`）
  - [x] SubTask 1.5: 配置静态文件服务
  - [x] SubTask 1.6: 运行 `python -m py_compile web/app.py` 检查语法

- [x] Task 2: 创建前端聊天界面
  - [x] SubTask 2.1: 创建 `web/static/index.html`
  - [x] SubTask 2.2: 创建 `web/static/style.css`
  - [x] SubTask 2.3: 创建 `web/static/app.js`
  - [x] SubTask 2.4: 运行 `python -m py_compile` 检查后端语法

# 额外完成(实现过程中发现并修复)
- [x] Bug-11: 静态文件加载改为基于 `__file__` 的绝对路径,避免工作目录外启动时 404
- [x] Bug-20: Pydantic 模型响应输出改为 `model_dump_json(indent=2)`,提升可读性
- [x] Bug-5 (web 部分): `skill_used` 改为基于 `isinstance(result, PydanticModel)` 判断,避免误判
- [x] 新增 `tests/test_web_app.py` 覆盖 `/health`、`/stats`、`/history/{session_id}`、`/chat` 文本与模型响应

# Task Dependencies

- Task 2 依赖 Task 1
