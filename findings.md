# 发现与决策

## 需求
- 目标是构建一个围绕“采集 → 评估 → 入库 → 质检 → 回流”的领域知识工程系统。
- 当前硬约束：Flask、LangGraph、marker-pdf、本地 Markdown 存储、Neo4j；ChromaDB 仅预留。
- 核心不可破坏能力：三路并行采集、状态持久化与恢复、稳定本地路径关联、来源追溯与质量闭环。

## 研究发现
- 需求文档、知识文档规范、流程执行文档三者一致指向同一主链路，说明当前最适合先规划端到端闭环，而不是孤立做单点功能。
- 领域知识文档已经形成明确数据合同：front matter、正文结构、证据来源、冲突与不确定性、后续动作、变更记录。
- 代理架构范式与项目 CLAUDE.md 一致，均要求采用 Router/Orchestrator + Engine 分层，且 Engine 间不要直接耦合。
- 质量失败需要明确区分“回流修复”和“补检索”，这将直接影响状态机与错误分类设计。
- 项目存在多个尚未定案点：完整性评估归属、专门模板范围、文件/图谱失败补偿、版本冻结规则、ChromaDB 后续职责。

## 技术决策
| 决策 | 理由 |
|------|------|
| 规划优先围绕主链路闭环设计 | 三份核心文档都把闭环与回流作为系统本体，而非附属功能 |
| 采用“主链路优先，后半段用可落地骨架接上”的实施路径 | 这是兼顾端到端可运行与关键后段能力不缺位的最稳路径 |
| 首个实施批次优先做到主链路闭环前半段 | 用户已明确第一批以输入、采集、完整性评估和知识文档保存为先 |
| 首个实施批次同步搭建 Neo4j 与质量检测前置骨架 | 用户希望第一批不是只停在 Markdown 保存，而是把后半段关键接口一起搭好 |
| 完整性评估归属、Neo4j 失败补偿、版本冻结规则在本次规格中定案 | 用户不希望这些关键机制留到后面再补，要求本轮直接产出可实施答案 |
| 整体架构以 Orchestrator + 三大 Engine 为核心 | 符合项目架构约束，且便于后续按能力域分阶段落地 |
| 知识文档 Markdown 规范视为关键数据合同 | 它同时支撑本地存储、抽取、Neo4j 映射、质量检测与版本管理 |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| 项目范围偏大，单一规格可能过宽 | 用户已选择直接产出可实施规格，后续需通过阶段划分控制范围 |

## 资源
- docs/项目需求.md
- docs/知识文档格式规范.md
- docs/流程执行文档.md
- docs/design-paradigms/agent-architecture.md
- CLAUDE.md

## 视觉/浏览器发现
- 当前问题仍是范围与阶段划分，不是视觉布局问题，暂不需要浏览器图示。

## 已确认的设计共识
- 整体架构采用 Flask Web 层 + LangGraph Orchestrator/Router + InsightEngine/QueryEngine/MediaEngine + 文档/图谱/质量/版本模块。
- 第一批实施按“前半段主链路做实、后半段关键骨架接上”的方式推进。
- 完整性评估为独立评估节点；Neo4j 失败采用 `graph_sync_pending` 异步补偿；版本冻结点在质量通过且文件图谱一致之后。
- 核心模块边界固定为 Web Interface、Orchestrator、Context Builder、三大 Engine、Completeness Evaluator、Knowledge Document Writer、Post-Storage Pipeline、Report Branch。
- 数据流固定为“输入 → 上下文构建 → 三路并行采集 → 完整性评估 → 文档落盘 → 后置流水线 → 版本化 → 可选研报”，并以本地 Markdown 作为源事实存储。
- 回流规则固定为 repair_flow 与 research_flow 两类，禁止仅返回模糊失败。
- 质量状态固定为 `passed` / `repair_required` / `research_required`；达到最大轮次、补偿或最小新增阈值时转入 `needs_human_review`。

## QueryEngine 补充结论
- 参考 BettaFish 的 QueryEngine 设计思路，更适合当前项目“节点化能力增强 + 单引擎可独立测试”的演进方向。
- 真实网络检索会拖慢 `workflow` 测试，后续需要更稳定的测试隔离策略，避免外部网络扰动主链路回归结果。
- 默认回退输出仍需保留可追溯来源，否则更容易触发完整性评估失败，削弱质量闭环判断的可信度。

## MediaEngine 补充结论
- 参考 BettaFish 的 MediaEngine 结构后，更适合把“社区观点 / 社交讨论 / 博客趋势”从占位摘要升级为可组合的节点化流程。
- `MediaEngine` 必须与 `QueryEngine` 保持边界清晰：前者负责“当下怎么看”，后者负责“权威事实是什么”。
- 技术领域的观点抓取默认应采用中外技术社区混合策略，单一中文或单一海外来源都容易丢失关键信号。
- Media crawler 在真实网络环境下仍会出现回退到 query-plan 输出的情况，后续应继续增强平台识别、正文提取和低质量页面降权。

## ReAct 升级结论
- 单次 `search -> summary` 对 Query / Media 两个 Engine 都偏弱，加入最小 ReAct 闭环后，结果会更接近“先观察，再决定补什么”的目标。
- 当前最稳的做法是先固定为“一次反思 + 一次补检索”，避免过早引入多轮复杂控制。
- `反思结论`、`缺口` 和 `检索轨迹` 直接进入输出，有助于后续质量闭环判断为什么会继续搜索、补了什么。

## Browser 抓取结论
- 直接依赖 `httpx + DuckDuckGo HTML` 对真实联调不够稳，接入 `agent-browser` 后更适合作为 Query / Media crawler 的优先路径。
- `MediaCrawler` 这类项目的核心启发不是平台代码照搬，而是“浏览器优先、网络请求兜底、把抓取与正文提取分层”。
- `ML` 这类缩写词案例说明：切换到浏览器抓取并不能单独解决问题，query normalization 仍然是关键。

## agent-browser 独立诊断结论
- 当前环境下，`agent-browser` 的 daemon 和 session 管理可以启动，但 `open` 对 DuckDuckGo HTML 与 LangGraph 官网都在 30 秒内超时，问题已经低于 Query / Media agent 这一层。
- 因此“联网失败”不能只归因于 query planning；浏览器抓取底座本身也需要单独排障，否则 browser-first crawler 的收益会被底层阻塞抵消。
- 在 `agent-browser` 稳定性没验证通过之前，保留 `httpx` 或其他非浏览器抓取兜底是必要的，不能把浏览器路径视为唯一真实抓取方案。

## 单引擎日志增强结论
- `scripts/test_single_engines.py` 现在会为每次运行创建 `logs/single-engines-YYYYMMDD-HHMMSS.log`，stderr 与文件内容一致，便于现场观察和事后复盘。
- LLM 与 Embedding 日志已经记录 `POST` endpoint、模型、timeout、payload 尺寸、耗时、返回 keys 或异常类型，可直接定位 `ReadTimeout` 与配置地址问题。
- Query / Media crawler 通过 trace callback 记录 browser-first 与 httpx fallback 的真实 URL、状态码、命中数和异常；`agent-browser eval` 日志只保留脚本长度，避免完整 JS 污染日志。
- `ML` smoke 复测显示链路能完整暴露问题：LLM 规划超时、Bing browser 命中质量偏差、DuckDuckGo HTML 连接超时、Embedding 成功、summary LLM 超时。

## Intake 收口结论
- 当前更值得优先收口的是 intake 入口层，而不是继续把主精力投到 crawler，因为仓库已经出现成型的 `intake session -> clarify -> confirm -> task` 主线实现。
- `ClarificationResult` 应作为 intake 层唯一结构化输出，`ContextBuilder` 只负责把已确认的澄清结果映射成 `RequestContext`，这样 Query / Media 才能稳定消费确认后的领域语义。
- 对 `confirmed=True` 的上下文保持“已确认输入优先”是必要的，否则前面澄清得到的 `Machine Learning` 之类结果会在引擎层再次被误归一化。
- `concept_explanation` 和 `qa` 不能直接 confirm 成 task；它们必须通过追加消息切换到 `knowledge_collection`，这也是 intake 会话存在的主要价值。

## 抓取稳定性补充结论
- `agent-browser` 不是完全不可用；在“预热 daemon + page 级 close + 更稳定的目标页”条件下，live 测试可以通过。
- 当前更现实的问题是默认 browser 调用太脆弱，一旦 `open` 或 `fetch` 超时，就会在同一次任务里重复付出高昂等待成本。
- 因此 crawler 需要两层保护：浏览器失败后的实例级短路，以及 HTTP provider 链式降级，而不是简单地“一次 browser 失败后继续硬试”。

## Machine Learning 输出质量诊断
- `save/Machine Learning` 的结果未达到知识沉淀要求，核心症状是 Query / Media 来源严重跑偏：Weblio 的 `machine`、`machinery`、`sewing machine` 词典页面被当成 Machine Learning 的官方文档、技术社区观点和高/中可信来源。
- 当前任务上下文并没有把 `ML` 误识别为普通 machine；intake 已正确生成 `normalized_domain=Machine Learning`，问题发生在后续检索与质量门禁。
- 真实运行链路显示：LLM 搜索规划超时后使用 fallback query；browser 搜索没有拿到结果；DuckDuckGo HTML 超时；Bing HTTP fallback 返回 Weblio 结果。crawler 未过滤 Bing 跳转链接，也没有检查标题、摘要、URL 是否与完整领域短语 `Machine Learning` 相关。
- Query 打分逻辑把 `source_type="official"` 直接加 5 分，formatter 又按 source_type 把 reliability 固定为 `high`，导致“请求的是官方来源”被误写成“结果是高可信官方来源”。
- Media crawler 同样缺少平台硬约束；当 requested_type 是 social/community/blog 时，非社区页面会被 classify 成 requested_type，从而把 Weblio 词典页包装成社交媒体或技术社区来源。
- 完整性评估只检查 QueryEngine 是否存在来源、子主题是否覆盖，不检查来源相关性、权威域名、重复率、实际证据是否支撑子主题，因此错误来源可以通过入库前门。
- QualityChecker 只检查 front matter、证据章节、实体、图谱节点和“是否有来源”，不检查来源内容质量、publisher 是否为搜索引擎跳转域、证据是否支持结论，因此该文档还能被冻结为 verified/report_eligible。
- Markdown Writer 生成的是“首版知识结构已经形成”等模板式结论，没有根据质量失败或弱证据降级表述，进一步放大了错误结果的可信外观。

## 质量流水线优化结论
- 仅靠 query normalization 或 browser-first 抓取不能保证来源质量；必须在 crawler、ranking、completeness、quality checker 和 writer 五个层级同时设门禁。
- QueryEngine 的 `source_type=official` 只能表示“检索意图”，不能表示“结果已经是官方来源”；可信度必须结合 URL netloc、候选官方域名和高权威域名白名单判断。
- MediaEngine 的平台分类不能把未知域名回退成 requested platform type；未知来源应保持 `unknown`，由后续质量门禁决定是否补检索。
- CompletenessEvaluator 和 QualityChecker 现在都要求至少存在 `high` 或 `medium` 可信来源；只有 unknown/low 来源会触发 `no_authoritative_source` / `source_quality_failed` 并进入 research flow。
- Markdown Writer 的结论应反映当前门禁状态：`pass` 才能表达可进入治理流程，`supplement_required` 必须明确是草稿并提示补检索。

## QueryEngine 查询计划优化结论
- QueryEngine 原先已有 `SearchPlan` 和一次反思补检索，但计划更像内部 query 列表；现在显式建模为 `SearchQuestion`，让“要问什么、用什么 Google 风格查询、要拿哪些信息、什么算满足、失败怎么补查”都可审计。
- 初始检索按 `SearchPlan.questions` 顺序逐项执行，`search_history` 记录 question、query、expected_info、hits、status 和 source_type，后续反思能绑定到具体不足问题。
- fallback reflection 只针对 `status=insufficient` 的问题生成补检索，避免泛化重复搜索；LLM reflection 也拿到完整问题清单和检索轨迹。
- query-plan fallback 来源现在统一标记为 `publisher=query-plan`、`reliability=unknown`、`source_type=query_plan`，避免“只有计划没有网页证据”时误通过来源质量门禁。

## QueryEngine 日志可见化结论
- 仅把计划写进 `raw_material` 不够，前端需要结构化字段才能稳定展示；因此 `EngineRunResult.execution_log` 作为各 Engine 的可选执行事件输出，当前先由 QueryEngine 填充。
- `TaskService` 会把各 Engine 的 `execution_log` 聚合到任务响应顶层，并同步写入 audit jsonl；这样 UI、API 和磁盘日志看到的是同一组事件。
- 新增 `/tasks/{task_id}/logs` 用于读取 audit 日志，适合前端“查看日志”按钮和后续排障。
- 端口 5000 在当前机器被 macOS AirTunes 占用并返回 403；本轮验证使用 `http://127.0.0.1:5001/`。

## 任务列表保存与查看结论
- 任务本体已经由 `TaskStateStore` 按 `task_id.json` 持久化，因此列表不需要新增独立数据库或索引文件；扫描已保存 JSON 并提取摘要即可满足“保存和查看”。
- `GET /tasks` 返回 `count` 与任务摘要数组，摘要包含 task_id、状态、领域、子领域、轮次、文档路径、版本、研报资格和更新时间。
- 前端任务列表面板只展示摘要并支持点击回填 Task ID，避免把完整任务 JSON 塞进列表导致页面过重。

## QueryEngine 查询计划文件落盘结论
- 用户期望在 `save/{领域}/{子领域}` 目录下看到查询计划，因此仅存于 API / 前端 / audit log 不够；查询计划属于 Agent 中间产物文档，应按知识文档规范保存。
- Markdown Writer 现在会为 QueryEngine 的 `查询计划：` raw material 与 `execution_log` 生成独立 `doc_type=note`、`source_type=query` 文档，文件名后缀为 `-query.md`。
- 综述文档的“后续动作”会引用查询计划文件路径，方便从主文档追溯到查询决策。
- `save/` 目录在 `.gitignore` 中被忽略，本地已生成的领域文档不会进入 git 提交。

## QueryEngine 查询计划清单化结论
- 查询计划应该先表现为“需要查询的内容列表”，而不是只有问题和 query 字符串；因此 `SearchQuestion.search_targets` 成为计划项的可勾选查询内容。
- 执行状态从 `satisfied` 改为更适合 UI 和审计的 `completed`，并显式经过 `in_progress`，便于前端展示“查询中 / 已完成 / 需补检索”。
- 前端现在优先从 `execution_log` 重建结构化计划卡片，而不是解析 raw markdown 文本，展示更稳定。
- Markdown query plan 文件保留 `☑/☐` 勾选符号与查询内容列表，便于人工审阅。

## 前端实时查询进度结论
- 同步 `/tasks` 接口无法让前端看到 QueryEngine 中间状态；需要新增异步启动接口，先返回 `task_id` 与 `running` 状态，再由后台线程执行 workflow。
- QueryEngine 节点内统一通过 `_record_event` 写 `execution_log`，并在存在 `task_id` 时立即回调 `TaskService` 写 audit jsonl，避免等任务完成后才看到计划和执行轨迹。
- 前端创建任务改走 `/tasks/async`，随后轮询 `/tasks/{task_id}/logs` 和 `/tasks/{task_id}`；查询计划卡片可实时显示待查询、查询中、已完成和需补检索。
- `RequestContext.task_id` 作为本轮最小运行期关联字段，解决 QueryEngine 在并行线程内无法通过外层上下文可靠拿到当前任务 ID 的问题。

## 任务管理功能结论
- 任务管理仍以本地 task state JSON 为事实源；修改任务只更新 `request_context`、`task_status` 和 `management_metadata`，不重写已生成知识文档。
- 运行中的异步任务不能修改或删除，否则后台 workflow 可能把已删除状态重新写回，造成 UI 与落盘状态不一致。
- 删除任务会移除 task state 与 frozen version；知识文档仍按 `save/` 事实存储保留，避免误删领域知识正文。
- 修改和删除都写入 audit 事件，便于审计是谁在任务生命周期上做过管理操作。

## 前端动作实时展示修复结论
- 直接任务创建已经走 `/tasks/async`，但 intake 确认此前仍走同步 workflow，会导致“确认并启动任务”直到后台执行完成后才返回，前端无法看到中间动作。
- QueryEngine 的实时事件此前主要进入 audit jsonl；任务详情 JSON 不会随每条中间事件刷新，因此前端轮询 `/tasks/{task_id}` 时缺少当前动作与中间 execution_log。
- 修复后，intake 确认复用异步任务启动路径，前端拿到 `task_id` 后立即轮询日志和任务详情。
- 修复后，QueryEngine 每条实时事件会同时写入 audit log 和运行中任务快照，并生成 `current_action`，用于前端摘要区实时展示。
- 追加修复：`/tasks/{task_id}/logs` 不能只读 audit jsonl；当运行中任务快照已经有新的 `execution_log` 而 audit 文件缺项时，需要在读取 logs 时补写缺失事件，保证日志接口和落盘 jsonl 一致。

## 三路 Agent 计划确认结论
- QueryEngine 原有计划能力可以复用为 `EnginePlan`，关键是把“生成计划”和“执行搜索”拆开，避免 `/tasks/async` 一创建就触发真实采集。
- MediaEngine 需要把 social / community / blog 三类查询统一映射为计划项，否则前端无法用同一个组件展示三路计划。
- InsightEngine 虽然当前仍是轻量本地上下文实现，也需要显式计划项，才能让三路采集在用户确认阶段保持一致体验。
- `awaiting_plan_confirmation` 应允许修改或删除任务，但不能 resume；真正后台执行只从 `POST /tasks/{task_id}/plan/confirm` 启动。
- Flow Map 使用 `WorkflowStepEvent` 比直接推断 `task_status` 更稳定，因为一个任务状态无法表达 planning、collecting、writing、governing 等细粒度前端焦点。
- 计划进度展示应以最终任务状态为准：`verified` 表示三路计划已经完成执行，不能再让 QueryEngine 过程日志里的 `insufficient` 覆盖最终进度。

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
*防止视觉信息丢失*
