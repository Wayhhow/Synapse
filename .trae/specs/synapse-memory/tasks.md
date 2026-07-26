# Tasks

- [x] Task 1: 实现对话记忆并修改 SkillRouter
  - [x] SubTask 1.1: ~~在 `requirements.txt` 中添加 `mem0ai>=0.1.0`~~ **(决策修订: 不引入 mem0, 见下方"决策记录")**
  - [x] SubTask 1.2: 在 `core/memory.py` 中实现自研 `Memory` 类(基于 JSON 文件持久化 + `threading.RLock` 线程安全)
  - [x] SubTask 1.3: 修改 `process_query` 签名，添加 `session_id: Optional[str] = None`
  - [x] SubTask 1.4: 在构建 LLM messages 时，如果有 `session_id`，从 `Memory.get_history` 获取历史并注入
  - [x] SubTask 1.5: Agent 回复后，将用户输入和 Agent 回复存入 `Memory.add_message`
  - [x] SubTask 1.6: 限制注入的历史消息为最近 10 轮(`max_history * 2` 条消息)
  - [x] SubTask 1.7: 运行 `pytest tests/test_skills_routing.py -v` 确保无回归

- [x] Task 2: 修改 CLI 支持 Session
  - [x] SubTask 2.1: 在 `cli.py` 中导入 `uuid`，生成唯一 `session_id`
  - [x] SubTask 2.2: 每次调用 `router.process_query(user_input, session_id=session_id)`
  - [x] SubTask 2.3: 运行 `python -m py_compile cli.py` 检查语法

- [x] Task 3: 编写记忆系统测试
  - [x] SubTask 3.1: 创建 `tests/test_memory.py`，覆盖 add/get/clear/persist/session 隔离/并发/裸文件名场景
  - [x] SubTask 3.2: 运行 `pytest tests/test_memory.py -v`

# 决策记录: 为何不整合 mem0
原始 spec 计划整合 `mem0ai` 作为对话记忆后端。在实现阶段经审查后决定改为自研轻量 Memory,理由如下:
- **依赖最小化**: Synapse 的核心卖点是"自进化 Agent 框架",引入 mem0 会带来它自身的 LLM 调用、向量数据库、可选后端等一长串传递依赖,显著抬高部署门槛,与"开箱即用"目标冲突。
- **职责边界清晰**: mem0 的核心价值是"语义记忆抽取 + 向量检索",适合长期跨会话个性化。Synapse 当前需求是"单 session 内最近 N 轮上下文注入",纯 FIFO 列表 + JSON 落盘已足够,语义记忆属于过度工程。
- **可观测性**: 自研 Memory 的状态可直接 `GET /history/{session_id}` 暴露给用户调试;mem0 的内部存储对用户不透明。
- **可替换性**: `Memory` 已抽象为 `router.memory`,未来若需升级到 mem0/LangGraph checkpointer/Redis,只需替换该字段实现,不影响 Router 主流程。
- 详见 `synapse-memory/spec.md` 中的"Decision Log"修订。

# 额外完成(实现过程中发现并修复)
- [x] Bug-9: `Memory` 添加 `threading.RLock` + 临时文件原子写,保证并发 `add_message` 不丢消息
- [x] Bug-17: `persist_path` 为裸文件名时不再因 `os.makedirs("")` 崩溃
- [x] Bug-3 (memory 部分): meta-evolution 重试前不再重复 `add_message`,session 历史更准确

# Task Dependencies

- Task 2 依赖 Task 1
- Task 3 依赖 Task 1
