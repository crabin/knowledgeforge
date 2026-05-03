# Progress

## 2026-05-03

- 按当前真实代码流程同步核心设计与执行文档：`README.md`、`docs/项目需求.md`、`docs/流程执行文档.md`、`docs/知识文档格式规范.md`、`docs/知识库文件架构设计.md`、`task_plan.md`、`findings.md`。
- 文档主流程统一为：真实意图识别 → 结构图谱规划 → Neo4j 任务图初始化 → 串行知识点文件生成 → 文件级证据队列 → 单条证据即时回写 → 父级状态聚合 → 治理质检 → 版本研报。
- 明确 `/tasks`、`/tasks/async` 与 intake confirm 均会先归一化领域和意图；非 `knowledge_collection` 直接任务会被拦截。
- 明确 Neo4j 节点状态字段、父级完成聚合规则、Markdown contract 与 `knowledge_task_queue.json` 的即时同步职责。
- 明确 SSE 是实时图谱与文件回写状态的主同步通道，`/tasks/{task_id}/graph` 与手动刷新保留为 fallback。
- 保留历史阶段记录，但将“最后统一回填”“前端 SSE 后自动拉 `/graph`”“默认三路计划确认”等旧描述标记为历史或兼容兜底。
- 未改动 `docs/流程图.excalidraw`，避免直接编辑 Excalidraw JSON 破坏画布；当前权威流程以 Markdown 文档和前端 Flow Map 为准。

## Verification

- 运行关键词扫描，确认主文档不再把“最后统一回填 / 前端自动拉 `/graph` / 默认三路计划确认”描述为当前主流程；旧词只保留在历史记录或兼容兜底说明中。
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`152 passed in 30.05s`

## 2026-05-03 前端空图谱快照修复

- 修复 SSE 任务流里 `graph_snapshot={}` 时前端误进入图谱渲染分支的问题。
- 新增图谱 payload 归一化逻辑，所有图谱输入都会先转成 `{nodes: [], edges: []}`，避免读取 `graph.nodes.length` 时触发 `Cannot read properties of undefined`。
- 空图谱快照不再触发本地图谱渲染；手动 `/graph` fallback 仍可显示无图谱数据状态。

## Verification

- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py tests/test_workflow.py`
- 结果：`38 passed in 7.88s`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`152 passed in 27.67s`
- 使用 in-app browser 刷新 `http://localhost:5001/`
- 结果：页面不再显示 `client_error`，浏览器 error logs 为空。

## 2026-05-03 开发期系统初始化功能

- 新增 `POST /system/initialize`，用于开发 / 测试阶段初始化运行产物。
- 初始化范围限定为任务状态、intake session、audit JSONL、冻结版本、`save/` 生成文件和 KnowledgeForge Neo4j 图谱节点。
- 初始化会保留源代码、配置、项目文档、依赖、ChromaDB、MySQL 和应用日志等系统数据。
- 若存在运行中任务，接口直接拒绝初始化，避免后台 workflow 继续写回已清理状态。
- 前端任务操作区新增“初始化系统”按钮，点击后会二次确认清理范围。
- Neo4j 清理只针对 KnowledgeForge 主标签节点，并仅删除由 Article 关联的实体，避免按泛用 `Entity` 标签误清全库实体。

## Verification

- 运行 `python -m py_compile knowledgeforge/graph/client.py knowledgeforge/services/task_service.py knowledgeforge/server/api.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py`
- 结果：`7 passed in 0.63s`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`154 passed in 24.15s`
- 尝试用 in-app browser 刷新验证按钮可见性时，Browser Use 因自身安全策略拒绝本次页面访问；未绕过该策略，改以模板测试覆盖按钮渲染。

## 2026-05-03 初始化前停止运行任务

- 调整 `POST /system/initialize`：不再因为存在运行中任务直接返回 400，而是先登记运行中任务为 stopped / cancelled，再清理运行产物。
- 后台 workflow 线程如果在初始化后继续触发状态写回，会被服务层取消标记拦截，不再重新写出已清理的 task state。
- 初始化响应新增 `stopped_task_ids`，便于前端和调试时确认本次初始化停止了哪些任务。

## Verification

- 运行 `python -m py_compile knowledgeforge/services/task_service.py knowledgeforge/server/api.py knowledgeforge/graph/client.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py`
- 结果：`7 passed in 0.73s`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`154 passed in 24.44s`

## 2026-05-03 当前任务执行耗时展示

- 任务状态新增 `started_at`、`finished_at` 和 `task_timing`，后端统一计算当前任务已执行秒数。
- `/tasks`、`/tasks/{task_id}`、`/tasks/{task_id}/logs` 和 SSE payload 均可携带任务耗时信息。
- 前端“响应与关键字段”摘要区新增“执行耗时”，运行中任务会按本地时间每秒刷新展示。
- 任务列表摘要补充 `started_at` / `finished_at`，方便后续扩展任务历史耗时显示。

## Verification

- 运行 `python -m py_compile knowledgeforge/services/task_service.py knowledgeforge/orchestrator/state.py knowledgeforge/runtime/state_store.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py`
- 结果：`40 passed in 6.05s`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`154 passed in 34.46s`

## 2026-05-03 X6 流程图与 Neo4j 图谱布局优化

- 流程图从两行折返改为桌面端单行自适应布局，小屏再切换纵向布局，减少箭头折返和重叠。
- 流程图边改为基于端口的直线连接，避免箭头穿过节点内容。
- Neo4j 图谱默认改为自上而下的分层垂直排列，节点按层居中铺开，箭头从节点底部连到下一层顶部。
- Neo4j 图谱渲染后会自动缩放并居中到可视容器；超大图保留可滚动画布高度作为兜底。
- 图谱容器允许滚动查看，避免大型结构图只能看到局部。

## Verification

- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py tests/test_workflow.py`
- 结果：`40 passed in 7.65s`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`154 passed in 27.26s`
- 使用 in-app browser 刷新 `http://localhost:5001/`
- 结果：页面没有新增前端 error。

## 2026-05-02

- Implemented graph-driven directory planning: workflow now generates an LLM-backed directory structure graph, derives dynamic blueprints, and uses the graph context during file generation.
- Added dynamic structure graph normalization, fallback graph generation, path validation, blueprint derivation, and Neo4j structure graph syncing.
- Updated workflow/dashboard observability for `structure_graph_planning` and `structure_graph_ready`.
- Verification: `PYTHONPATH=. pytest` passed with 146 tests.
- Follow-up: none currently required.

## 2026-04-27

- 完成“文件级知识库生成-查询-补全”第一版落地。
- 为 `RequestContext`、`EngineRunResult` 与知识树配置补充文件级蓝图、required files、completion mode、artifact 等结构化字段。
- 将 `knowledgeforge/utils/knowledge_tree.py` 升级为完整知识库蓝图生成器，默认覆盖 `00_overview` 到 `07_review`，并为领域/模块/主题文件分配稳定角色、owner engine 和完成要求。
- 新增 `knowledgeforge/utils/file_contract.py`，为知识文件定义固定 JSON 合同区块；Writer 现在会先全量物化骨架文件，再由各 Engine 回写状态与贡献内容。
- `MarkdownKnowledgeWriter` 现已支持全量知识树骨架创建、JSON 合同生成、artifact 回写和生成文件跟踪，同时保留现有 mixed 汇总文档输出链路。
- `QueryEngine` 现优先从骨架 Markdown 的 JSON 合同读取 `query_tasks` 作为文件级检索输入，而不是只依赖自由搜索问题。
- `InsightEngine`、`MediaEngine`、`QueryEngine` 的计划元数据与运行结果都已补充 `target_file_path` / `target_section` / `artifacts`，可对齐到同一知识文件架构。
- `CompletenessEvaluator` 新增 file-level 模式，优先按文件级 artifact 完成状态判断，而旧的模块执行日志门禁退回兼容兜底路径。
- `KnowledgeGraphWorkflow.generate_plans()` 现会在三路计划生成前先物化整套知识库骨架，并把文件状态带入运行时状态。
- 新增 `tests/test_knowledge_blueprint.py`，覆盖知识库蓝图生成与骨架 JSON 合同可解析性。
- 完成 QueryEngine 文章级采集计划升级。
- 将 Query 计划项从笼统查询问题扩展为可序列化的文章级条目，支持 `url`、`subdomain`、`doc_type`、`planned_path` 等元数据。
- 在 Query 计划阶段加入轻量候选检索，确认前即可得到链接级采集计划；已有 URL 会在计划中标记为 `skipped`。
- 将 Query 执行流改为按 URL 抓取并按“一链接一文档”实时落盘，保留来源、计划项、路径、状态与索引同步信息。
- 新增子领域 `README.md` 索引刷新，并保留领域级 `README.md` 总索引。
- 调整最终 mixed 汇总文档，使 Query 部分优先聚合已保存的文章级文档，而不是把原始查询计划当主载体。
- 完成 MediaEngine 与 QueryEngine 的计划/执行逻辑同步升级。
- 将 Media 计划从平台级 query 清单升级为确认前可见的链接级候选计划，并按单 URL 实时保存趋势/社区资料。
- MediaEngine 现在同样会携带 `url`、`subdomain`、`planned_path` 等计划元数据，并复用统一的 README / 子领域索引更新链路。
- 为 QueryEngine 增加“补充查询源”机制：当结果不足或命中知乎问题页等高风险来源时，自动补充 `腾讯云开发者社区搜索`、`知乎搜索`、`中文维基百科搜索` 三个备用 URL。
- 新增通用 URL 探测模块 `agent/QueryEngine/tools/supplemental_sources.py`，对备用源执行 HTTP 可用性检测，并识别知乎 403/封禁提示等阻断信号。
- 为 `zh.wikipedia` 增加 browser fallback 探测：当 `httpx` 返回 403 时，允许通过 browser 文本抓取二次确认该搜索页是否仍可用。
- 优化补源探测返回结构：把 `status_code` 与 `http_status_code` 分离，并新增 `probe_method`，明确区分“HTTP 首探结果”和“最终可用性判定来源”。
- 扩展补源：新增 `菜鸟教程搜索` 与 `CSDN 搜索`。其中 `菜鸟教程` 仅在 IT/教程型 query 下启用，`CSDN` 作为低优先级博客补源保留但默认降权。
- 新增 5 个独立检测脚本：`scripts/check_tencent_cloud_source.py`、`scripts/check_zhihu_search_source.py`、`scripts/check_zh_wikipedia_source.py`、`scripts/check_runoob_source.py`、`scripts/check_csdn_source.py`，可直接验证每个补源 URL 当前是否可用。
- 补充 pytest 回归，覆盖备用源 URL 生成、IT 教程型 query 判断、知乎封禁识别、Query 补源合并，以及 5 个检测脚本的退出码行为。
- 新建仓库根目录 `README.md`，补充项目定位、快速启动、目录说明与运行界面截图。
- 将两张 KnowledgeForge 控制台运行截图收纳到 `docs/images/`，用于 README 展示整体控制台与补检索运行状态。

## 2026-04-28

- 完成“串行文件生成 + 域级查询队列 + 前端实时展示”主链路重构。
- 新增 `knowledgeforge/prompts/knowledge_file_generation.py`，把知识文件结构要求、必写内容与查询提示固化为 prompt 注册表，运行时不再从设计文档动态推断。
- 新增 `knowledgeforge/runtime/domain_task_queue_store.py`，把领域级 `knowledge_task_queue.json` 作为文件生成状态、查询任务、轮次验证与最终回填的唯一持久化协议。
- `KnowledgeGraphWorkflow` 改为 `generate_files -> run_query_queue -> validate_round -> fill_evidence -> run_post_storage` 的串行流程，移除旧的默认“等待确认计划”主入口。
- 文件骨架生成阶段改为严格串行，一次只生成一个 Markdown，并在保存后立即提取 `query_tasks` 写入领域级队列。
- Query / Media 在新流程里改为单 task 执行器，队列按任务串行执行，结果先写入 JSON 队列，再统一回填目标 Markdown。
- 前端流程图与状态面板改为展示 `blueprint_ready`、`llm_generating`、`query_queue_running`、`round_validation`、`evidence_filling`、`governing`、`versioning`。
- 前端交互已进一步与新流程同步：新增“查看队列”入口，`intake confirm` 后会自动进入任务轮询，摘要区与状态面板改为显示生成进度、队列进度和轮次验证，而不再沿用旧的计划确认语义。
- 将 `plan_llm_timeout` 默认值从 45 秒提升到 120 秒，降低串行文件生成阶段因单文件请求过早超时而近似卡住的概率。
- 为 OpenAI-compatible chat / embedding client 增加实时 LLM 生命周期事件：现在会在 audit/logs 中记录 `llm_call_started`、`llm_call_completed`、`llm_call_failed`，不再只在结束后留下 token 统计。
- 保留现有 post-storage / versioning 链路，但统一回填后仍生成 mixed 汇总文档，保证现有治理与冻结流程可继续消费。

## Verification

- 运行 `/Users/lpb/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m py_compile ...`
- 结果：核心改动文件均可通过语法编译。
- 运行自定义 smoke：同步 `TaskService.run_task(...)`
- 结果：返回 `task_status=verified`、`post_storage_result.status=passed`、`task_queue_snapshot.final_status=ready_for_fill`。
- 运行自定义 smoke：Flask 首页与异步任务
- 结果：`GET / -> 200`，页面包含“生成与查询队列状态”；`POST /tasks/async` 可从 `blueprint_ready` 进入并最终到 `versioning / verified`。
- 运行 `pytest tests/test_workflow.py tests/test_dashboard.py -q`（受控子集）
- 结果：测试进程在当前环境下超过 90s 超时，未完成整轮回归；已改用同步/异步 smoke 验证主路径。

## Verification

- 运行 `PYTHONPATH=. pytest -q`
- 结果：`135 passed`
- 运行 `PYTHONPATH=. pytest -q tests/test_multi_provider_search.py tests/test_source_probe_scripts.py tests/test_browser_fallbacks.py tests/test_source_relevance_filter.py`
- 结果：`34 passed`
- 运行 `python scripts/check_tencent_cloud_source.py GAN`
- 结果：`available=true, status=200`
- 运行 `python scripts/check_zhihu_search_source.py GAN`
- 结果：`available=false, status=403`
- 运行 `python scripts/check_zh_wikipedia_source.py GAN`
- 结果：`available=false, status=403`
- 运行 `uv run scripts/check_zh_wikipedia_source.py`
- 结果：`available=true, status_code=null, http_status_code=403, probe_method=browser_fallback, reason=browser_fallback_ok`
- 运行 `uv run scripts/check_zhihu_search_source.py`
- 结果：`available=false, status_code=403, http_status_code=403, probe_method=http, reason=http_403`
- 运行 `uv run scripts/check_runoob_source.py`
- 结果：`available=true, status_code=200, http_status_code=200, probe_method=http, reason=ok`
- 运行 `uv run scripts/check_csdn_source.py`
- 结果：`available=true, status_code=200, http_status_code=200, probe_method=http, reason=ok`
- 检查 `README.md` 中截图资源路径
- 结果：`docs/images/knowledgeforge-dashboard-overview.png` 与 `docs/images/knowledgeforge-dashboard-runtime.png` 已入库可引用

## Follow-up

- QueryEngine 与 MediaEngine 已统一为链接级计划和单篇落盘模式，InsightEngine 仍保持原有本地线索规划形态。
- 补检索决策已能读取领域 README、子领域 README 与已保存文章概览；若后续需要“补检索确认前也必须显式展示 URL 级计划”，可继续把 supplement planner 扩展为预检索链接生成器。
- 当前网络环境下 `知乎搜索` 与 `zh.wikipedia.org` 均返回 403，因此它们更适合作为“有条件启用并先探测”的补源，而不是无条件主源；后续如果需要稳定中文百科补源，建议增加 API/镜像级备选策略。
- 实测表明 `zh.wikipedia` 属于“HTTP 层受限但浏览器可达”，而 `知乎搜索` 属于“浏览器也会进入安全验证”；两者后续应继续分开治理，不适合共用同一放行规则。
- `菜鸟教程` 适合作为 IT 教程、语法、入门示例类查询的补源，不适合泛化到非技术主题；`CSDN` 可补博客与经验线索，但内容质量波动较大，应继续维持低权重。

## 2026-04-28 队列状态与流程控制修复

- 修复生成与查询队列状态展示：文件生成前后、队列任务开始/完成时会同步刷新运行中 task snapshot，避免前端轮询只看到旧的 `task_queue_snapshot`。
- 任务详情与“查看队列”接口现在会从 `task_queue_path` 读取最新 `knowledge_task_queue.json`，并回填 `generation_progress`，避免队列文件和任务状态短暂不同步时页面显示空状态。
- 每次新任务启动都会重新初始化领域级活动队列，避免复用同领域旧 `knowledge_task_queue.json` 导致生成进度、任务列表或 `final_status` 污染本次流程。
- 修复轮次验证空转：当验证不完整但没有新任务时，会为当前轮失败项生成下一轮 retry 任务；达到最大轮次后进入统一回填并保留缺口，避免 `validate_round -> run_query_queue` 无限循环。
- 修复治理结果分类：只有 `research_flow` 时返回 `research_required`，包含 `repair_flow` 时返回 `repair_required`，符合质量闭环中“补检索 / 修复”分流要求。

## Verification

- 运行 `PYTHONPATH=. pytest tests/test_workflow.py tests/test_dashboard.py -q`
- 结果：`31 passed`

## 2026-04-28 项目结构重组

- 将 Flask 后端工厂从 `knowledgeforge/api.py` 迁移到 `knowledgeforge/server/api.py`，新增 `knowledgeforge/server/__init__.py` 导出 `create_app`，根目录 `app.py` 继续作为启动入口。
- 将前端模板与静态资源迁移到 `knowledgeforge/web/templates` 与 `knowledgeforge/web/static`，并在 Flask app 中显式配置资源目录，保留 `/static/...` URL 不变。
- 将根目录 `agent/` 迁移为 `knowledgeforge/agent/`，同步更新项目代码、脚本和测试中的导入路径。
- 更新 `README.md`、`AGENTS.md`、`CLAUDE.md` 与 `pyproject.toml`，使目录说明和 setuptools 包发现与新结构一致。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile app.py $(rg --files knowledgeforge scripts tests -g '*.py')`
- 结果：通过。
- 运行导入 smoke：`knowledgeforge.server.create_app`、`knowledgeforge.agent.QueryEngine`、`knowledgeforge.agent.MediaEngine`、`knowledgeforge.agent.InsightEngine`
- 结果：通过，Flask template/static 目录指向 `knowledgeforge/web`。
- 运行 `PYTHONPATH=. pytest tests/test_dashboard.py tests/test_workflow.py -q`
- 结果：`31 passed`
- 运行 `PYTHONPATH=. pytest tests/test_dashboard.py tests/test_workflow.py tests/test_ml_regression.py tests/test_query_engine.py tests/test_media_engine.py tests/test_integration_layers.py -q`
- 结果：`58 passed`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`137 passed, 2 failed`。失败项为 `tests/test_supplement_decision.py::test_workflow_uses_index_decision_to_dispatch_query_supplement`（当前串行文件队列流程不再触发旧测试期望的第二轮三路 Engine run）与 `tests/test_workflow.py::test_async_task_falls_back_when_llm_generation_fails`（全量顺序下轮询撞到中间态 `filled`；该用例单独复跑通过）。

## Follow-up

- 后续需要将补检索决策相关旧测试同步到当前 `generate_files -> run_query_queue -> validate_round -> fill_evidence` 串行文件队列流程。
- 可考虑把异步接口返回给前端的 `filled` 中间态继续归一为 `running`，减少测试和 UI 轮询对瞬时内部状态的敏感度。

## 2026-04-28 LLM 连通性测试脚本

- 新增 `scripts/test_llm_available.py`，用于读取 `.env` 中的 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` 并向 OpenAI-compatible `/chat/completions` 发送最小 smoke 请求。
- 脚本支持 `--env-file`、`--prompt`、`--timeout` 参数，输出目标 base URL、模型、脱敏 API key、响应耗时、usage 与回复内容。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile scripts/test_llm_available.py`
- 结果：通过。
- 运行 `PYTHONPATH=. python scripts/test_llm_available.py --help`
- 结果：参数帮助可正常显示。
- 运行 `PYTHONPATH=. python scripts/test_llm_available.py`
- 结果：`[OK] received reply in 1.45s`，回复内容为 `LLM 连接正常。`

## 2026-04-28 LLM 调用机制优化

- 为串行文件骨架生成增加专用 `generation.chat_json` client，不再复用通用 planning client；生成链路默认 `0` 次重试，单次失败直接回退到本地固定骨架，避免一个文件在 LLM 超时时卡住多个完整超时窗口。
- 为 planning / execution / intake 增加独立的 `*_llm_max_retries` 配置项，并新增 `generation_llm_timeout`，让不同阶段可以分别调优。
- 调整 OpenAI-compatible chat client：`httpx.TimeoutException` 不再进入盲目重试，超时后立即失败并交由上层 fallback 或下一步流程处理。
- 修复 audit 回填重复问题：`llm_call_started` / `llm_call_completed` / `llm_call_failed` 不再从 `execution_log` 二次写入 audit，避免实时日志出现成对重复记录。
- 收敛 `fill_evidence` 的中间态：统一继续保持 `running`，减少前端轮询和异步测试误把内部中间态当成终态。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/config.py knowledgeforge/llms/openai_compatible.py knowledgeforge/orchestrator/graph.py knowledgeforge/services/task_service.py`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest tests/test_openai_compatible.py tests/test_workflow.py tests/test_token_usage.py -q`
- 结果：`38 passed in 13.42s`

## 2026-04-28 日志展示与应用日志增强

- 扩展 `/tasks/{task_id}/logs` 返回结构，新增 `queue_summary`、`log_summary`、`llm_activity`、`recent_errors`、`log_files`、`generation_progress`，让前端和接口调用方直接看到队列状态、最近一次 LLM 调用、失败摘要和日志文件路径。
- 为 `AuditLogger` 增加 `path_for(...)`，统一输出 audit JSONL 路径，便于接口返回和日志追踪。
- Flask 服务新增应用级请求日志文件 `logs/knowledgeforge-server.log`，对 `/tasks/...` 和 `/tasks/.../logs` 这类轮询接口额外记录 `task_status`、`current_step`、`current_action`、队列统计和最近一次 LLM 调用状态，不再只有终端里那种简陋的 `GET ... 200`。
- 前端日志面板升级为更易读的诊断视图：摘要区新增“队列状态 / 队列统计 / 最新 LLM / 最近错误 / 日志文件”，执行日志区会高亮文件、查询、轮次、尝试次数和错误信息，而不是只堆一行原始 JSON。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/config.py knowledgeforge/runtime/audit.py knowledgeforge/services/task_service.py knowledgeforge/server/api.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest tests/test_workflow.py tests/test_token_usage.py -q`
- 结果：`35 passed in 16.80s`

## 2026-04-28 生成阶段实时进度修正

- 生成阶段的 LLM 生命周期事件现在会自动携带 `current_file`、`completed_files`、`total_files`，所以 `current_action` 不再一直停在同一句 `generation.chat_json 第 1/1 次`，而是会带上当前文件和文件序号，例如 `"[2/116] index.md · LLM 调用开始..."`。
- 串行文件生成阶段补发了更明确的文件级事件元数据，生成开始和保存完成都带上当前文件、总文件数和已完成数量，方便前端和日志统一展示。
- 应用日志 `request_trace` 现在也附带 `generation_progress`，排查时能直接看到当前生成到哪个文件。
- 修复前端队列面板里队列统计函数重名的问题，避免“生成进度/队列统计”摘要被覆盖后看起来一直不动。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/services/task_service.py knowledgeforge/orchestrator/graph.py knowledgeforge/server/api.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest tests/test_token_usage.py tests/test_workflow.py -q`
- 结果：`36 passed in 20.58s`

## 2026-05-02 Neo4j 图谱清理

- 按用户要求清理 Neo4j 知识图谱数据，目标连接为 `.env` 中的 `NEO4J_URI=bolt://lpbkuaile6:7687`，用户为 `neo4j`。
- 清理前图谱包含 `60` 个节点、`55` 条关系；标签包括 `Article`、`Domain`、`Entity`、`KnowledgePoint`、`Source`、`SubTopic`；关系类型包括 `HAS_ARTICLE`、`HAS_SUBTOPIC`、`MENTIONS`。
- 使用分批 `MATCH (n) WITH n LIMIT 1000 DETACH DELETE n RETURN count(n)` 删除所有节点及其关系；未修改本地 Markdown 知识库文件。

## Verification

- 运行 Neo4j 只读验证查询 `MATCH (n) RETURN count(n)` 与 `MATCH ()-[r]->() RETURN count(r)`。
- 结果：清理后 `nodes=0`、`relationships=0`。

## 2026-05-02 Neo4j 实时知识图谱窗口

- 新增 `/tasks/{task_id}/graph` 接口，按当前任务 `request_context.domain` 读取 Neo4j 中的真实领域图谱快照，并返回统一的 `nodes/edges` JSON、刷新时间与节点/关系限制。
- 扩展 `Neo4jGraphClient`，支持读取 `Domain -> SubTopic -> Article -> Entity` 以及 `Domain -> KnowledgeStructureNode -> STRUCTURE_EDGE` 相关节点和关系；Neo4j 不可用时接口返回可渲染的 `status=unavailable`，不暴露连接凭据。
- 前端工作台新增“Neo4j 实时知识图谱”可折叠面板，包含连接状态、领域、节点/关系数量、自动跟随任务开关和手动刷新按钮；复用现有 X6 渲染并在 SSE 任务更新时节流刷新。
- 图谱渲染按节点类型分层布局，并对比上一帧快照高亮新增节点与关系。

## Verification

- 运行 `python -m py_compile knowledgeforge/graph/client.py knowledgeforge/services/task_service.py knowledgeforge/server/api.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `python -m pytest tests/test_dashboard.py tests/test_integration_layers.py -q`
- 结果：`7 passed in 0.60s`
- 运行 `python -m pytest tests/test_workflow.py tests/test_dashboard.py tests/test_integration_layers.py -q`
- 结果：`38 passed in 5.35s`
- 使用当前 `.env` Neo4j 连接执行只读 snapshot smoke。
- 结果：`neo4j_smoke=ok nodes=0 edges=0`；当前库无对应领域数据，Neo4j 对尚未出现的结构节点标签/关系给出 warning，但查询可正常解析并返回空图。

## 2026-05-02 Neo4j 结构图谱前置同步

- 按用户反馈调整图谱事实源：目录结构图谱生成后立即同步到 Neo4j，而不是等最终治理阶段才写入图谱。
- `KnowledgeStructureNode` 现在带有生成进度属性：`is_generated`、`generation_state`、`generated_path`、`generated_at`、`task_id`、`domain`。
- 文件骨架每成功落盘一个，就按蓝图里的 `completion_requirements.structure_node_id` 更新对应 Neo4j 结构节点的落实 flag；如果结构图谱初始同步失败，文件生成不会被打断，只会跳过节点 flag 更新。
- 图谱 API 对 Neo4j temporal 等非 JSON 原生属性做序列化保护，避免 `datetime()` 属性导致 Flask `jsonify` 500。
- 前端图谱指标新增“已落实”数量，节点标题区显示 `TODO/DONE` 状态。
- 对修复前已经启动的 `deep learning` 任务做了一次 Neo4j 回填：同步 23 个结构节点，并根据当前生成进度标记 4 个已生成节点。

## Verification

- 运行 `python -m py_compile knowledgeforge/graph/client.py knowledgeforge/graph/neo4j_adapter.py knowledgeforge/postprocess/pipeline.py knowledgeforge/orchestrator/graph.py knowledgeforge/services/task_service.py knowledgeforge/server/api.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `python -m pytest tests/test_integration_layers.py tests/test_dashboard.py -q`
- 结果：`8 passed in 0.59s`
- 运行 `python -m pytest tests/test_workflow.py tests/test_dashboard.py tests/test_integration_layers.py -q`
- 结果：`39 passed in 8.60s`
- 当前任务 `2146b1ba719d4990a3567fff46794af0` 的 `/graph` 接口已返回 `deep learning` 图谱节点与结构关系。

## 2026-05-02 Neo4j 图谱排版优化

- 将 Neo4j 图谱前端布局从“按类型堆叠”调整为优先按知识结构层级排布：Domain、根结构节点、section/index、article/subtopic 等按列展开。
- 图谱存在 `STRUCTURE_EDGE` 时，隐藏大部分 `HAS_STRUCTURE_NODE` 管理边，只保留结构树连线，避免边和标签遮挡节点。
- 去掉边标签文本，节点状态文案从 `NEW · KnowledgeStructureNode` 收敛为 `TODO/DONE · node_type`，并用生成状态调整节点配色。

## Verification

- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `python -m pytest tests/test_dashboard.py tests/test_integration_layers.py -q`
- 结果：`8 passed in 0.61s`

## 2026-05-03 真实流程对齐：意图识别、即时回写与 SSE 图谱

- 将 `/tasks` 与 `/tasks/async` 统一接入 intake 归一化链路，直接任务也会先识别真实意图与领域缩写；`DL` 现在会规范为 `Deep Learning`，概念解释类输入会被拒绝直接启动采集任务。
- 扩展结构图谱状态模型，结构节点支持 `planned/generating/generated/evidence_pending/evidence_running/completed/failed`，并在本地任务状态和 Neo4j 中同步 `pending_task_count`、`completed_task_count`、`is_completed`、`generated_path` 等属性。
- 文件生成阶段会在开始/完成时更新图谱节点状态；证据队列每个任务完成后立即回写目标 Markdown contract、更新 `knowledge_task_queue.json`、同步图谱节点，并根据子节点状态聚合父级 SubTopic / Domain 完成度。
- SSE 任务流 payload 现在携带 `graph_snapshot`、`graph_event`、`file_update`，前端优先用 SSE 图谱快照渲染，不再在每次任务消息后自动请求 `/graph`；`/graph` 保留为手动刷新和 Neo4j 不可用时的本地快照 fallback。
- 前端流程图调整为“意图识别 → 图谱规划 → 文件生成 → 证据查询 → 即时回写 → 父级聚合 → 治理质检 → 版本研报”，摘要区新增当前文件、证据任务、图谱完成度、父级状态和最近回写路径。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/graph/client.py knowledgeforge/graph/neo4j_adapter.py knowledgeforge/postprocess/pipeline.py knowledgeforge/orchestrator/graph.py knowledgeforge/services/task_service.py knowledgeforge/intake/clarifier.py knowledgeforge/intake/context_builder.py knowledgeforge/utils/query_normalization.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_knowledge_blueprint.py tests/test_dashboard.py tests/test_writer_dynamic_status.py`
- 结果：`49 passed in 9.80s`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`152 passed in 27.98s`

## 2026-05-03 实时流程图 HTML 展示优化

- 将前端“实时流程图”主展示从 X6 SVG 改为原生 HTML/CSS 流程卡片轨道，避免 SVG 箭头重叠、尺寸裁切和已完成状态颜色不同步的问题。
- 流程步骤现在统一通过 `data-status` 与 `data-status-label` 渲染 `待处理/执行中/已完成/需处理`，并兼容旧的 workflow step id（如 `blueprint_ready`、`evidence_filling`、`collecting` 等）映射到目标流程步骤。
- 当前执行步骤增加绿色强调、状态胶囊、底部进度线和呼吸光圈动画；已完成步骤自动根据当前步骤位置向前推断，不再依赖每个步骤都显式写入 completed 事件。
- 流程卡片改为自适应换行布局，8 个目标步骤在当前工作台宽度内完整展示，不再横向裁掉最后的步骤；Neo4j 图谱仍保留 X6 渲染。
- 同步更新 Dashboard 测试断言，确认页面使用新的 `flow-track` 展示容器。

## Verification

- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py tests/test_workflow.py`
- 结果：`40 passed in 7.38s`
- 使用 in-app browser 刷新 `http://localhost:5001/` 验证：`#workflow-map` 存在、`#workflow-x6` 不存在、8 个流程步骤完整渲染，当前步骤显示 `执行中`。
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`154 passed in 32.80s`
