# Progress

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
