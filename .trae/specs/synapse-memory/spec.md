# Synapse 对话记忆系统 Spec

## Why

当前 Synapse 的每次请求都是独立的，Agent 无法记住之前的对话内容。LightAgent 框架已验证 Memory + Tool Generator 架构的有效性。原 spec 计划整合 mem0 库,实现阶段经审查后改为自研轻量 Memory(理由见 Decision Log)。

## What Changes

- **实现自研 Memory 模块**: `core/memory.py` 提供 `Memory` 类,基于 `defaultdict(list)` + JSON 文件持久化,线程安全(`threading.RLock` + 临时文件原子写)
- **修改 SkillRouter**: `process_query` 接收可选的 `session_id`,自动从 `Memory` 加载历史并注入 LLM messages
- **修改 CLI**: `cli.py` 支持 session 管理 (每个运行实例生成唯一 `uuid4`)
- **新增测试**: 覆盖 add/get/clear/persist/session 隔离/并发/裸文件名场景

## Impact

- Affected code:
  - `core/memory.py` — 新增自研 Memory 类(替代原计划的 mem0 整合)
  - `router/router.py` — `process_query` 注入历史上下文
  - `cli.py` — 支持 session
  - `tests/test_memory.py` — 新增
  - `requirements.txt` — **不**添加 `mem0ai`(决策修订)

## ADDED Requirements

### Requirement: 基于自研 Memory 的对话记忆

The system SHALL 使用 `core/memory.py` 中的 `Memory` 类管理对话历史，按 `session_id` 存储/检索消息。

#### Scenario: 存储与检索对话
- **WHEN** Agent 完成一次交互
- **THEN** 调用 `Memory.add_message(session_id, role, content)` 存储消息
- **WHEN** 处理新请求时
- **THEN** 调用 `Memory.get_history(session_id)` 获取历史，注入 LLM messages

### Requirement: 线程安全与持久化安全

The system SHALL 保证:
- 所有 public mutator/reader 通过 `threading.RLock` 串行化(load-modify-write 原子)
- 持久化通过临时文件 + `os.replace` 原子重命名,避免半写损坏
- `persist_path` 为裸文件名(无目录)时不崩溃

### Requirement: 记忆容量管理

The system SHALL 限制注入 LLM 的历史消息轮数（默认 10 轮 = 20 条 user/assistant 消息），防止上下文窗口溢出。超出时保留最近 N 条。

### Requirement: CLI Session 支持

The system SHALL 在 `cli.py` 中为每个运行实例生成唯一的 `session_id`。

## MODIFIED Requirements

无

## REMOVED Requirements

- ~~Requirement: 基于 mem0 的对话记忆~~ — 改为基于自研 Memory(见 Decision Log)

## Decision Log

### 2026-07-26: 不整合 mem0, 改为自研轻量 Memory

**背景**: 原 spec 计划整合 `mem0ai` 作为对话记忆后端。在实现阶段经审查者复核后决定改为自研轻量 Memory。

**理由**:
1. **依赖最小化**: Synapse 的核心卖点是"自进化 Agent 框架",引入 mem0 会带来它自身的 LLM 调用、向量数据库、可选后端等一长串传递依赖,显著抬高部署门槛,与"开箱即用"目标冲突。
2. **职责边界清晰**: mem0 的核心价值是"语义记忆抽取 + 向量检索",适合长期跨会话个性化。Synapse 当前需求是"单 session 内最近 N 轮上下文注入",纯 FIFO 列表 + JSON 落盘已足够,语义记忆属于过度工程。
3. **可观测性**: 自研 Memory 的状态可直接 `GET /history/{session_id}` 暴露给用户调试;mem0 的内部存储对用户不透明。
4. **可替换性**: `Memory` 已抽象为 `router.memory` 字段,未来若需升级到 mem0/LangGraph checkpointer/Redis,只需替换该字段实现,不影响 Router 主流程。

**验证**: `tests/test_memory.py` 覆盖 10 个场景包括并发写、裸文件名持久化等,Bug-9 / Bug-17 已通过测试。
