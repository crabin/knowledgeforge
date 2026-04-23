# KnowledgeForge 整体设计规格

- 日期：2026-04-24
- 主题：KnowledgeForge 端到端知识工程主链路与后置治理骨架
- 状态：draft-approved-for-spec-review

## 1. 目标

KnowledgeForge 的首个可实施版本应构建一条围绕“输入领域 → 三路并行采集 → 完整性评估 → 统一 Markdown 沉淀 → 后置治理骨架 → 版本冻结”的端到端知识工程主链路，并为 Neo4j 路径关联、质量检测、失败补偿、版本管理和后续研报消费提供可直接实现的规则与接口边界。

该版本必须满足以下原则：

- 不破坏三路并行采集、状态持久化与恢复、稳定本地路径关联、来源追溯与质量闭环。
- 本地 Markdown 是知识源事实存储。
- Neo4j 是结构化映射层，而不是主数据源。
- 未通过质量检测或未冻结的知识不得进入研报分支。

## 2. 范围

### 2.1 本次规格覆盖

- Flask Web 入口
- LangGraph Orchestrator / Router
- Context Builder / Intake 节点
- InsightEngine / QueryEngine / MediaEngine 三大能力域
- Completeness Evaluator 独立评估节点
- Knowledge Document Writer
- Post-Storage Pipeline 的首版骨架：结构化抽取接口、Neo4j 路径关联接口、质量检测接口、版本记录接口
- 回流分类、失败补偿、版本冻结规则
- 首批实施批次、测试策略、验收标准

### 2.2 本次规格不要求首批完整做实

- 完整的 Chunk / Entity / Relation 抽取细节实现
- 完整的 Report Agent 能力
- ChromaDB 集成
- 全量人工审查系统或复杂后台运维面板

这些能力在接口和状态上要被预留，但不要求在第一批全部做深。

## 3. 总体架构

系统采用以下分层：

1. **Web Interface（Flask）**

   - 接收领域输入与交互补充信息
   - 发起、恢复、查询流程任务
   - 返回当前流程状态、文档结果与阻断原因
2. **Orchestrator / Router（LangGraph）**

   - 维护全局状态
   - 路由请求到主链路、回流链路、恢复链路
   - 并行调度三大 Engine
   - 控制循环、重试、终止和冻结条件
3. **Context Builder / Intake**

   - 将用户输入转化为可执行领域上下文
   - 生成领域边界、时间范围、重点、初始检索策略
4. **能力域 Engine 层**

   - `InsightEngine`：本地知识与历史沉淀
   - `QueryEngine`：外部事实、官方与权威来源
   - `MediaEngine`：热点、社区、媒体与用法视角
5. **Knowledge Document Layer**

   - 将通过完整性评估的内容沉淀为统一 Markdown 文档
   - 严格遵守 `docs/知识文档格式规范.md`
6. **Post-Storage Pipeline**

   - 结构化抽取接口
   - Neo4j 写入与路径关联
   - 质量检测
   - 版本记录与冻结
7. **Report Branch**

   - 仅消费 `verified + frozen` 的知识版本
   - 与主入库链路解耦

## 4. 模块边界

### 4.1 Web Interface

职责：

- 接收用户输入
- 进行必要的追问交互
- 提交任务并返回任务 ID 或状态
- 查询已有任务结果

不负责：

- 业务编排
- 质量判断
- 图谱写入

### 4.2 Orchestrator / Router

职责：

- 维护主流程状态真相
- 启动并行三路采集
- 汇总本轮结果
- 调用完整性评估、文档写入、后置流水线
- 决定进入 `repair_flow`、`research_flow`、`needs_human_review` 或 `frozen`

不负责：

- 具体采集逻辑
- 文档内容生成细节
- 图谱细节建模实现

### 4.3 Context Builder / Intake

职责：

- 处理用户输入的领域名、边界、时间范围、关注重点
- 生成首轮检索上下文
- 标准化为可注入流程状态的结构

### 4.4 三大 Engine

每个 Engine 对外统一暴露 `run(...)` / `execute(...)` 风格入口，并在内部保持下列结构：

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

约束：

- Engine 之间不得直接依赖。
- Engine 不直接写 Neo4j。
- Engine 不负责版本冻结。
- Engine 输出必须包含来源、Agent、轮次、时间信息。

### 4.5 Completeness Evaluator

职责：

- 独立评估一轮采集是否足以进入沉淀
- 输出 `pass` 或 `supplement_required`
- 当需要补检索时生成可执行策略

该节点由 Orchestrator 调用，但不属于任一 Engine，以保证标准统一。

### 4.6 Knowledge Document Writer

职责：

- 将汇总结果写入统一 Markdown 文档
- 校验 front matter、路径、必要章节
- 返回文档路径、文档 ID、写入状态

不负责：

- 质量通过与否判断
- 冻结版本

### 4.7 Post-Storage Pipeline

职责：

- 为已落盘文档执行结构化处理与治理动作
- 提供四类首版能力接口：
  - 结构化抽取接口
  - Neo4j 写入接口
  - 质量检测接口
  - 版本记录接口

第一批可先实现为骨架，但状态与返回契约必须稳定。

### 4.8 Report Branch

职责：

- 读取冻结后的知识版本
- 生成面向用户的报告内容

约束：

- 不得直接读取未质检原始资料
- 不得绕过版本冻结点

## 5. 主数据流

标准数据流如下：

1. 用户在 Flask 输入目标领域。
2. Context Builder 补全领域边界、重点、时间窗口和初始策略。
3. Orchestrator 创建流程状态并进入当前轮次。
4. Orchestrator 并行调度三大 Engine。
5. 汇总 `Insight / Query / Media` 输出与来源元数据。
6. Completeness Evaluator 执行完整性评估。
7. 若 `supplement_required`：生成补检索策略，进入下一轮采集。
8. 若 `pass`：Knowledge Document Writer 生成统一 Markdown 文档并落盘。
9. Post-Storage Pipeline 执行后置治理：抽取、图谱关联、质量检测、版本记录。
10. 若质量或治理失败：进入 `repair_flow` 或 `research_flow`。
11. 若通过冻结条件：生成正式版本。
12. 若用户需要研报：Report Branch 仅消费冻结版本。

## 6. 关键状态模型

LangGraph 全局状态至少包含以下部分：

### 6.1 request_context

- `domain`
- `subdomains`
- `time_window`
- `focus_points`
- `constraints`
- `initial_strategy`

### 6.2 round_context

- `round`
- `round_reason`
- `trigger_type`（initial / supplement / repair）
- `target_gap`
- `priority`

### 6.3 agent_outputs

- `insight_output`
- `query_output`
- `media_output`
- `source_metadata`
- `agent_runtime`

### 6.4 evidence_index

- 来源标题
- URL 或本地路径
- 发布方
- 获取时间
- 可信度
- 引用指针

### 6.5 document_records

- `document_id`
- `path`
- `status`
- `created_at`
- `updated_at`
- `source_round`

### 6.6 graph_sync_status

- `state`（not_started / synced / graph_sync_pending / graph_sync_blocked）
- `retry_count`
- `last_error`
- `last_attempt_at`

### 6.7 quality_status

- `conflict_check`
- `duplicate_check`
- `citation_check`
- `graph_consistency_check`
- `final_status`（passed / repair_required / research_required）

### 6.8 version_status

- `version_id`
- `is_frozen`
- `frozen_at`
- `blocking_issues`
- `consumable_by_report`

## 7. 统一知识文档合同

Knowledge Document Writer 必须产出符合 `docs/知识文档格式规范.md` 的 Markdown 文档，至少保证：

- 使用 YAML front matter
- `id`、`title`、`domain`、`subdomain`、`doc_type`、`source_type`、`agent`、`round`、`status`、`created_at`、`updated_at`、`version`、`path`、`sources` 完整
- 正文包含：摘要、关键结论、背景与上下文、正文、证据与来源、冲突与不确定性、后续动作、变更记录
- 能回溯到来源、Agent、轮次、时间和本地路径
- 保存路径遵循：

```text
save/{领域名称}/README.md
save/{领域名称}/{子领域名称}/{文档文件名}.md
```

本地 Markdown 是知识源事实存储。后续抽取、图谱、质量、版本全部围绕该文档建立。

## 8. 完整性评估规则

完整性评估是独立节点，不属于任一 Engine。

### 8.1 检查项

- 核心子主题是否覆盖
- 是否有高可信或权威来源支撑
- 是否存在“只有观点、缺少事实”的失衡
- 是否存在明显信息空洞
- 是否存在未解释冲突
- 是否达到最小可沉淀门槛

### 8.2 输出

- `pass`
- `supplement_required`

### 8.3 supplement_required 必须附带

- 缺口说明
- 待补主题
- 待补来源类型
- 关键词或检索方向
- 优先级

完整性评估通过，才允许进入 Markdown 沉淀。

## 9. 回流与失败分类

所有失败必须输出问题类型、原因和建议动作，禁止仅返回通用失败。

### 9.1 repair_flow

用于：

- 结构化抽取错误
- 元数据缺失
- 实体关系异常
- 图谱写入异常
- 路径映射异常

目标：修已有结果，不重新发起大范围采集。

### 9.2 research_flow

用于：

- 证据不足
- 来源不权威
- 引用链断裂
- 核心主题缺失
- 冲突无法裁决

目标：补新信息并重新进入采集。

### 9.3 needs_human_review

以下任一条件触发时进入人工审查：

- 达到最大采集轮次
- 达到最大 repair 次数
- 达到最大图谱补偿次数
- 单轮新增有效信息低于阈值

## 10. Neo4j 失败补偿规则

### 10.1 基本顺序

1. 先落本地 Markdown。
2. 本地文档成功后，才允许进入 Neo4j 写入。

### 10.2 失败规则

- 若 Markdown 写入失败：本轮知识沉淀失败，不进入图谱与版本阶段。
- 若 Markdown 成功但 Neo4j 失败：
  - 不回滚本地文档
  - 将状态标记为 `graph_sync_pending`
  - 记录失败原因、重试次数、最近尝试时间
  - 进入补偿队列
- 若多次补偿失败：
  - 状态标记为 `graph_sync_blocked`
  - 不允许正式版本冻结
  - 允许人工介入

### 10.3 设计原则

本地知识库优先于图谱映射。图谱失败不能抹除已保存的知识事实。

## 11. 质量闭环规则

质量检测至少包含四类检查：

- `conflict_check`
- `duplicate_check`
- `citation_check`
- `graph_consistency_check`

### 11.1 质量最终状态

- `passed`
- `repair_required`
- `research_required`

### 11.2 状态映射

- 结构与一致性问题 → `repair_required`
- 证据与来源问题 → `research_required`

Orchestrator 只根据该结果决定进入 repair_flow、research_flow 或冻结判断。

## 12. 版本冻结规则

只有同时满足以下条件，才允许生成正式版本：

1. 统一 Markdown 文档已成功保存。
2. 质量状态为 `passed`。
3. Neo4j 状态为 `synced`，而不是 `graph_sync_pending` 或 `graph_sync_blocked`。
4. 当前轮次不存在阻断冻结的未解决问题。

### 12.1 冻结后必须记录

- `version_id`
- 更新知识对象列表
- 来源轮次
- 涉及文件路径
- 涉及图谱节点
- 保留问题摘要
- 冻结时间

### 12.2 版本命名规则

正式冻结版本采用以下命名格式：

```text
{domain_slug}-v{major}.{minor}.{patch}-{YYYYMMDDHHmm}
```

规则如下：

- `major`：领域结构或核心知识组织方式发生不兼容调整时递增
- `minor`：新增或显著扩展知识对象时递增
- `patch`：修复引用、图谱关联、元数据或局部内容问题时递增
- 时间戳使用冻结时间，确保版本可排序、可审计

### 12.3 版本可见性规则

- 未冻结版本仅对流程内部和人工审查可见，不作为稳定知识消费对象
- 已冻结版本可被 Query 类检索、下游报告和版本审计消费
- `graph_sync_pending`、`graph_sync_blocked`、`repair_required`、`research_required` 状态的对象不得提升为公开稳定版本

### 12.4 研报消费规则

Report Branch 只读取冻结版本，绝不直接读取未审查原始采集资料。

## 13. 实施批次

### 批次 1：主链路可运行

- Flask 入口
- Context Builder
- LangGraph Orchestrator 基础状态
- 三大 Engine 骨架与并行调度
- Completeness Evaluator
- Markdown 文档落盘
- 基本回流控制

### 批次 2：后置骨架可追踪

- 结构化抽取接口
- Neo4j 路径关联
- 质量检测模块
- `graph_sync_pending / graph_sync_blocked`
- 版本冻结与版本记录

### 批次 3：增强与下游能力

- repair_flow 细化
- 补偿队列完善
- 人工审查入口
- Report Agent
- 更完整的结构化抽取与后续扩展接口

## 14. 测试策略

### 14.1 单元测试

- Context Builder 输入补全逻辑
- Completeness Evaluator 判定逻辑
- Markdown 文档生成与 front matter 校验
- 质量状态映射

### 14.2 集成测试

- Orchestrator 是否正确并行调度三路 Engine
- `research_flow` 是否能进入下一轮采集
- Markdown 成功但 Neo4j 失败时是否进入 `graph_sync_pending`
- 质量通过后是否允许版本冻结

### 14.3 流程测试

- 从输入领域到生成 Markdown 的主链路跑通
- 补检索路径是否带着原因和策略回流
- repair_flow 是否不会误触发重新采集
- `needs_human_review` 是否在阈值触发时终止自动流程

### 14.4 验收级测试

针对一个明确领域输入，系统应能输出：

- 明确领域上下文
- 三路采集结果
- 完整性评估结果
- 合规 Markdown 文档
- 后置流水线状态
- 正式版本或阻断原因

## 15. 验收标准

### 15.1 批次 1 验收

- 能接收领域输入并补足上下文
- 能并行执行三路 Engine
- 能完成完整性评估
- 能在通过后写出符合规范的 Markdown 文档
- 能在不通过时给出补检索策略并进入下一轮

### 15.2 批次 2 验收

- 能记录结构化抽取状态
- 能将文档路径与 Neo4j 关联
- Neo4j 失败时能进入补偿状态且不丢本地文档
- 能输出明确质量状态
- 满足冻结条件时能生成正式版本记录

### 15.3 总体验收

- 主链路可追溯
- 回流可分类
- 文件与图谱职责清晰
- 版本冻结规则可执行
- 未通过质量的知识不会进入研报分支

## 16. 实施建议

建议按以下顺序进入详细实施计划：

1. 初始化环境，使用uv管理项目。
2. 定义全局状态模型与模块接口。
3. 再搭建 Flask 入口、Context Builder、Orchestrator 和三大 Engine 骨架。
4. 接着完成 Completeness Evaluator 与 Knowledge Document Writer。
5. 然后补上 Neo4j、质量检测、版本冻结接口与状态流转。
6. 最后推进补偿队列、人工审查和研报分支。

这个顺序能保证最早得到一条真实可运行的主链路，同时不会把关键治理规则推迟到后期。
