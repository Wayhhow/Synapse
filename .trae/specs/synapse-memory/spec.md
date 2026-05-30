# Synapse 对话记忆系统 Spec

## Why

当前 Synapse 的每次请求都是独立的，Agent 无法记住之前的对话内容。LightAgent 框架已验证 Memory + Tool Generator 架构的有效性，mem0 库提供了成熟的对话记忆方案。直接整合 mem0 而非自己实现记忆存储。

## What Changes

- **整合 mem0 库**: 使用 mem0 作为对话记忆后端，替代自研 Memory 模块
- **修改 SkillRouter**: `process_query` 接收可选的 `session_id`（即 mem0 的 user_id），自动加载历史并注入 LLM messages
- **修改 CLI**: `cli.py` 支持 session 管理
- **新增测试**: 覆盖记忆注入逻辑

## Impact

- Affected code:
  - `requirements.txt` — 添加 `mem0ai>=0.1.0`
  - `router/router.py` — `process_query` 注入历史上下文
  - `cli.py` — 支持 session
  - `tests/test_memory.py` — 新增

## ADDED Requirements

### Requirement: 基于 mem0 的对话记忆

The system SHALL 使用 mem0 库管理对话历史，按 `session_id`（user_id）存储和检索消息。

#### Scenario: 存储与检索对话
- **WHEN** Agent 完成一次交互
- **THEN** 调用 `mem0.add(msg, user_id=session_id)` 存储消息
- **WHEN** 处理新请求时
- **THEN** 调用 `mem0.get_all(user_id=session_id)` 获取历史，注入 LLM messages

### Requirement: 记忆容量管理

The system SHALL 限制注入 LLM 的历史消息轮数（默认 10 轮），防止上下文窗口溢出。

### Requirement: CLI Session 支持

The system SHALL 在 `cli.py` 中为每个运行实例生成唯一的 `session_id`。

## MODIFIED Requirements

无

## REMOVED Requirements

无
