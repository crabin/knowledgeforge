# Progress

## 2026-05-05 Neo4j 压缩边显示开关

- 在 Neovis 图谱头部新增“显示全部边 / 收起压缩边”按钮，默认保持当前的骨架视图。
- 打开开关后，会把目前被压缩隐藏的原始关系边补出来，并使用虚线样式显示，方便对照图中主骨架与完整关系。
- 再次点击按钮会回到默认压缩视图；节点选中、聚焦和右侧详情行为保持不变。
- 验证：`node --check knowledgeforge/web/static/js/dashboard.js` 通过；`uv run pytest -q tests/test_dashboard.py tests/test_graph_client.py` 结果 `11 passed`。

## 2026-05-05 Neo4j 相邻关系按方向分组

- 右侧“相邻关系”从单列表改成“来自”和“指向”两个分组，阅读路径更清楚，尤其适合结构节点连接较多的场景。
- 分组后的关系项继续保留点击聚焦能力，交互逻辑不变。
- 验证：`node --check knowledgeforge/web/static/js/dashboard.js` 通过；`uv run pytest -q tests/test_dashboard.py tests/test_graph_client.py` 结果 `11 passed`。

## 2026-05-05 Neo4j 相邻关系点击聚焦

- 右侧“相邻关系”列表现在支持点击聚焦对应节点：点击“来自/指向”关系项会复用现有 `focusNeo4jNode(...)` 逻辑，自动选中并将左侧图谱居中到对应节点。
- 同步补充可点击态样式，让关系项在 hover 时有更明确的交互反馈。
- 验证：`node --check knowledgeforge/web/static/js/dashboard.js` 通过；`uv run pytest -q tests/test_dashboard.py tests/test_graph_client.py` 结果 `11 passed`。

## 2026-05-05 Neo4j 问题列表与红点同步

- 修复问题列表残留：右侧“问题知识点”现在会按当前 Neo4j 图谱快照的 `graph.nodes` 过滤，只展示左侧图中真实存在、也能被标红的问题节点。
- 红色高亮集合和右侧列表使用同一套过滤后的 `graph_id` 集合，避免左侧没有红点但右侧仍显示旧问题项。
- 验证：`node --check knowledgeforge/web/static/js/dashboard.js` 通过；`uv run pytest -q tests/test_dashboard.py tests/test_graph_client.py` 结果 `11 passed`。

## 2026-05-05 Neo4j 问题节点去重

- 修复问题知识点检查结果按“匹配结构关系”重复返回的情况：同一个噪声节点命中多个结构节点时，后端现在按 `graph_id` 聚合，只在结果里保留一条问题节点记录。
- 聚合后会合并 `relationship_types`，并保留 `matching_candidates` 供后续扩展使用；当前列表数量会与图谱中的实际红色问题节点数量保持一致。
- 验证：`python -m py_compile knowledgeforge/graph/client.py` 通过；`uv run pytest -q tests/test_graph_client.py tests/test_dashboard.py` 结果 `11 passed`。

## 2026-05-05 Neo4j 问题节点高亮与聚焦

- 去掉 Neo4j 图谱外层容器的整体滚动，保留图谱固定展示和右侧详情栏独立滚动，避免再次出现整块图谱一起滑动。
- “检查知识点” 返回的问题节点现在会在 Neovis 图谱中使用红色节点渲染，即使节点不是结构节点，也会被优先纳入当前可见集合。
- 右侧“问题知识点”卡片支持点击聚焦：点击卡片会选中对应图谱节点，并把左侧图谱平滑居中到该节点；操作按钮区域仍保持原来的删除 / 连接行为。
- 验证：`node --check knowledgeforge/web/static/js/dashboard.js` 通过；`uv run pytest -q tests/test_dashboard.py` 结果 `10 passed`。

## 2026-05-05 Neo4j 图谱详情栏独立滚动

- 优化 Neo4j 实时知识图谱展示：桌面布局中图谱区域保持稳定高度，左侧 Neovis 画布填满容器且不随右侧详情内容滚动。
- 右侧节点详情 / 检查结果栏改为独立纵向滚动，避免问题列表过长时拖动整个图谱面板。
- 窄屏单列布局保留自然高度，并给详情栏设置独立最大高度，避免移动端内容挤压图谱。
- 验证：`node --check knowledgeforge/web/static/js/dashboard.js` 通过；`PYTHONPATH=. pytest -q tests/test_dashboard.py` 结果 `10 passed`。

## 2026-05-05 图谱叶子节点增量扩展接口

- 开始实现点击 Neo4j 图谱叶子节点后继续扩展知识点的后端接口。
- 已确认核心约束：读取被点击节点的一跳关联上下文，拼接给 LLM；结果合并到任务 `structure_graph`，同步 Neo4j，并返回可供前端立即刷新的图谱快照。
- 新增 `POST /tasks/{task_id}/graph/nodes/expand`：普通调用只允许扩展叶子节点；前端按钮使用 `force=true` 可在已有子分支时继续追加。
- 后端扩展流程会优先读取 Neo4j 关联上下文，失败时回退本地 `structure_graph`；LLM 未返回可用结构时生成 3 个基础子知识点作为 fallback。
- 前端 Neo4j 右侧节点详情新增“扩展知识点”按钮，成功后立即用返回的 `graph_snapshot` 刷新图谱，并触发一次 Neo4j fallback 刷新。
- 验证：`uv run ruff check knowledgeforge/services/task_service.py knowledgeforge/server/api.py tests/test_dashboard.py` 通过；`node --check knowledgeforge/web/static/js/dashboard.js` 通过；`python -m py_compile knowledgeforge/services/task_service.py knowledgeforge/server/api.py` 通过；`PYTHONPATH=. pytest -q tests/test_dashboard.py` 结果 `9 passed`；`PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py` 结果 `53 passed`。
- 本地开发服务已启动在 `http://127.0.0.1:5002`；`5001` 当时已被占用。

## 2026-05-05 治理质检卡在需处理排查

- 排查用户在 `http://localhost:5001/` 标记的 Deep Learning 任务，后端任务实际已终止为 `research_required`，不是仍在运行。
- 根因：LLM 生成的结构节点显式写入 `required_query_tasks=0`，现有规范化逻辑尊重该值，导致图谱补全阶段每个节点 `enqueued_tasks=0`、证据队列总数为 0；治理摘要没有任何可引用来源，因此质量检查失败并进入 `research_flow`。
- 修复：`subtopic` / `article` 节点即使 LLM 显式给 `required_query_tasks=0`，也默认保留 1 个证据查询任务；只有显式 `requires_query=false` 时才允许跳过。
- 用当前 Deep Learning 任务的真实 `structure_graph` 复核：修复后 23 个蓝图中有 17 个会派生证据查询任务。

## 2026-05-05 扩展知识点实验脚本

- 新增 `scripts/experiment_expand_graph_node.py`，用于从 `/tasks` 找最新任务、查询 Neo4j 中该任务领域下的 article/subtopic 叶子节点，并调用 `/tasks/{task_id}/graph/nodes/expand` 做端到端测试。
- 脚本支持 `--base-url`、`--task-id`、`--node-id`、`--force` 和 `--dry-run`；默认会实际调用扩展 API，`--dry-run` 只打印候选节点。
- 验证：`python -m py_compile scripts/experiment_expand_graph_node.py`、`PYTHONPATH=. python scripts/experiment_expand_graph_node.py --help`、`uv run ruff check scripts/experiment_expand_graph_node.py` 均通过。
- 对当前 `http://localhost:5001` 干跑选中 Deep Learning 任务的 `article_definition_scope`；实际调用扩展 API 成功，新增 5 个子知识点，返回图谱快照 `28` 个节点、`57` 条边，Neo4j 同步状态为 `passed`。

## 2026-05-05 Neo4j 重名独立节点检查与修复

- 新增图谱问题检查能力：`GET /tasks/{task_id}/graph/issues` 会列出和正式 `KnowledgeStructureNode` 重名、但自身不是结构节点的 `Entity/SubTopic/Article` 候选噪声节点。
- 新增两个操作接口：`POST /tasks/{task_id}/graph/issues/delete` 清除多余节点；`POST /tasks/{task_id}/graph/issues/link` 把候选节点用 `RELATED_TO` 连到匹配的结构节点。
- 前端 Neo4j 图谱增加“检查知识点”按钮，右侧详情栏会展示问题知识点列表，并提供“清除多余节点”和“连接到结构节点”操作。
- 在当前 `localhost:5001` 的 Deep Learning 任务上验证检查接口，成功列出 4 个候选问题节点，包括截图中的“数学与工程前置”重名节点。

## 2026-05-03 流程详情浮窗可读性增强

- 根据浏览器反馈降低详情浮窗的透底感：改为更实的不透明背景、更清晰边框、更重阴影和更高对比文字颜色。
- 验证：`uv run ruff check tests/test_dashboard.py`、`PYTHONPATH=. pytest -q tests/test_dashboard.py` 均通过，相关测试结果 `7 passed`。

## 2026-05-03 流程步骤详情浮窗层级修复

- 修复流程步骤详情 popover 被后续步骤卡片遮挡的问题：为普通卡片设置基础层级，hover / focus / focus-within 时抬高当前卡片层级，并提高详情浮窗 z-index。
- 验证：`uv run ruff check tests/test_dashboard.py`、`PYTHONPATH=. pytest -q tests/test_dashboard.py` 均通过，相关测试结果 `7 passed`。

## 2026-05-03 治理质检步骤悬浮说明

- 为前端流程图 07 “治理质检”卡片增加 hover / focus 详情层，说明触发条件与执行步骤。
- 详情内容覆盖证据队列完成 / 达到治理资格、结构化抽取、Neo4j 路径关联、质量检测、repair_flow / research_flow 分类和版本资格记录。
- 扩展为全部 10 个流程步骤都支持 hover / focus 查看详情；详情框采用浮动 popover，不占用流程图卡片布局空间。
- 验证：`node --check knowledgeforge/web/static/js/dashboard.js`、`uv run ruff check tests/test_dashboard.py`、`PYTHONPATH=. pytest -q tests/test_dashboard.py` 均通过，相关测试结果 `7 passed`。

## 2026-05-03 恢复任务清理初始化取消标记

- 修复用户点击恢复旧 `repair_required` 检查点时报 `_TaskCancelled: task ... was stopped by system initialization` 的问题。
- `resume_task(...)` 现在会在确认任务不是运行中后清理该 task id 的初始化取消标记，再进入结构修复接续或普通恢复流程；系统初始化仍会停止当时正在运行的任务。
- 补充回归覆盖：旧结构修复检查点即使残留在 `_cancelled_task_ids` 中，显式恢复也能继续执行。
- 验证：`uv run ruff check knowledgeforge/services/task_service.py tests/test_workflow.py tests/test_dashboard.py`、`python -m py_compile knowledgeforge/services/task_service.py`、`PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py` 均通过，相关测试结果 `51 passed`。

## 2026-05-03 第二轮结构修补后自动继续主链路

- 根据浏览器批注调整架构 review 后的修复流：第二轮 review 仍发现缺口时，不再停到 `repair_required / 可恢复`，而是执行第二轮自动修补、同步 Neo4j，并直接进入图谱补全和后续证据 / 治理链路。
- 第二轮结构修补后将 `structure_review_status` 标记为 `auto_repaired`，本地图谱节点状态置为 `approved`，并在 `current_action` 中明确“已自动修补并同步 Neo4j”。
- 前端耗时状态中 `repair_required` 文案从“待修复，可恢复”改为“待系统修复”，避免暗示需要人工处理。
- 旧任务的 `/tasks/{task_id}/resume` 兼容入口仍保留，但新任务不再需要用户点击恢复才能继续。
- 验证：`uv run ruff check knowledgeforge/orchestrator/graph.py knowledgeforge/services/task_service.py tests/test_workflow.py tests/test_dashboard.py`、`python -m py_compile knowledgeforge/orchestrator/graph.py knowledgeforge/services/task_service.py`、`node --check knowledgeforge/web/static/js/dashboard.js`、`PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py` 均通过，相关测试结果 `51 passed`。

## 2026-05-03 图谱证据写入改为 Neo4j 必需步骤

- 根据浏览器批注修正 08「图谱证据写入」定位：它属于默认 Neo4j 主链路必需能力，不再标记为可选。
- Workflow 新增自动 `record_evidence_to_graph` 节点：治理质检后写入 `selected_link/source_kind/reachable/relevance_reason/checked_at/claim_or_gap/expected_evidence` 等字段，并记录 `document_evidence_sync` 与 `evidence_link_recorded` 事件。
- 前端 Flow Map 与 `FLOW_STEPS` 文案同步为必需步骤；09「补全文档」和 10「版本研报」仍保持可选。
- 同步更新 `docs/项目需求.md`、`docs/流程执行文档.md`、`task_plan.md` 和 `findings.md`。
- 验证：`python -m py_compile knowledgeforge/orchestrator/graph.py knowledgeforge/services/task_service.py`、`node --check knowledgeforge/web/static/js/dashboard.js`、`uv run ruff check knowledgeforge/orchestrator/graph.py tests/test_workflow.py tests/test_dashboard.py`、`PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py` 均通过，相关测试结果 `51 passed`。
- 记录：曾误把 JavaScript 文件传给 `ruff`，该命令按 Python 解析 JS 后失败；已改用 `node --check` 验证 JS、`ruff` 只检查 Python 文件。

## 2026-05-03 图谱证据写入改为补全文档前置可选步骤

- 根据浏览器批注调整流程：默认主链路保留 `evidence_link_query` 可信链接查询，但不再触发 `evidence_link_recorded`，也不再把 `selected_link/source_kind/reachable/relevance_reason/checked_at/claim_or_gap` 等证据字段写入 Neo4j。
- `/tasks/{task_id}/documents/complete` 现在会先执行图谱证据同步，记录 `document_evidence_sync`，追加 `evidence_link_recorded` workflow event，再生成本地 Markdown。
- 历史记录：当时前端流程顺序曾更新为“证据链接 → 治理质检 → 可选图谱证据写入 → 补全文档”；后续已按最新批注改为必需 Neo4j 步骤。
- 历史记录：当时曾把图谱证据写入口径统一为补全文档前的可选动作；后续已按最新批注改为默认主链路必需动作。
- 验证：`uv run ruff check knowledgeforge/services/task_service.py knowledgeforge/orchestrator/graph.py tests/test_workflow.py tests/test_dashboard.py`、`python -m py_compile knowledgeforge/services/task_service.py knowledgeforge/orchestrator/graph.py`、`node --check knowledgeforge/web/static/js/dashboard.js`、`PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py` 均通过，相关测试结果 `51 passed`。

## 2026-05-03 Neo4j 图谱优先与补全文档后置文档同步

- 按用户确认的新方向同步 `docs/项目需求.md`、`docs/流程执行文档.md`、`docs/知识文档格式规范.md`、`task_plan.md` 和 `findings.md`。
- 文档口径调整为：默认主链路只完善 Neo4j 知识图谱、review 结果、证据链接、建议路径和治理状态；本地知识 Markdown 只在用户点击 `/tasks/{task_id}/documents/complete` 后生成。
- 明确未点击补全文档时，不要求 `save/{领域}/README.md` 或知识点 Markdown 存在；运行态状态、日志、缓存和队列文件不属于知识文档落盘。
- 明确 Neo4j 节点需保存补全文档所需字段，包括 `evidence_links`、`selected_link`、`source_kind`、`reachable`、`relevance_reason`、`checked_at`、`claim_or_gap`、`expected_evidence`、`review_status`、`repair_log`、`suggested_relative_path` 和 `document_completion_status`。
- 未直接编辑 `docs/流程图.excalidraw`，遵守本次计划的文档范围。

## 2026-05-03 Neo4j 图谱优先主链路代码改造

- 将默认 workflow 从本地架构 Markdown 生成改为图谱补全文档上下文：review 通过后写入 Neo4j 节点状态、建议路径、证据需求和 `document_completion_status=not_requested`，不生成 `save/{领域}/README.md` 或知识点 Markdown。
- 证据阶段继续使用 QueryEngine 查询可信链接，但实时文件保存会在默认主链路中跳过；证据结果先写入运行态队列、SSE payload 和本地图谱快照，Neo4j 证据字段改由补全文档动作前置写入。
- 治理阶段改用 `.knowledgeforge/tasks/graph_governance/` 下的运行态图谱治理摘要，避免把治理摘要当作本地知识库 Markdown 落到 `save/`。
- `/tasks/{task_id}/documents/complete` 现在负责唯一的知识 Markdown 落盘入口：前置检查通过后创建缺失的文档骨架、消费队列证据补全文档，并把 `generated_path` / `document_completion_status=generated` 同步回图谱。
- 历史记录：前端流程和图谱状态文案曾同步为“图谱补全 / 证据链接 / 治理质检 / 可选图谱证据写入 / 补全文档”，并新增 `completion_ready`、`document_generating` 状态展示；后续 08 已改为必需 Neo4j 步骤。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_knowledge_blueprint.py tests/test_integration_layers.py tests/test_dashboard.py`，结果：`60 passed`。
- 运行 `PYTHONPATH=. pytest -q tests/test_quality_source_checks.py tests/test_ml_regression.py tests/test_writer_dynamic_status.py`，修复质量门禁后相关用例通过。
- 运行 `PYTHONPATH=. pytest -q`，结果：`165 passed, 1 failed`；唯一失败为 live browser 外网用例 `tests/test_agent_browser_live.py::test_agent_browser_can_fetch_page_text` 访问 LangGraph 站点超时，非本地代码回归。

## 2026-05-03 Neovis.js 图谱展示接入

- 按官方 Neovis.js 安装文档为项目安装 `neovis.js`，新增 `package.json` 与 `package-lock.json`，并将 `node_modules/` 加入 `.gitignore`。
- 前端模板加载 `https://unpkg.com/neovis.js@2.1.0/dist/neovis.js`，与项目内安装版本保持一致；官方文档示例的 `2.0.2` 在当前用法下会尝试默认直连 Neo4j，因此未继续使用。
- 将 Neo4j 图谱主画布切换为 Neovis.js / vis-network 力导向图展示，节点呈圆点网络形态，保留顶部统计和右侧选中节点详情。
- 为了避免在浏览器暴露 Neo4j 密码，前端不直连 Neo4j；仍使用后端 `/tasks/{task_id}/graph` 的安全快照数据，并转换为 Neovis.js 数据集渲染。
- 图谱面板排版调整为左侧 Neovis.js 画布、右侧详情栏，画布高度使用 `min(58vh, 620px)` 并保留响应式单列布局。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py`
- 结果：`7 passed in 0.69s`
- 使用 in-app browser 刷新当前 Machine Learning 任务图谱，确认 Neovis.js canvas 已渲染，节点与关系可见。
- 运行 `npm audit --audit-level=moderate`
- 结果：失败，`neovis.js -> vis-network -> vis-data -> uuid` 链路存在 4 个 moderate 漏洞；`npm audit fix --force` 会把 `neovis.js` 降到 `1.6.0`，属于破坏性变更，本轮未执行。

## 2026-05-03 Neo4j 图谱可读性优化

- 根据浏览器 diff comment 继续修复关系可读性：主图不再直接绘制所有 Neo4j `STRUCTURE_EDGE` / 管理边，而是根据结构节点 `parent_node_id` 生成唯一父子边，避免跨层线和重复标签堆成蓝线团。
- 边标签默认隐藏，只在选中节点的直接相邻边上显示；选中节点、父节点和子节点保持高亮，其他节点降噪，右侧详情继续列出直接相邻关系。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py`
- 结果：`7 passed in 0.67s`
- 使用 in-app browser 重新刷新现有 Deep Learning 任务图谱，确认主图只显示清晰父子连接线，右侧仍能查看节点直接关系。

## 2026-05-03 Neo4j 图谱可读性优化（首版）

- 将前端 Neo4j 图谱主体从紧凑节点列表升级为分层连线知识图谱：节点按 Domain / 结构节点层级自上而下排布，边以曲线箭头连接，并显示短关系标签。
- 节点改为可点击的大文本卡片，保留状态、类型、标题和路径；右侧新增选中节点详情，展示路径、任务计数、Task ID 和相邻关系。
- 优化图谱在窄视口下的布局：详情面板上移，图谱宽度不再固定 920px，避免首屏只看到大面积空白。
- 修复页面初始 `lastPayload=null` 时手动刷新 Neo4j 图谱会触发 `task_id` 空值读取错误的问题。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py`
- 结果：`7 passed in 0.68s`
- 使用 in-app browser 打开 `http://127.0.0.1:5001/`，用现有任务 `5ff363b2fa9f4814811ffe5aa0d9bcf2` 手动刷新图谱，确认 Deep Learning 图谱、详情面板和节点关系可见。

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

## 2026-05-03 Neo4j 图谱 HTML 紧凑展示

- 将前端 Neo4j 实时知识图谱主体从 X6 大画布改为 HTML 快照展示，保留连接状态、领域指标、自动跟随和手动刷新控制。
- HTML 图谱包含状态统计条、重点节点卡片和关系摘要；节点按运行中、待证据、失败、完成、规划等优先级排序，新增节点和新增关系保留轻量高亮。
- 空状态从大画布压缩为 168px 高提示；有数据时容器最大高度限制为 360px，内部滚动展示，避免占用大量页面空间。
- 初始化页面时会立即渲染紧凑空状态，不再留下空白图谱容器。

## Verification

- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py tests/test_workflow.py`
- 结果：`40 passed in 9.02s`
- 使用 in-app browser 刷新 `http://localhost:5001/` 验证：`#neo4j-graph` 下无 `svg.x6-graph-svg`，紧凑空状态正常显示。
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`154 passed in 37.89s`

## 2026-05-03 知识框架优先流程改造

- 将 `RequestContext.completion_mode` 默认值从旧的 `file_level` 调整为 `framework`，并将旧输入 `file_level` 规范化为 `full_document`。
- 默认主链路现在先生成知识框架图谱与框架证据 Markdown：文件包含知识定位、学习角色与路径、知识关系、证据与来源、后续动作和 contract，不再默认生成完整正文。
- `full_document` 模式保留完整知识库文档能力，但执行顺序改为“框架图谱与证据完成后，最后补全 mixed 完整文档”。
- 治理链路根据模式切换质量检查：`framework` 检查图谱、蓝图、框架证据文件、官方/权威证据和路径关联；`full_document` 继续检查完整文档。
- API / intake / 前端支持传入 `completion_mode`，前端摘要区展示产出模式与完整文档状态。
- 同步更新 `docs/项目需求.md`、`docs/流程执行文档.md`、`docs/知识文档格式规范.md`，明确“知识框架图谱 + 证据”为必须产物，完整文档为后置可选产物。

## Verification

- 运行 `PYTHONPATH=. pytest -q tests/test_knowledge_blueprint.py tests/test_workflow.py`
- 结果：`41 passed in 7.52s`
- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/models.py knowledgeforge/intake/context_builder.py knowledgeforge/prompts/knowledge_file_generation.py knowledgeforge/orchestrator/graph.py knowledgeforge/storage/markdown_writer.py knowledgeforge/quality/checker.py knowledgeforge/evaluation/completeness.py knowledgeforge/services/task_service.py knowledgeforge/runtime/state_store.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_knowledge_blueprint.py tests/test_workflow.py tests/test_dashboard.py`
- 结果：`48 passed in 7.54s`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`157 passed in 33.57s`

## 2026-05-03 知识架构 Review 与链接证据主链路重排

- 将 LangGraph 主链路重排为：`generate_structure_graph -> sync_structure_graph_to_neo4j -> review_structure_round_1 -> repair_structure_graph_round_1 -> review_structure_round_2 -> generate_architecture_documents -> query_evidence_links -> validate_round -> fill_evidence -> run_post_storage`。
- 新增 `structure_review_rounds`、`structure_review_status`、`structure_repair_log`；当时第二轮仍不完整会进入 `repair_required`，该行为后续已调整为自动修补并继续主链路。
- 证据阶段收敛为 QueryEngine 链接查询：队列记录 `selected_link`、`source_kind`、`reachable`、`relevance_reason`、`checked_at`，不再即时把网页内容或摘要写回 Markdown。
- Neo4j 结构节点状态改为架构语义：`reviewing`、`repairing`、`documenting`、`documented`、`link_querying`、`link_verified`、`link_failed`；`update_structure_node_status` 不再做祖先或 Domain 父级聚合。
- 前端流程图更新为“意图识别 → 图谱生成 → Neo4j呈现 → 架构Review → 架构文档 → 证据链接 → 治理质检 → 补全文档/版本研报”。
- 同步更新项目需求、流程执行文档、知识文档格式规范、计划与发现记录。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/orchestrator/graph.py knowledgeforge/models.py knowledgeforge/orchestrator/state.py knowledgeforge/prompts/knowledge_file_generation.py knowledgeforge/graph/client.py knowledgeforge/graph/neo4j_adapter.py knowledgeforge/services/task_service.py knowledgeforge/agent/QueryEngine/agent.py knowledgeforge/runtime/domain_task_queue_store.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_knowledge_blueprint.py tests/test_dashboard.py`
- 结果：`52 passed in 8.17s`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`161 passed in 52.33s`
- 误把 `knowledgeforge/web/static/js/dashboard.js` 传给 `python -m py_compile`，Python 按 `.py` 解析 JS 并报 `SyntaxError: invalid character '·'`；随后改用 Python 文件列表 + `node --check` 分别验证。
- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/orchestrator/graph.py knowledgeforge/models.py knowledgeforge/orchestrator/state.py knowledgeforge/prompts/knowledge_file_generation.py knowledgeforge/graph/client.py knowledgeforge/graph/neo4j_adapter.py knowledgeforge/services/task_service.py knowledgeforge/agent/QueryEngine/agent.py knowledgeforge/runtime/domain_task_queue_store.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`161 passed in 30.25s`

## 2026-05-03 按当前代码流程同步文档与 Excalidraw

- 同步 `docs/项目需求.md`、`docs/流程执行文档.md`、`docs/知识文档格式规范.md` 到当前代码真实流程，明确：
  - 主链路是 `generate_structure_graph -> sync_structure_graph_to_neo4j -> 两轮架构 review / 自动修补 -> generate_architecture_documents -> query_evidence_links -> validate_round -> fill_evidence -> run_post_storage`。
  - `completion_mode=full_document` 仍会在主链路 `fill_evidence` 阶段直接生成 mixed 完整文档。
  - `/tasks/{task_id}/documents/complete` 是 framework 任务完成后的后置逐文件补全文档动作。
- 重写 `docs/流程图.excalidraw` 为当前主链路的精简流程图，突出 Neo4j 前置呈现、两轮 review、link-only evidence queue、`full_document` mixed 文档分支和 framework 后置补全文档分支。

## Verification

- 运行 `node -e "JSON.parse(require('fs').readFileSync('docs/流程图.excalidraw','utf8')); console.log('ok')"`
- 结果：`ok`

## 2026-05-03 修正文案中的人工干预表述

- 修正 `repair_required` 的 `current_action` 文案，不再声明“需要人工修复或重新生成图谱”。
- 当时表述改为系统后续修复流；后续已调整为第二轮自动修补并同步 Neo4j 后直接继续主链路。
- 为工作流测试补充断言，防止失败态文案再次回退到人工介入口径。

## 2026-05-03 架构 Review 去人工化与 Neo4j 上下文增强

- 使用 `planning-with-files` 恢复计划上下文并记录本轮任务。
- 阅读了 `docs/项目需求.md`、`docs/流程执行文档.md`、`docs/知识文档格式规范.md`、`knowledgeforge/orchestrator/graph.py`、`knowledgeforge/prompts/knowledge_file_generation.py`、Neo4j mapper/client 与相关 workflow 测试。
- 发现当前 review 输入未拼接 Neo4j 上下文；第一轮通过时两轮 review 之间不做 Neo4j 同步；Neo4j 结构图谱同步保留旧状态，无法反映 review 后状态；`manual_review` 建议可能被原样记录。
- 已新增 review 专用 Neo4j 上下文读取链路：`PostStoragePipeline -> Neo4jPathMapper -> Neo4jGraphClient.structure_review_context`。
- 已调整 `_run_structure_review` 的 LLM 输入，拼接当前 `knowledge_id`、Neo4j 相关图谱上下文、本地 `structure_graph`、上一轮 review 记录和自动补全约束。
- 已调整每轮 review：Neo4j 初始同步可用时查询当前知识 ID 上下文；review 结束后同步结构状态，Neo4j 不可用时使用本地图谱 fallback 并跳过重复连接。
- 已过滤非自动化 review 建议，并把文档/生成器中的人工处理表述收敛为系统复核、repair flow 或 research flow。
- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/orchestrator/graph.py knowledgeforge/prompts/knowledge_file_generation.py knowledgeforge/postprocess/pipeline.py knowledgeforge/graph/neo4j_adapter.py knowledgeforge/graph/client.py knowledgeforge/storage/markdown_writer.py`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py::test_structure_review_uses_neo4j_context_and_syncs_each_round tests/test_workflow.py::test_structure_review_repairs_first_round_before_documents tests/test_workflow.py::test_structure_review_failure_stops_before_documents`
- 结果：`3 passed in 4.05s`
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_knowledge_blueprint.py tests/test_dashboard.py`
- 结果：`53 passed in 23.14s`
- 运行 `PYTHONPATH=. pytest -q`
- 第一次结果：`1 failed, 161 passed`，失败用例为 `test_async_task_streams_query_progress_before_completion`；原因是 Neo4j 不可用时 review 前查询/同步重复触发连接重试，异步轮询窗口内仍处于 running。
- 修复：Neo4j 初始同步失败或跳过时，review 上下文改用本地 structure graph fallback；review 结束同步也记录 skipped，避免重复连接不可用 Neo4j。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py::test_structure_review_uses_neo4j_context_and_syncs_each_round tests/test_workflow.py::test_async_task_streams_query_progress_before_completion`
- 结果：`2 passed in 2.92s`
- 运行 `PYTHONPATH=. pytest -q`
- 最终结果：`162 passed in 30.12s`

## 2026-05-03 前端流程状态颜色优化

- 将 Flow Map 的 `blocked/需处理` 状态从红色调整为橙色，表达可恢复的自动修补、补检索或待处理状态。
- 新增 `error/错误` 流程状态，只有 workflow event 或当前任务状态为 failed/error/plan_failed 时才使用红色。
- 同步更新 HTML 图例、fallback 卡片样式和 X6 流程图节点/边颜色。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py`
- 结果：`7 passed in 0.71s`
- 修复处理中第 01 步颜色回退问题：将内部 `structure_repair` / `repair_structure_graph_round_*` 映射回第 04 步，并在当前步骤不属于主流程节点时使用最新 workflow event 兜底。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py`
- 结果：`7 passed in 0.68s`

## 2026-05-03 repair_required 恢复继续执行

- 修复旧任务停在 `repair_required` 后点击“恢复任务”也不能沿当前图谱继续的问题；新任务后续已调整为不再停靠该检查点。
- 新增 `KnowledgeGraphWorkflow.continue_after_structure_repair(...)`，用于复用已修补的 `structure_graph` / `knowledge_blueprint`，直接接续架构文档生成、证据链接查询、轮次验证、证据收尾与治理质检。
- 调整 `TaskService.resume_task(...)`：当任务是 `repair_required` 且停在 `structure_review`，并且已有图谱与蓝图时，走 repair flow 接续；其他终态仍保留原有轮次恢复 / 最大轮次保护逻辑。
- 增加回归测试 `test_resume_repair_required_continues_from_repaired_structure`，确认恢复后会生成文件与领域级 `knowledge_task_queue.json`，并记录 `resume_mode=continue_after_structure_repair` 事件。

## Verification

- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py::test_structure_review_failure_stops_before_documents tests/test_workflow.py::test_resume_repair_required_continues_from_repaired_structure tests/test_workflow.py::test_complete_documents_requires_finished_framework_then_expands_files`
- 结果：`3 passed in 1.93s`
- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/orchestrator/graph.py knowledgeforge/services/task_service.py`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py`
- 结果：`48 passed in 17.92s`

## 2026-05-03 repair_required 耗时状态展示

- 修复前端摘要区执行耗时后缀：不再把所有非运行任务都显示为“已完成”。
- 当时 `repair_required` 显示为“待修复，可恢复”；后续已调整为“待系统修复”，避免暗示人工处理。
- 补充 dashboard 静态回归断言，防止耗时展示回退到 `is_running ? 运行中 : 已完成` 的二分逻辑。

## Verification

- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_dashboard.py`
- 结果：`7 passed in 0.70s`

## 2026-05-03 架构 Review 轮次去重

- 修复恢复或重跑结构审查时 `structure_review_rounds` 追加历史轮次，导致前端显示 `3/2 · 需修补` 并可能反复超过两轮的问题。
- 后端 `_merge_structure_review_round(...)` 现在按 `round=1/2` 覆盖对应轮次，只保留最多两轮有效 review 记录。
- 前端 `summarizeStructureReview(...)` 增加同样的去重兜底，旧任务状态里即使已经存在重复 review 记录，也不会再显示超过 `2/2`。
- 补充 workflow 与 dashboard 回归断言，防止恢复任务后结构 Review 计数再次累加。

## Verification

- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py::test_structure_review_failure_stops_before_documents tests/test_workflow.py::test_resume_repair_required_continues_from_repaired_structure tests/test_workflow.py::test_structure_review_rounds_are_replaced_not_appended tests/test_dashboard.py`
- 结果：`10 passed in 1.06s`
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/orchestrator/graph.py`
- 结果：通过。

## 2026-05-03 防止恢复任务卡回架构 Review

- 修复 `/tasks/{task_id}/resume` 对运行中任务缺少保护的问题：运行中的任务再次点击恢复会直接返回当前状态并记录 `task_resume_skipped`，不再启动第二条 workflow。
- `repair_required` 的结构修补检查点现在同时接受 `current_step=structure_review` 和 `current_step=structure_repair`，避免旧任务停在修补步骤时恢复分支未命中，重新进入结构 review / repair。
- Flask app 将当前 `TaskService` 暴露到 `app.config["TASK_SERVICE"]`，方便测试验证服务内存状态与持久化状态。
- 补充回归测试覆盖：从 `structure_repair` 检查点恢复会继续进入文档生成；运行中任务重复恢复不会启动新 workflow。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/services/task_service.py knowledgeforge/server/api.py`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py::test_resume_repair_required_continues_from_repaired_structure tests/test_workflow.py::test_resume_repair_required_from_structure_repair_step_continues tests/test_workflow.py::test_resume_running_task_does_not_start_second_workflow tests/test_workflow.py::test_structure_review_rounds_are_replaced_not_appended tests/test_dashboard.py`
- 结果：`11 passed in 4.07s`
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py`
- 结果：`51 passed in 18.58s`
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。

## 2026-05-05 图谱生成与查询填充分步执行

- 调整默认任务工作流：完成结构图谱生成、Neo4j 同步、两轮架构 review 和图谱补全后，任务进入 `graph_ready`，不再自动联网查询证据。
- 新增 `POST /tasks/{task_id}/evidence/fill`，作为“查询填充”动作；触发后执行可信链接查询、轮次验证、治理质检和 Neo4j 图谱证据写入。
- 前端任务操作区新增“查询填充”按钮，流程图第 06 步改为用户触发的“查询填充”，避免把证据为 0 误表达为异常。
- 补全文档仍要求查询填充与治理通过后才能执行；研报仍要求冻结版本。
- 同步更新 `docs/项目需求.md`、`docs/流程执行文档.md`、`task_plan.md`、`findings.md` 与 workflow/dashboard 回归测试。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/orchestrator/graph.py knowledgeforge/services/task_service.py knowledgeforge/server/api.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py`
- 结果：`54 passed in 15.81s`
- 运行 `PYTHONPATH=. pytest -q`
- 初次结果：`170 passed, 1 failed`，失败用例仍按旧口径期望 workflow.run 直接完成证据查询。
- 修复后重跑 `PYTHONPATH=. pytest -q`
- 结果：`171 passed in 27.94s`

## 2026-05-05 查询填充实时同步修复

- 修复“查询填充”按钮点击后前端不立即更新的问题：`/tasks/{task_id}/evidence/fill` 改为异步启动，先保存 `task_status=running`、`current_step=evidence_link_query` 和活动 workflow event，再由后台线程继续执行联网证据填充。
- 前端点击“查询填充”后会立即 `showPayload(...)` 并启动 SSE 跟踪，summary、实时流程图和查询队列区域不再等查询全部结束才刷新。
- SSE 终止条件调整为“终态且已有 finished_at”，避免治理中途把状态暂时写成 `verified/research_required` 时过早断开，导致图谱证据写入阶段不再同步。
- 将队列面板的“LLM 生成进度 / 文件已生成”改为“图谱上下文进度 / 图谱上下文已准备”，避免误导为已经进入本地 Markdown 生成阶段。
- 浏览器插件验证尝试被 Browser Use 安全策略拦截，改用 Flask 测试客户端和前端静态断言验证实时同步契约。

## Verification

- 运行 `PYTHONPATH=. python -m py_compile knowledgeforge/services/task_service.py knowledgeforge/server/api.py`
- 结果：通过。
- 运行 `node --check knowledgeforge/web/static/js/dashboard.js`
- 结果：通过。
- 运行 `PYTHONPATH=. pytest -q tests/test_workflow.py tests/test_dashboard.py`
- 结果：`55 passed in 14.32s`
- 运行 `PYTHONPATH=. pytest -q`
- 结果：`172 passed in 29.23s`
