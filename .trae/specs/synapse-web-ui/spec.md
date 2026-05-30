# Synapse Web UI Spec

## Why

当前 Synapse 只有 CLI 入口，非技术用户难以使用。一个简洁的 Web UI 可以让更多人体验这个自进化 Agent，也是展示项目能力的重要窗口。

## What Changes

- **新增 Web 服务**: 使用 `fastapi` + `uvicorn` 提供 HTTP API
- **新增前端页面**: 使用原生 HTML/CSS/JS（不引入复杂前端框架），实现聊天界面
- **新增 API 端点**:
  - `POST /chat` — 发送消息，返回 Agent 回复
  - `GET /skills` — 列出所有技能
  - `POST /skills/{name}/execute` — 直接执行某个技能
  - `GET /` — 返回前端页面
- **修改 requirements.txt**: 添加 `fastapi` 和 `uvicorn`

## Impact

- Affected specs: 项目入口、依赖管理
- Affected code:
  - `web/app.py` — 新增 FastAPI 应用
  - `web/static/index.html` — 新增前端页面
  - `web/static/style.css` — 新增样式
  - `web/static/app.js` — 新增前端逻辑
  - `requirements.txt` — 添加依赖

## ADDED Requirements

### Requirement: FastAPI 后端

The system SHALL 提供基于 FastAPI 的 HTTP 服务，暴露 RESTful API。

#### Scenario: 发送聊天消息
- **WHEN** 客户端 POST `{"message": "北京天气怎么样", "session_id": "abc123"}` 到 `/chat`
- **THEN** 返回 `{"reply": "...", "skill_used": "weather_skill"}`

#### Scenario: 列出技能
- **WHEN** 客户端 GET `/skills`
- **THEN** 返回所有已注册技能的列表（名称、描述）

### Requirement: 聊天前端页面

The system SHALL 提供简洁的聊天界面，支持：
- 用户输入消息
- 显示 Agent 回复
- 显示使用了哪个技能
- 支持多轮对话（基于 session_id）

#### Scenario: Web 聊天交互
- **WHEN** 用户打开 `http://localhost:8000/`
- **THEN** 看到聊天界面，可以输入消息并看到回复

### Requirement: 实时更新（可选）

The system SHALL 支持 Server-Sent Events (SSE) 流式输出 LLM 回复（如果模型支持）。

#### Scenario: 流式回复
- **WHEN** Agent 生成长回复
- **THEN** 用户看到文字逐字出现，而不是等待全部生成完

## MODIFIED Requirements

无

## REMOVED Requirements

无
