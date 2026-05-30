# Synapse Web UI Spec

## Why

当前只有 CLI 入口。使用 FastAPI + 原生 HTML/CSS/JS 构建轻量 Web UI，参考 OpenManus 的简洁交互设计。

## What Changes

- **新增 FastAPI 后端**: `web/app.py`，提供 RESTful API
- **新增前端页面**: 原生 HTML/CSS/JS 聊天界面
- **修改 requirements.txt**: 添加 `fastapi` 和 `uvicorn`

## Impact

- Affected code:
  - `web/app.py` — 新增
  - `web/static/index.html` — 新增
  - `web/static/style.css` — 新增
  - `web/static/app.js` — 新增
  - `requirements.txt` — 添加依赖

## ADDED Requirements

### Requirement: FastAPI 后端

The system SHALL 提供基于 FastAPI 的 HTTP 服务：
- `POST /chat` — 发送消息，返回 Agent 回复
- `GET /skills` — 列出所有技能
- `GET /` — 返回前端页面

### Requirement: 聊天前端

The system SHALL 提供聊天界面，支持输入消息、显示回复、显示使用的技能、多轮对话。

## MODIFIED Requirements

无

## REMOVED Requirements

无
