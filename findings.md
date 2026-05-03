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

## 2026-05-03 真实代码流程对齐结论
- 当前真实主流程已经从旧的“三路计划确认后并行采集，再统一写文档”演进为“意图识别 → 结构图谱 → Neo4j 任务图 → 串行知识点文件生成 → 文件级证据队列 → 单条证据即时回写 → 父级状态聚合 → 治理质检 → 版本研报”。
- `/tasks`、`/tasks/async` 与 intake confirm 已统一经过 `IntakeClarifier` 风格的归一化逻辑，`request_context` 会保留 `original_input`、`normalized_domain` 和 `confirmed=true`；概念解释类输入不能绕过 intake 直接创建知识库任务。
- Neo4j 结构节点现在承担任务状态职责：`planned`、`generating`、`generated`、`evidence_pending`、`evidence_running`、`completed`、`failed` 是主状态流转；`is_generated`、`is_completed`、`generated_path`、证据计数与父节点 ID 是前端和治理层共享字段。
- 证据回填不再等待所有队列完成。每个 query task 完成后会立即更新目标 Markdown contract、队列 JSON、图谱节点和 SSE payload；最终 `fill_evidence` 只做收尾校验和兼容兜底。
- 前端实时同步的主通道是 SSE。`/tasks/{task_id}/stream` 直接带 `graph_snapshot`、`graph_event`、`file_update`，`/tasks/{task_id}/graph` 只保留给手动刷新、Neo4j 重连和兜底展示。
- 历史文档中“前端轮询后再拉图谱”“最后统一回填”“默认等待三路计划确认”的描述均视为旧阶段记录，不再代表当前主流程。

## 2026-05-03 架构 Review 去人工化与 Neo4j 上下文增强
- 当前 `KnowledgeGraphWorkflow._run_structure_review` 只把本地 `structure_graph`、领域、子领域和关注点传给 LLM，没有查询当前知识 ID 在 Neo4j 中的相关节点、关系与状态。
- 当前图执行顺序是生成结构图谱后先同步 Neo4j；第一轮 review 如果直接通过，会进入第二轮，中间没有再同步 Neo4j；第一轮有缺口时会在 repair 后同步。
- `sync_structure_graph` 写 Neo4j 时使用 `coalesce(n.generation_state, 'planned')`，会保留旧状态，无法用后续 review 阶段的本地 `reviewing/approved` 状态覆盖 Neo4j。
- 测试中已有失败态文案不包含“人工”的回归断言，但 review payload 仍可能传入 `suggested_repairs=[{"type": "manual_review"}]` 并被原样保存。

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

## 项目结构重组发现
- 迁移前 Flask 工厂位于 `knowledgeforge/api.py`，根目录 `app.py` 只是启动入口；迁移后保留根入口并改为导入 `knowledgeforge.server.create_app`，避免破坏现有启动习惯。
- 迁移前前端资源位于 `knowledgeforge/templates` 与 `knowledgeforge/static`，HTML 使用 `url_for('static', ...)`；迁移到 `knowledgeforge/web` 后在 Flask 构造函数中显式设置 `template_folder`、`static_folder` 和 `static_url_path="/static"`，保证 URL 不变。
- 迁移前三路 Engine 位于仓库根目录 `agent/`，项目代码、脚本和测试都大量引用 `agent.*`；迁移到 `knowledgeforge/agent/` 后已统一替换导入路径，保持 Engine 内部结构不变。

## 视觉/浏览器发现
- 当前问题仍是范围与阶段划分，不是视觉布局问题，暂不需要浏览器图示。

## 已确认的设计共识
- 整体架构采用 Flask Web 层 + LangGraph Orchestrator/Router + InsightEngine/QueryEngine/MediaEngine + 文档/图谱/质量/版本模块。
- 第一批实施按“前半段主链路做实、后半段关键骨架接上”的方式推进。
- 完整性评估为独立评估节点；Neo4j 失败采用 `graph_sync_pending` 异步补偿；版本冻结点在质量通过且文件图谱一致之后。
- 核心模块边界固定为 Web Interface、Orchestrator、Context Builder、三大 Engine、Completeness Evaluator、Knowledge Document Writer、Post-Storage Pipeline、Report Branch。
- 当前任务数据流固定为“输入 → 真实意图识别 → 结构图谱规划 → Neo4j 任务图同步 → 串行文件生成 → 证据队列执行 → 即时回写 → 父级完成聚合 → 后置治理 → 版本化 → 可选研报”，并以本地 Markdown 作为源事实存储。
- 回流规则固定为 repair_flow 与 research_flow 两类，禁止仅返回模糊失败。
- 质量状态固定为 `passed` / `repair_required` / `research_required`；达到最大轮次、补偿或最小新增阈值时转入 `needs_human_review`。

## QueryEngine 补充结论
- 参考 BettaFish 的 QueryEngine 设计思路，更适合当前项目“节点化能力增强 + 单引擎可独立测试”的演进方向。
- 真实网络检索会拖慢 `workflow` 测试，后续需要更稳定的测试隔离策略，避免外部网络扰动主链路回归结果。
- 默认回退输出仍需保留可追溯来源，否则更容易触发完整性评估失败，削弱质量闭环判断的可信度。
- 把 `SearchQuestion` 作为独立网络任务进行队列化，比“一个节点内串行扫完所有 query”更适合控制抓取速度；当前以 5 并发作为默认上限，可以先缓解 browser / provider 被瞬时打满的问题。
- 单次网络查询失败不应上升为整轮 QueryEngine 失败；更稳的策略是记录 `network_query_failed`，继续执行 fallback query、其他计划项和最终总结，让补检索与质量闭环再决定是否继续回流。
- browser 搜索主路径切到 Google 后，QueryEngine 的“Google 查询计划”与实际执行路径终于一致；HTTP fallback 仍保留多 provider 链，避免 browser/google 一处异常时整条链路失效。
- 对中文社区/百科类来源不能只看“配置里有这个 URL”；必须把“URL 当前是否可用”显式建模，否则像知乎搜索页、中文维基搜索页这类目标会在某些网络环境下稳定返回 403，却仍被误当成可补源。
- 针对站点级补源，最稳的方案不是直接把所有备用源硬塞进结果，而是“先探测、再合并、最后去重排序”；这能保持来源可追溯，也避免把明显失效的 URL 写入后续知识文档。

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

## 串行文件生成与域级队列重构结论
- 如果把 `EngineRunResult` 这类运行时对象直接写进领域级队列 JSON，会在保存队列时触发序列化失败；队列协议必须只保留纯 JSON 字段，运行结果对象应只存在于 `agent_outputs`。
- 知识文件数量很多时，若每个文件都默认生成查询任务，会让串行流程退化成非常重的长任务；更稳的方案是以蓝图中的 `required_query_tasks` 作为显式开关，只给真正需要依据闭环的文件建队列任务。
- 即便整体转为“文件级补全”流程，继续在 fill pass 后保留 mixed 汇总文档，能最大程度兼容现有 post-storage / quality / versioning 链路，避免为了流程重构同时打碎治理链。
- 异步 UI 轮询并不需要继续理解旧的三路计划；只要稳定暴露 `generation_progress`、`task_queue_snapshot` 和新的 workflow step，就能完整呈现“生成了什么、还差哪些依据、当前在执行哪一个任务”。

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

## 执行进度卡死排查结论
- 异步任务此前只有 workflow step 事件和 Query / Media 实时事件会刷新运行中任务快照；`evaluate_completeness`、`write_markdown`、`run_post_storage` 等节点返回的新 `task_status/current_step/current_action/round_number` 要等整条 workflow 结束后才整体落盘。
- 这会导致前端在轮询 `/tasks/{task_id}/logs` 时长期看到旧快照，例如一直停在 `running + evaluating`，即使后端内部已经继续到补检索准备或后续节点。
- 修复方式是：在 workflow 每个关键节点结束后立即提交中间 state 快照到 `TaskStateStore`，让运行中任务也具备“按节点落盘”的可观察性。
- 额外补强：`/tasks/{task_id}/logs` 现在除了日志，还直接返回最新的 `task_status/current_step/current_action/round_number/workflow_events/agent_plans`，避免前端必须等下一次 `/tasks/{task_id}` 才拿到新状态。

## 补检索轮次门禁结论
- 源需求和流程文档都明确主链路是“并行采集 → 完整性评估 → 补检索策略 → 再次并行采集”；补检索不应在评估后直接绕过其他 Engine 单独执行。
- 旧实现里 `evaluate_completeness -> query_supplement -> evaluate_completeness` 会让 QueryEngine 补采直接回评估，等于把第二轮缩成了单引擎补跑，和三路并行采集约束不一致。
- 现在补检索节点只负责生成下一轮 QueryEngine 补采计划，并把 round 推进到下一轮；真正的执行会回到 `collect_parallel`，由 Insight / Query / Media 三路一起完成后再重新评估。
- 这样做的直接收益是：前端计划进度、轮次和当前动作与真实流程重新对齐，也更符合后续“状态持久化与恢复”对轮次边界清晰可审计的要求。

## 任务列表保存与查看结论
- 任务本体已经由 `TaskStateStore` 按 `task_id.json` 持久化，因此列表不需要新增独立数据库或索引文件；扫描已保存 JSON 并提取摘要即可满足“保存和查看”。
- `GET /tasks` 返回 `count` 与任务摘要数组，摘要包含 task_id、状态、领域、子领域、轮次、文档路径、版本、研报资格和更新时间。
- 前端任务列表面板只展示摘要并支持点击回填 Task ID，避免把完整任务 JSON 塞进列表导致页面过重。

## QueryEngine 查询计划文件落盘结论
- 用户期望在 `save/{领域}/{子领域}` 目录下看到查询计划，因此仅存于 API / 前端 / audit log 不够；查询计划属于 Agent 中间产物文档，应按知识文档规范保存。
- Markdown Writer 现在会为 QueryEngine 的 `查询计划：` raw material 与 `execution_log` 生成独立 `doc_type=note`、`source_type=query` 文档，文件名后缀为 `-query.md`。
- 综述文档的“后续动作”会引用查询计划文件路径，方便从主文档追溯到查询决策。

## MediaEngine 计划去重结论
- MediaEngine 的重复计划不能只靠“完全相同字符串”去重；很多冗余来自同一主题意图只换站点、引号、OR 词或轻微修饰词。
- 更稳的做法是双层收敛：prompt 明确“最少必要查询 + 每类数量上限 + 同类必须覆盖不同信息目标”，执行层再按语义 key 做兜底去重。
- 补检索也必须复用同样的去重思路；否则首轮计划收敛后，reflection 仍会把同一意图换个平台重新补回来。
- 对当前 MediaEngine，较稳的上限是 `social<=2`、`community<=3`、`blog<=2`，并要求按信息价值排序，让系统优先执行最有信息密度的 query。
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
- AntV X6 更适合作为实时流程图主展示层：节点和边可直接由同一批 `WorkflowStepEvent` JSON 生成；原 HTML 卡片应继续保留为 X6 CDN 未加载或禁用脚本时的回退。

## 查询计划不足门禁结论
- 仅看“有中高可信来源”不够；如果 QueryEngine 的结构化计划项仍有 `insufficient`，说明用户确认的检索目标没有完成，不能进入 verified。
- `deep learning 基础概念 tutorial guide` 这类中英混杂 query 容易空命中，fallback plan 应把常见中文子主题映射为英文检索 topic，同时保留中文问题标题给用户阅读。
- 主知识文档不适合展开完整查询执行清单；计划明细应保存在独立 query 文档，主文档只保留可读摘要、证据和后续动作。
- 测试环境的 no-op crawler 应提供稳定 fixture，而不是空结果；空结果代表真实检索失败，会触发新门禁。

## 计划阶段 LLM-only 结论
- 用户确认前的三路计划属于关键决策，不应在 LLM 不可用时悄悄降级为规则计划，否则前端看不到真实失败。
- Query / Media 的规则 fallback 已移除；Insight 也改为 LLM 计划，保持三路体验和审计口径一致。
- 计划失败是任务终态 `plan_failed`，不是 `failed` 或 `supplement_required`；它表示“执行尚未开始，规划阶段就失败”。
- 前端与 logs 都需要呈现失败原因：`current_action` 给用户看，`agent_plan_failed` 和 `workflow_step(blocked)` 给排障看。
- LLM-only 后，计划阶段 timeout 不能沿用 1.5 秒这类实时展示优化值；计划是阻塞决策点，默认应给更长窗口，并通过 `PLAN_LLM_TIMEOUT` 配置化。
- 三路计划不适合并发压同一个本地 LLM 服务；并发会让某一路排队到 timeout。计划阶段改为顺序调用更符合“先拿到可审查计划”的交互目标，真正执行采集阶段仍保持并行。
- MediaEngine 计划阶段不能复用 execution client；否则即使全局 planning timeout 已放宽，Media 的归一化和计划仍会被 5 秒执行超时截断。

## 补充模块 index 决策结论
- 补充检索不应只从完整性评估的规则 query 出发；实时保存的领域 `README.md`、独立 query plan 文档和已保存文章能暴露更具体的结构缺口。
- LLM 补充决策应位于 Orchestrator / Evaluator 附近，而不是塞进 QueryEngine 内部；QueryEngine 只负责执行“补什么”的事实检索，避免跨 Engine 决策耦合。
- 补充决策输出需要结构化为缺陷、优先级、query、预期信息、fallback 和成功标准，才能被前端、audit、Markdown 后续动作稳定审计。
- LLM 不可用时可以退回完整性评估生成的补查 query，但必须标记 `source=fallback_saved_document_review`，不能伪装成 LLM 文档审阅分析。
- 第二次完整性评估通过后仍应保留上一轮 `supplement_decision`，否则最终任务只能看到“已通过”，看不到为什么曾经补采、读了哪些 index 文件。

## 保存文档概述驱动补检索结论
- 仅把整段 Markdown 原文截断后交给补充决策器还不够稳定；先抽取“摘要 / 关键结论 / 后续动作 / 背景与上下文”形成概述，再让 LLM 判断缺口，更贴近知识文档格式规范，也更省上下文。
- `reviewed_documents` 应进入 `CompletenessResult.supplement_decision`，这样前端和审计都能直接看到“LLM 实际看了哪些保存文档”，不会把补检索决策变成黑盒。
- 前端不需要新建独立协议；复用现有任务快照轮询和计划面板，增加一张“补检索分析”卡片，就能把已审阅文档、覆盖概述和缺口判断实时暴露出来。
- 补检索节点开始时应先把 `current_action` 切到“正在分析已保存文档概述”，这样用户在前端能明确感知当前并不是重新抓取，而是在做已有知识审阅与补查规划。

## 实时文件审查保存结论
- Query / Media 的合格资料不应等完整性评估后才落盘；按计划项实时保存能让补充决策读取更真实的领域 index。
- 保存粒度采用“每个计划项一篇 Markdown”，比逐来源保存更可控，同时仍在 front matter 和证据表中保留每个 URL 的追溯信息。

## 文件级知识库闭环结论
- 仅用 `planned_path` 还不足以表达“整个知识领域应生成哪些文件、哪些文件必须完成、哪些证据还缺失”；需要把知识树提升为显式蓝图对象。
- 把待查询信息写进 Markdown 固定 JSON 合同区块，比散落在 prompt 或 execution log 里更稳定，代码也能直接提取 `query_tasks` 做后续检索。
- file-level 模式下，完整性评估不应继续强依赖旧的模块执行日志门禁；更稳的做法是优先看统一 artifact 状态，再把旧日志逻辑退回兼容兜底。
- 三路 Engine 若不统一输出 `target_file_path` / `target_section`，Writer 就无法把背景、事实和趋势稳定地合并回同一知识文件，最终会重新回到“结果散落”的旧问题。
- 领域索引继续使用 `save/{领域}/README.md`，不新增平行 `index.md`；每次实时保存后刷新“实时保存文档”区块。
- 实时保存文档只能是 `draft`，不能替代最终综合文档、结构化治理、Neo4j 路径关联和质量检测。
- 文件写入失败属于 `file_write_failed`，应进入 audit / execution log，但默认不打断 Query / Media 的采集线程。

## 前端步骤显示优化结论
- 用户需要在流程图上直接看到“实时沉淀”，否则 Query / Media 已经实时保存文件但 UI 仍像是在单纯采集。
- `realtime_saving` 可以由 execution log 合成前端步骤，不需要改后端 LangGraph 主节点；这样不破坏现有编排顺序。
- Agent 计划卡片比原始日志更适合承载保存路径、跳过来源和失败状态，因为用户确认的是计划项，实时保存也按计划项发生。
- MediaEngine 需要和 QueryEngine 一样从日志回填计划项执行状态，否则最终完成前只能看到静态 approved 计划。

## 计划去重与生成计划落盘结论
- Query / Media 计划重复既可能来自 LLM 输出本身，也可能来自前端把 `agent_plans` 与执行日志重新合成卡片；需要在后端生成、执行转换和前端展示三层都保持幂等去重。
- QueryEngine 计划按标准化 `google_query + search_targets + source_priority` 去重；MediaEngine 计划按平台类型和标准化 query 去重，避免同一查询项在确认页重复出现。
- MediaEngine 执行日志必须携带原始 `plan_item_id`，前端不能只靠平台类型和 query 顺序猜测计划项，否则日志回填容易生成额外卡片。
- 用户确认前生成的计划也是可审计中间产物，应在 `save/{领域}/{子领域}` 下立即保存为 `doc_type=note`、`source_type=agent_plan` 的 Markdown 文档，而不是等最终综述写入后才看到 Query 执行计划。
- 计划文档不是只读快照；用户在等待确认阶段 PATCH 或 DELETE 计划项后，task state 与对应 `*-plan.md` 必须同步更新，否则页面和后端文件会出现两个事实源。
- 计划文档同步失败应写入 `plan_document_sync_failed` 审计事件，便于区分“状态更新成功但文件写入失败”和“接口整体失败”。

## Token 记录与实时展示结论
- Token 记录应接在 OpenAI-compatible client 封装层，而不是散落到 Engine / Node 内部；这样 planning、execution、intake 和 embedding 调用可以统一审计。
- 当前任务或 intake session 需要通过运行期上下文传给 LLM client，否则并行线程和后台任务很难把一次模型调用稳定归属到正确任务。
- Token 使用记录适合写入 audit jsonl，并由 `/tasks/{task_id}/logs` 汇总返回；前端已有实时轮询，不需要新增第二套推送机制。
- Provider 未返回 usage 或调用失败时仍要记录一次调用事件，`source=unavailable`、`status=failed`，避免“没有用量数据”被误读成“没有调用”。
- 前端 token 展示更适合做左下角悬浮窗，默认收起，不占用主流程和计划展示空间；展开后只保留发送、接收、总计和调用次数四项，降低噪音。
- Provider 未返回 usage 时，Chat 调用按发送 prompt 与接收 content 估算；Embedding 调用按 input 文本估算发送 token，接收 token 记为 0。记录需标记 `source=estimated`，避免和 provider 精确 usage 混淆。

## 生成与查询队列状态结论
- 队列 JSON 写入不等于前端可见状态；运行中 task snapshot 必须和 `knowledge_task_queue.json` 在关键状态点同步，否则 `/tasks/{task_id}` 会显示旧进度。
- “查看队列”接口应以 `task_queue_path` 指向的本地队列文件作为兜底事实源，这符合领域级队列作为持久化协议的定位，也能避免任务状态短暂滞后。
- 领域级 `knowledge_task_queue.json` 是当前任务活动队列，不是历史记录；新任务启动时应重新初始化，否则同领域旧任务的 `final_status`、生成进度和任务列表会污染当前流程。
- 轮次验证返回“不完整”时必须携带下一步可执行任务；如果没有 LLM 新任务，应把当前轮未完成项显式转成下一轮 retry 任务。否则 LangGraph 会在空队列轮次里循环，前端表现为查询队列卡住。
- 质量治理的任务状态要跟 remediation flow 对齐：证据不足、弱来源、断裂引用属于 `research_required`；结构化抽取、元数据、图谱路径问题属于 `repair_required`。

## 知识框架优先流程结论
- 默认产物应是“领域知识框架 + 官方/权威证据”，而不是每个知识点的完整正文；这样用户先获得一眼可读的学习地图、角色、顺序和证据基础。
- `completion_mode` 需要表达产品意图：`framework` 是默认必做链路，`full_document` 是最后补全完整知识库文档；旧 `file_level` 只能作为兼容别名，不能继续代表默认主线。
- 框架证据文件的质量标准应看图谱、蓝图、证据文件、官方来源和路径关联；不能继续用完整文章的“摘要/正文”结构作为默认门槛。
- 实时来源保存可能刷新领域 README 和部分 index 文档；治理框架模式时应选择仍保留“知识定位/证据与来源”的框架证据文件作为代表 artifact，而不是固定使用领域 README。
- 完整文档生成必须在证据闭环之后执行，避免“先写长文再找证据”的流程把知识库变成不可追溯摘要。

## 知识架构 Review 优先流程结论
- 用户重新定义核心链路：LLM 生成的知识架构图谱必须先在 Neo4j 呈现，并经过两轮 review 检查完整性；只有架构通过后才生成本地架构文档。
- 两轮 review 是架构阶段的完成门槛，不再由父级 SubTopic / Domain 聚合状态判断架构是否完整。
- 证据阶段的职责收窄为“找到真实、可访问、最贴近知识点的官方或高公信力链接”，链接内容解析和正文补全属于后置文档补全阶段。
- 主链路默认只使用 QueryEngine 执行链接查询；MediaEngine 保留给后续文档补全、社区观点或扩展材料，不参与默认架构证据链接阶段。
- `knowledge_task_queue.json` 从内容回写队列收敛为链接队列，核心结果字段为 `selected_link`、`source_kind`、`reachable`、`relevance_reason` 和 `checked_at`。

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
*防止视觉信息丢失*
