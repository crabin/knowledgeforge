# 任务计划：KnowledgeForge 实施计划

## 目标
在不偏离项目需求、知识文档格式规范和流程执行文档的前提下，分阶段落地 KnowledgeForge 的主链路闭环，并为 Neo4j、质量检测、版本更新和后续研报分支建立稳定接口与治理骨架。

## 当前阶段
阶段 8：版本冻结与研报分支已完成

## 下一轮增强 / 当前进行中的补充工作
- 前端动作实时展示修复
  - 已完成：统一直接创建任务与 intake 确认任务的异步启动路径，避免确认时同步阻塞页面。
  - 已完成：QueryEngine 实时事件写入 audit log 的同时刷新任务快照，让前端轮询任务详情时能看到当前动作、更新时间和中间日志。
  - 已完成：补充回归测试覆盖 intake 确认后的实时轮询、任务详情中间状态和最终任务状态。
  - 已完成：`/tasks/{task_id}/logs` 读取时从任务快照补写缺失 execution_log，确保新日志保存到 audit jsonl。
- 三路 Agent 计划确认与流程可视化
  - 已完成：Insight / Query / Media 三路 Engine 均支持先生成 `EnginePlan`，再按确认后的计划执行。
  - 已完成：`/tasks/async` 与 intake confirm 默认进入 `awaiting_plan_confirmation`，新增计划查看与确认接口。
  - 已完成：前端展示三路 Agent 执行计划，用户确认后再启动并行采集。
  - 已完成：Flow Map 改为 workflow step 事件驱动，可聚焦当前 planning / collecting / evaluating / writing / governing / versioning 步骤。
  - 已完成：计划阶段取消规则 fallback，任一路 LLM 计划生成失败时进入 `plan_failed` 并记录 logs。
  - 已完成：Flow Map 接入 AntV X6 画布展示实时流程图，保留原卡片作为 X6 未加载时的语义回退。
  - 已完成：MediaEngine 计划阶段改用 planning client，避免误用 5 秒 execution timeout 导致计划失败。
- 补充模块决策优化
  - 已完成：完整性不足时读取实时保存的领域 `README.md`、`*-query.md` 和已保存 Markdown 内容作为知识 index 上下文。
  - 已完成：新增 LLM 补充决策器，分析当前 index 暴露的缺陷、优先级、补查 query、预期信息和成功标准。
  - 已完成：补充决策只分发给 QueryEngine 执行权威事实补采，执行后合并 QueryEngine 输出并重新评估完整性。
  - 已完成：补充决策结果进入 `CompletenessResult.supplement_decision`，最终通过后仍可审计读取的 index 路径和决策来源。
- Query / Media 计划项实时保存
  - 已完成：新增文件审查模块，按计划项审查 QueryEngine / MediaEngine 获取的合格内容并实时保存 Markdown 草稿。
  - 已完成：每次实时保存或跳过后刷新领域 `README.md` 的“实时保存文档”索引区块，最终 writer 重写 README 时保留该区块。
  - 已完成：实时保存事件进入 audit log 与运行中任务快照，失败按 `file_write_failed` 记录但默认不阻断采集流程。
- 前端步骤显示优化
  - 已完成：Flow Map 新增“实时沉淀”步骤，展示计划项级实时文件审查与 Markdown 草稿保存。
  - 已完成：Agent 计划卡片显示实时保存状态、保存路径和 MediaEngine 执行进度。
  - 已完成：摘要区增加实时保存文件数与跳过来源数。
- 质量流水线来源门禁
  - 已完成 `docs/superpowers/plans/2026-04-24-quality-pipeline-optimization.md`：多 provider 搜索、Wikipedia supplement、Bing redirect 解码、领域相关性过滤、source reliability 重判、Completeness / Quality 来源门禁、Writer 动态状态和 ML Weblio 回归测试。
- Browser 抓取稳定性
  - 继续收敛 `agent-browser` 的超时行为、会话复用方式和页面关闭策略，避免同一次任务里反复卡住。
- crawler 降级策略
  - 将 Query / Media crawler 固化为“browser-first，失败后快速降级到 HTTP fallback 链”，并在 browser 不健康时短路后续 browser 调用。
- HTTP 搜索兜底质量
  - 在 DuckDuckGo HTML 之外保留第二条 HTTP 搜索 provider，减少单一搜索源不可用时的整体失败率。
- QueryEngine 结构化重构
  - 参考 BettaFish 的设计思路，将 `QueryEngine` 从占位实现升级为由 `search -> summary -> formatting` 组成的节点化结构。
- 官方文档优先检索策略
  - 保持“官方文档为主、教程补充为辅”的检索优先级，并在输出中显式保留来源类型与可信度。
- MediaEngine 结构化重构
  - 按相同思路将 `MediaEngine` 升级为 `search -> summary -> formatting` 的节点化结构，专门补“社区观点 / 社交讨论 / 博客趋势”。
- Query / Media ReAct 闭环
  - 在两个 Engine 内部增加“首轮检索 -> 反思 -> 补检索 -> 总结”的最小 ReAct 循环，避免一次检索后直接结束。
- QueryEngine 查询计划决策化
  - 已完成：QueryEngine 在联网查询前先生成结构化 `SearchQuestion` 决策表，逐项执行 Google 风格查询，记录每题预期信息、满足标准、fallback 查询、执行状态和检索轨迹。
  - 已完成：fallback query-plan 来源降级为 `unknown`，避免把“计划”误判为高可信证据。
- QueryEngine 中间日志可见化
  - 已完成：任务响应新增 `execution_log` 聚合字段，QueryEngine 写出计划、检索、反思、总结 fallback 等结构化事件。
  - 已完成：新增 `/tasks/{task_id}/logs` 读取 audit jsonl，前端展示“QueryEngine 查询计划”和“调用与执行日志”。
- 任务列表保存与查看
  - 已完成：基于已落盘的 task state JSON 生成持久化任务列表，新增 `GET /tasks`。
  - 已完成：前端新增“查看任务列表”和任务列表面板，点击列表项可回填 Task ID。
- QueryEngine 查询计划文件落盘
  - 已完成：Markdown Writer 会将 QueryEngine 查询计划保存为同一子领域目录下的 `*-query.md` 文档，并在综述文档后续动作中引用。
  - 已验证：`save/Machine Learning/最新论文方向/20260425-machine-learning-queryengine-query.md` 已生成；`save/` 目录按仓库规则被 git ignore。
- QueryEngine 查询计划清单化
  - 已完成：查询计划项新增 `search_targets`、`plan_item_id`、`completed_at`，执行状态调整为 `planned -> in_progress -> completed/insufficient`。
  - 已完成：每条计划项执行完立即输出完成或不足事件，前端以清单卡片显示查询内容、满足标准和勾选状态。
- 技术领域社区优先策略
  - 技术领域默认采用中外技术社区混合来源，优先 `X / Reddit / Hacker News / GitHub Discussions / 技术博客`，同时补 `V2EX / 掘金 / 知乎`。
- crawler 质量增强
  - 在首版 crawler 已落地的基础上，继续收敛 browser-first 抓取、官方域名识别、社区平台识别、正文提取质量和低质量页面降权策略。
- workflow 回归稳定化
  - 继续隔离真实网络检索对主流程测试的影响，并把 intake 新入口纳入稳定、可重复的 workflow 回归确认。

## 总体策略
- 先打通主链路，再补深治理能力。
- 先稳定 Markdown 本地存储与状态模型，再接 Neo4j 和质量闭环。
- 先做接口和契约，再逐步替换为更完整的实现。
- 严格保持三路并行采集、状态持久化与恢复、路径稳定、来源追溯。
- 当前阶段不把 ChromaDB 纳入主链路。

## 阶段计划

### 阶段 1：基础骨架初始化
- [x] 建立 Flask 应用入口与基础路由
- [x] 建立 LangGraph Orchestrator 骨架
- [x] 定义全局状态模型、消息模型、轮次模型
- [x] 建立 `agent/InsightEngine`、`agent/QueryEngine`、`agent/MediaEngine` 标准目录结构
- [x] 建立配置管理、日志、任务 ID 与时间工具
- [x] 预留持久化与恢复接口
- **交付物：**
  - 可启动的 Flask 应用
  - 可导入的编排层模块
  - 三个 Engine 的空实现骨架
  - typed state / schema 定义
- **验收标准：**
  - 项目目录符合 Engine 分层约束
  - 主流程状态对象可创建
  - Web 层可接收领域输入并创建任务
- **状态：** complete

### 阶段 2：输入与上下文构建
- [x] 实现领域输入校验
- [x] 实现范围、边界、时间窗口、关注点的标准化结构
- [x] 生成 `request_context` 与 `initial_strategy`
- [x] 增加模糊输入的追问或补足机制
- **交付物：**
  - Intake / Context Builder 模块
  - 标准化请求 schema
  - 初始检索策略生成逻辑
- **验收标准：**
  - 模糊领域输入能转化为可执行上下文
  - 输出可直接注入 LangGraph 状态
- **状态：** complete

### 阶段 3：三路并行采集主链路
- [x] 实现 Orchestrator 对三路 Engine 的并行调度
- [x] 为 Insight / Query / Media 建立统一输入输出契约
- [x] 为每路结果记录来源、Agent、轮次、采集时间和证据元数据
- [x] 汇总本轮采集结果并写入共享状态
- **交付物：**
  - 并行采集节点
  - 三路 Engine 的最小可运行实现
  - 汇总器与采集元数据结构
- **验收标准：**
  - 三路可并行执行
  - 每一路输出均具备完整追溯字段
  - 汇总结果可进入完整性评估节点
- **状态：** complete

### 阶段 4：完整性评估与补检索
- [x] 实现独立 `Completeness Evaluator`
- [x] 定义覆盖度、可信度、事实性、冲突与时效性检查项
- [x] 输出 `pass` 或 `supplement_required`
- [x] 失败时生成补检索策略、目标缺口、优先级和下一轮关键词
- [x] 增加最大轮次保护
- **交付物：**
  - 完整性评估节点
  - 补检索策略生成器
  - 轮次控制规则
- **验收标准：**
  - 缺失关键主题时能阻止入库
  - 补检索结果明确说明“为什么补、补什么、怎么补”
- **状态：** complete

### 阶段 5：知识文档落盘
- [x] 实现 Markdown 文档写入器
- [x] 生成领域级 `README.md`
- [x] 按 `save/{领域名称}/{子领域名称}/{文档文件名}.md` 落盘
- [x] 严格写入 YAML front matter 和规范要求的章节
- [x] 建立文档 ID、版本、路径、状态的一致性校验
- **交付物：**
  - Knowledge Document Writer
  - 文件命名与路径生成器
  - front matter / 文档章节校验器
- **验收标准：**
  - 落盘文档符合知识文档格式规范
  - 文档可回溯到来源、Agent、轮次、时间和本地路径
- **状态：** complete

### 阶段 6：后置治理骨架
- [x] 建立结构化抽取接口
- [x] 建立 Neo4j 写入与路径关联接口
- [x] 建立质量检测接口
- [x] 建立版本记录接口
- [x] 统一错误分类为文件写入失败、图谱写入失败、路径关联失败、检测失败
- **交付物：**
  - `post_storage_pipeline` 骨架
  - Neo4j adapter 接口
  - quality checker 接口
  - version recorder 接口
- **验收标准：**
  - 后置治理链路可串联调用
  - 各类失败可被明确分类和返回
- **状态：** complete

### 阶段 7：质量闭环与回流分类
- [x] 实现冲突检测
- [x] 实现重复检测
- [x] 实现引用检查
- [x] 实现图谱一致性校验
- [x] 将失败分类为 `repair_flow` 或 `research_flow`
- [x] 为回流写入明确原因、目标和下一步动作
- **交付物：**
  - 质量检测器首版
  - 回流分类规则
  - 问题报告结构
- **验收标准：**
  - 不再出现泛化“失败”结果
  - 每次回流均有问题类别和处理方向
- **状态：** complete

### 阶段 8：版本冻结与研报分支
- [x] 实现版本记录与冻结规则
- [x] 限制研报分支只消费 `verified` 知识
- [x] 预留 Report Agent 接口
- [x] 记录每次更新涉及的文档、图谱节点、轮次和保留问题
- **交付物：**
  - 版本冻结规则
  - 研报消费边界
  - 版本记录 schema
- **验收标准：**
  - 未通过质量检测的知识不能进入研报分支
  - 冻结版本可被明确查询与追踪
- **状态：** complete

## 首批实施批次

### 批次 A：主链路前半段最小闭环
- [x] Flask 基础接口
- [x] LangGraph 主流程骨架
- [x] 三路 Engine 空骨架
- [x] 全局状态模型
- [x] 完整性评估节点
- [x] Markdown Writer
- **目标：**
  - 打通 `输入领域 -> 并行采集 -> 完整性评估 -> Markdown 落盘`
- **状态：** complete

### 批次 B：后置治理接口骨架
- [x] 结构化抽取接口壳
- [x] Neo4j adapter 接口壳
- [x] quality checker 接口壳
- [x] version recorder 接口壳
- **目标：**
  - 让主链路输出能稳定接入治理层
- **状态：** complete

### 批次 C：质量闭环与恢复能力
- [x] repair / research 双回流
- [x] 状态持久化与恢复
- [x] 最大轮次保护
- [x] 错误分类与审计记录
- **目标：**
  - 形成可恢复、可回流、可解释的闭环
- **状态：** complete

## 推荐实现顺序
1. 搭目录结构和 schema。
2. 搭 Flask 入口和任务创建接口。
3. 搭 LangGraph 主状态与主图。
4. 接入三路 Engine 最小空实现。
5. 接入完整性评估。
6. 接入 Markdown Writer。
7. 再补 Neo4j / 质量检测 / 版本接口骨架。
8. 最后补恢复、回流和冻结规则。

## 关键决策
| 决策 | 理由 |
|------|------|
| Markdown 本地文件是主事实存储 | 需求文档已明确本地文件为权威存储 |
| Neo4j 是映射层而非主数据源 | 避免图谱反客为主并破坏路径一致性 |
| 完整性评估独立于三路 Engine | 统一评估标准，避免能力域内部各自为政 |
| 先做骨架和契约，再逐步做深 | 当前仓库处于设计态，先求可联通和稳定边界 |
| ChromaDB 暂不进入主链路 | 当前阶段仅预留职责 |

## 关键风险
| 风险 | 影响 | 应对 |
|------|------|------|
| 过早引入额外存储或共享抽象 | 范围失控、返工增加 | 严格按当前需求只做本地文件 + Neo4j |
| Markdown schema 与 Neo4j schema 不一致 | 路径关联和版本记录不稳定 | 先统一 `id/path/status/version` 契约 |
| 回流只返回“失败” | 无法形成质量闭环 | 强制问题分类和流向分类 |
| 三路输出字段不统一 | 难以汇总、评估和追溯 | 先定义统一输出 schema |
| 真实网络检索影响 workflow 稳定性 | 回归结果易波动，影响验证可信度 | 增强假依赖注入与测试隔离，避免将在线检索直接耦合进默认回归 |

## 完成定义
- 主链路至少能从领域输入生成一份符合规范的 Markdown 知识文档。
- 三路输出、完整性评估、落盘结果都具备来源追溯字段。
- 后置治理失败可被明确分类。
- 状态支持持久化和恢复接口预留。
- 实施结果与需求文档、格式规范、流程执行文档无明显冲突。
- QueryEngine 补充增强阶段需额外满足“官方文档优先、教程补充、来源可追溯、回归测试可稳定复现”。
- MediaEngine 补充增强阶段需额外满足“社区/社交/博客职责清晰、趋势观点可追溯、技术社区优先策略可验证”。
- ReAct 升级后需额外满足“反思结论可解释、补检索可追溯、单轮补检索后稳定收口”。
- QueryEngine 查询计划优化后需额外满足“先生成结构化问题清单，再逐项检索；每项记录预期信息、满足标准、状态和不足原因；计划型 fallback 来源不能伪装成高可信来源”。
- 前端实时查询进度需额外满足“任务启动后立即可查询 task/logs；QueryEngine 计划、调用、执行和完成事件在任务运行中写入 audit；页面能按计划项实时显示待查询、查询中、已完成和需补检索”。
- 任务管理功能需额外满足“可查看、修改和删除已保存任务；运行中任务拒绝改删；管理操作写入 audit；删除任务不误删 `save/` 下的知识文档正文”。
- 单引擎真实联调日志需额外满足“记录每次 LLM / Embedding / browser / httpx 调用的 endpoint、耗时、状态或失败原因，并按时间保存到 `logs/`”。
- Intake 收口阶段需额外满足“创建与追加都返回完整 intake session、confirm 返回 `{ intake_session, task }`、非知识采集 intent 不允许直接启动任务”。
