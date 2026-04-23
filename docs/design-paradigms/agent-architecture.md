# 多智能体架构范式

与具体业务无关的智能体分层与路由设计经验。

## 1. 基类抽象与消息模型

- **基类**：用抽象基类定义统一接口（如 `process(user_input, **kwargs) -> str`），子类实现具体逻辑。系统提示词、对话历史、记忆可放在基类，由子类按需覆盖默认实现。
- **消息模型**：使用 Pydantic 或 dataclass 定义 `AgentMessage(role, content, metadata)`，便于序列化、日志与持久化。`role` 建议固定为 `user` / `assistant` / `system`。
- **历史与记忆分离**：对话历史（当前会话轮次）与长期记忆（跨会话）建议用不同字段或不同管理器，避免混用导致难以做记忆摘要或裁剪。

## 2. 路由分发

- **职责**：根据用户输入决定走「简单问答」还是「需要规划/工具执行」等分支，而不是把所有请求都交给同一个重型流水线。
- **实现方式**：
  - 关键词列表：问候、帮助、介绍类 → 轻量 Q&A；操作类动词（扫描、执行、分析等）→ 规划/执行流。
  - 规则顺序：先匹配问候/再见，再匹配问答类关键词，再根据长度与操作词判定；短句且无操作词可默认走 Q&A，减少误判。
- **类型**：路由结果用 `Literal["qa", "technical"]` 等明确类型，便于上层分支与测试。

## 3. 多智能体分工

- **Q&A Agent**：只做对话、介绍、帮助，不调用工具，响应快、成本低。
- **Planner Agent**：解析意图、拆解步骤、产出待办（Todo），不直接执行。
- **Core Agent**：带工具调用的主智能体，执行具体动作，可复用 ReAct/function calling。
- **Summary Agent**：对当轮工具执行结果做摘要，便于用户与审计。

路由只决定「走 Q&A 还是走 Planner → Core → Summary」；各 Agent 之间通过会话上下文或事件总线传递数据，避免紧耦合。

## 4. 面向业务域的 Engine 分层

当项目需要构建多个面向业务能力的智能体时，优先采用 `XxxEngine` 命名与分层，而不是堆叠一组职责模糊的 `Agent` 类。

- **推荐命名**：使用清晰的领域名，例如 `MediaEngine`、`InsightEngine`、`QueryEngine`。
- **职责边界**：每个 Engine 对应一类稳定能力域，对外暴露统一入口，例如 `run(...)`、`process(...)` 或 `execute(...)`。
- **编排方式**：由上层 Orchestrator / Router 决定调用哪个 Engine，避免 Engine 之间互相直接依赖。
- **内部结构**：Engine 内部再组合 prompts、tools、memory、planner、executor 等组件，而不是把所有逻辑写在单一类中。
- **适用场景**：当系统天然存在“媒体处理 / 洞察生成 / 查询问答”这类分工时，优先按能力域拆分 Engine；只有纯对话助手或极简原型才保留单 Agent 结构。

一个推荐形态如下：

- `Router`：根据输入或任务类型选择目标 Engine。
- `MediaEngine`：负责媒体理解、转码、提取、摘要等与媒介处理相关的能力。
- `InsightEngine`：负责分析、归纳、报告、结构化洞察生成。
- `QueryEngine`：负责检索、问答、知识查询与结果整合。

### Node / Utils / LLMs 的配套分层

为了让 `XxxEngine` 结构长期可维护，建议同步定义以下配套层：

- **Nodes**：承载可编排的原子执行步骤，例如解析输入、检索资料、调用工具、汇总结果。Node 应该尽量单一职责、可测试、可复用，适合挂到工作流图、状态机或 DAG 中。
- **Utils**：放纯函数、格式转换、文本处理、时间与 ID 生成、schema 校验这类与业务编排无关的辅助逻辑。避免把真正的流程决策塞进 utils，防止 utils 变成杂物间。
- **LLMs**：统一封装模型配置与调用入口，例如模型选择、温度、max tokens、重试、fallback、结构化输出适配。不要在每个 Engine 或 Node 内部散落地直接 new client 或硬编码模型参数。

推荐职责边界：

- `Engine` 负责“一个业务能力域的编排与对外入口”。
- `Node` 负责“流程中的单步能力块”。
- `Utils` 负责“无状态、可复用的小工具”。
- `LLMs` 负责“模型访问层与模型策略”。

推荐目录形态示例应尽量贴近当前项目的 `MediaEngine` / `InsightEngine` / `QueryEngine` 结构。可以都放在统一的 `agent/` 目录下，但每个能力域最好仍然保持各自完整子结构，例如：

```text
agent/
  MediaEngine/
    agent.py
    nodes/
    llms/
    prompts/
    state/
    tools/
    utils/
  InsightEngine/
    agent.py
    nodes/
    llms/
    prompts/
    state/
    tools/
    utils/
  QueryEngine/
    agent.py
    nodes/
    llms/
    prompts/
    state/
    tools/
    utils/
```

如果项目规模较小，也可以先只保留一个 `MediaEngine/` 风格目录，后续再按同样骨架扩展出 `InsightEngine/` 与 `QueryEngine/`，而不是先抽象成共享的 `engines/` 总目录。

拆分原则：

- Engine 不直接吞掉所有实现细节，复杂步骤下沉到各自 Engine 内部的 `nodes/`。
- `nodes/` 放流程步骤节点，例如 search、summary、formatting、report_structure 这类可编排步骤。
- `utils/` 放文本处理、配置读取、通用辅助函数，但不要承载主流程编排。
- `llms/` 放模型客户端与模型适配层，统一封装模型访问。
- `prompts/`、`state/`、`tools/` 也建议与 Engine 同级保留，形成完整闭环，保持与 `MediaEngine` 一致。
- 若后续确实出现跨 Engine 复用，再谨慎抽共享模块；默认先保持每个 Engine 内聚。

这样做的好处：

- 业务边界更稳定，后续扩展新能力时只需新增 Engine。
- 测试更清晰，可按 Engine、Node、LLM adapter 分层测试。
- 与 UI/API 的契约更自然，便于把不同能力暴露为独立端点或工具。
- 便于未来把 Engine 替换为不同模型、不同工具链、或不同执行策略。
- 可避免 `utils.py` 或某个巨型 agent 文件无限膨胀。

## 5. 依赖注入与获取智能体

- 上层（CLI / API）持有一个 `get_agent(agent_type)`，内部按类型懒加载并缓存实例，避免进程内重复创建。
- 如果已经采用 Engine 分层，也可扩展为 `get_engine(engine_type)` 或通过 registry/factory 获取具体实例。
- 审计、记忆、DB、LLM client、tool registry 等依赖优先通过构造函数注入，便于测试时替换为 mock。

## 6. 可复用要点小结

- 抽象基类 + 统一 `process` 接口。
- 消息模型标准化（role/content/metadata）。
- 路由按「问答 vs 技术/执行」分流，规则可配置、可测试。
- 多智能体各司其职：Q&A / Planner / Core / Summary。
- 复杂业务优先按 `MediaEngine` / `InsightEngine` / `QueryEngine` 这类能力域拆分。
- 流程步骤下沉为 Node，通用逻辑放 Utils，模型访问统一收敛到 LLMs 层。
- 智能体/Engine 实例懒加载 + 缓存，依赖通过构造函数或 factory 注入。
