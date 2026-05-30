# Synapse 对话记忆系统 Spec

## Why

当前 Synapse 的每次请求都是独立的，Agent 无法记住之前的对话内容。这导致用户无法追问（"刚才说的那个城市天气怎么样？"），也无法进行多轮上下文相关的交互。对话记忆是 Agent 从「工具调用器」升级为「智能助手」的关键能力。

## What Changes

- **新增 Memory 模块**: 在 `core/` 下添加 `memory.py`，提供对话历史的存储、检索和格式化
- **修改 SkillRouter**: `process_query` 接收可选的 `session_id`，自动加载该会话的历史记录并注入到 LLM 的 messages 中
- **修改 CLI**: `cli.py` 支持基于 `session_id` 的多轮对话，用户可以在同一会话中连续提问
- **新增测试**: 覆盖记忆存储、检索、上下文注入

## Impact

- Affected specs: LLM 路由、CLI 交互
- Affected code:
  - `core/memory.py` — 新增
  - `router/router.py` — `process_query` 注入历史上下文
  - `cli.py` — 支持 session 管理
  - `tests/test_memory.py` — 新增

## ADDED Requirements

### Requirement: 记忆存储

The system SHALL 提供 `Memory` 类，能够按 `session_id` 存储用户和 Agent 的对话消息。

#### Scenario: 存储对话消息
- **WHEN** Agent 完成一次交互（用户输入 + Agent 回复）
- **THEN** 调用 `memory.add_message(session_id, role, content)` 将消息追加到该会话的历史中

### Requirement: 记忆检索

The system SHALL 在 `process_query` 时，根据传入的 `session_id` 自动检索该会话的历史消息，并将其注入到 LLM 的 `messages` 列表中。

#### Scenario: 多轮对话上下文
- **GIVEN** 用户在同一会话中先问"北京天气怎么样"，再问"那上海呢"
- **WHEN** 处理第二个问题时
- **THEN** LLM 收到的 messages 包含第一轮的用户输入和 Agent 回复，使 Agent 能理解"那上海呢"是指天气

### Requirement: 记忆容量管理

The system SHALL 支持配置记忆的最大轮数（默认 10 轮），超出时自动丢弃最早的消息，防止上下文窗口溢出。

#### Scenario: 长对话截断
- **WHEN** 一个会话的消息数量超过 `max_history` 配置
- **THEN** 最早的消息被移除，保留最近的消息

### Requirement: CLI Session 支持

The system SHALL 在 `cli.py` 中为每个运行实例生成唯一的 `session_id`，并在每次调用 `process_query` 时传递该 ID。

#### Scenario: CLI 多轮对话
- **WHEN** 用户在 CLI 中连续输入多个相关问题
- **THEN** Agent 能基于之前的对话内容理解追问

## MODIFIED Requirements

无

## REMOVED Requirements

无
