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

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
*防止视觉信息丢失*
