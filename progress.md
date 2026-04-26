# 进度日志

## 会话：2026-04-24

### 阶段 48：结果区页面展示修复与收拢
- **状态：** complete
- **开始时间：** 2026-04-26
- 执行的操作：
  - 修复结果区模板中的错误引号，恢复“执行计划 / 执行日志 / 任务列表”面板样式与 DOM 绑定
  - 将原始响应 JSON 收拢为默认折叠的 `details` 面板，避免大段 JSON 挤压主界面
  - 保留执行计划为全宽区域，下方维持日志与任务列表双栏布局
  - 补充 dashboard 回归断言，覆盖 `plan-full-panel`、`trace-grid` 和“原始响应 JSON”入口
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/templates/index.html
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_dashboard.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `node --check knowledgeforge/static/js/dashboard.js`：通过
  - `PYTHONPATH=. pytest tests/test_dashboard.py -q`：2 passed
  - in-app browser 本地检查：结果区已恢复卡片布局，新增“原始响应 JSON”折叠面板
  - `PYTHONPATH=. pytest -q`：当前工作树下存在 2 个非本次改动导致的失败
- 当前保守结论：
  - 页面展示问题已修复；全量测试失败来自当前工作树中与前端展示无关的计划生成改动，需要与本次 UI 调整分开处理。

### 阶段 47：前端流程步骤显示优化
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 在实时流程图与 HTML fallback 流程卡片中新增“实时沉淀”步骤，放在并行采集与完整性评估之间
  - 前端从 `query_realtime_file_reviewed` / `media_realtime_file_reviewed` / failed 事件合成 `realtime_saving` 流程状态
  - 计划卡片展示实时审查状态和已保存 Markdown 路径，MediaEngine 计划项也能从执行日志中更新命中与保存状态
  - 响应摘要新增“实时保存”统计，展示已保存文件数和跳过来源数
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/templates/index.html
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
- 验证结果：
  - `node --check knowledgeforge/static/js/dashboard.js`：通过
  - `curl -s http://127.0.0.1:5017/ | rg -n "实时沉淀|workflow-x6|dashboard.js|实时流程图"`：页面响应包含新增步骤和脚本
  - `PYTHONPATH=. pytest tests/test_dashboard.py tests/test_workflow.py -q`：26 passed
  - `PYTHONPATH=. pytest -q`：105 passed
- 当前保守结论：
  - 前端现在能把“实时文件审查保存”从后台日志提升为明确步骤和计划项状态，不再只依赖 JSON 原文排查。

### 阶段 46：Query / Media 计划项实时文件审查保存
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 新增 `RealtimeFileReviewer`，按计划项审查 QueryEngine / MediaEngine 获取的合格内容并实时保存 Markdown
  - 实时文档写入 `realtime_saved`、`plan_item_id`、`query`、agent、round、sources 和本地 path，默认状态为 `draft`
  - 每次保存或跳过后刷新领域 `README.md` 的“实时保存文档”索引区块
  - QueryEngine 在每个 `SearchQuestion` 完成后触发实时审查；MediaEngine 在每个 social / community / blog 查询项执行后触发实时审查
  - TaskService 注入共享审查器，并把实时审查事件写入 audit log 与运行中任务快照
  - 最终 Markdown writer 在重写领域 README 时保留实时保存文档索引
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/storage/realtime_reviewer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/storage/markdown_writer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_realtime_reviewer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_engine_plans.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `PYTHONPATH=. pytest tests/test_realtime_reviewer.py tests/test_engine_plans.py tests/test_writer_dynamic_status.py -q`：14 passed
  - `PYTHONPATH=. pytest tests/test_query_engine.py tests/test_media_engine.py tests/test_workflow.py tests/test_supplement_decision.py -q`：39 passed
  - `PYTHONPATH=. pytest -q`：105 passed
- 当前保守结论：
  - Query / Media 现在能在计划项级别实时沉淀合格资料；最终综合文档和治理链路保持原有职责，不会提前把实时草稿当成 verified 知识。

### 阶段 1：上下文恢复与需求收敛
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 检查项目根目录与现有文件
  - 运行 session-catchup 脚本恢复上下文
  - 读取 docs/项目需求.md
  - 读取 docs/知识文档格式规范.md
  - 读取 docs/流程执行文档.md
  - 读取 docs/design-paradigms/agent-architecture.md
  - 读取 planning-with-files 模板与 visual companion 指南
  - 初始化 task_plan.md、findings.md、progress.md
  - 用户确认本轮输出为“直接可实施规格”
  - 用户确认首个实施批次优先主链路闭环前半段
  - 用户确认第一批同步纳入 Neo4j 与质量检测前置骨架
  - 用户确认完整性评估归属、Neo4j 失败补偿与版本冻结规则本轮直接定案
  - 用户确认采用“主链路优先，后半段用可落地骨架接上”的推荐路径
  - 用户确认第 1 部分设计：整体架构与阶段划分
  - 用户确认第 2 部分设计：核心模块边界与数据流
  - 用户确认第 3 部分设计：回流、失败补偿、质量闭环与版本规则
  - 用户确认第 4 部分设计：测试策略、实施批次与验收标准
  - 已完成规格自查，并补充版本命名与可见性规则
  - 用户要求“使用技能生成计划”，已按可用技能 `bootstrap-project-paradigms` 的轻量规划约定完成计划整理
  - 已将 task_plan.md 从规格阶段计划切换为实施阶段计划
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md

### 阶段 2：实施计划切换
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 读取现有 task_plan.md 与 progress.md
  - 基于 docs/项目需求.md、docs/流程执行文档.md、docs/知识文档格式规范.md 重组实施阶段
  - 将任务拆分为 8 个实施阶段与 3 个首批批次
  - 明确首批闭环目标、推荐实现顺序、关键风险与完成定义
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md

### 阶段 3：批次 A 主链路实现
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 读取 `daily-coding` 技能并按最小改动原则执行
  - 建立 Flask 应用入口、`/health`、`/tasks`、`/tasks/<task_id>` 接口
  - 建立 `knowledgeforge/` 应用包、配置、schema、时间与路径工具
  - 建立 LangGraph 主流程图，接入并行采集、完整性评估和 Markdown 落盘节点
  - 建立 `agent/InsightEngine`、`agent/QueryEngine`、`agent/MediaEngine` 标准目录骨架与最小实现
  - 建立 Markdown Writer，生成领域 `README.md` 和知识文档
  - 新增 `requirements.txt`
  - 新增 `tests/test_workflow.py` 覆盖主链路和参数校验
  - 安装 Flask 依赖并通过测试验证
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/app.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/requirements.txt
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/config.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/api.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/intake/context_builder.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/evaluation/completeness.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/storage/markdown_writer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/graph.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/utils/time.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/utils/paths.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/base.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/InsightEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md

### 阶段 4：uv 项目初始化
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 使用 `uv init --bare --app --vcs none --python 3.13` 初始化项目元数据
  - 使用 `uv add` 迁移运行依赖 `Flask`、`PyYAML`、`langgraph`
  - 使用 `uv add --dev pytest` 建立开发测试依赖
  - 补充 `pyproject.toml` 的 build-system 和本地包声明，使 `uv` 环境可导入 `knowledgeforge`
  - 生成 `.venv` 与 `uv.lock`
  - 使用 `uv sync` 和 `uv run pytest tests/test_workflow.py` 完成验证
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/pyproject.toml
  - /Users/lpb/workspace/myProjects/KnowledgeForge/uv.lock
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md

### 阶段 5：批次 B 后置治理骨架
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 扩展治理相关 schema，新增结构化抽取、图谱同步、质量检测、版本记录和 post-storage 聚合结果模型
  - 新建 `postprocess`、`graph`、`quality`、`versioning` 模块骨架
  - 实现 `PostStoragePipeline`，按“结构化抽取 -> 路径关联 -> 质量检测 -> 版本记录”串联治理流程
  - 将 post-storage pipeline 接入 LangGraph 主流程，在 Markdown 落盘后继续执行治理节点
  - 扩展 API 返回内容，暴露治理结果和失败分类
  - 补充治理链路测试，验证 extraction、graph_sync、quality_check、version_record 都能返回
  - 清理临时验证目录
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/graph.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/postprocess/extractor.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/postprocess/pipeline.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/graph/neo4j_adapter.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/quality/checker.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/versioning/recorder.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md

### 阶段 6：批次 C 质量闭环与恢复能力
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 扩展质量检测规则，新增冲突、重复、引用与图谱一致性检查项
  - 将治理失败分类为 `repair_flow` 与 `research_flow`，并生成下一轮动作建议
  - 新增本地 JSON 状态持久化存储与审计日志
  - 新增 `/tasks/<task_id>/resume` 接口，实现任务恢复执行
  - 为恢复流程加入最大轮次保护
  - 将运行态目录切换到 `.knowledgeforge/` 并加入 `.gitignore`
  - 增加跨应用重建恢复、research flow 回流与 max rounds 的测试覆盖
  - 清理临时验证目录
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/.gitignore
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/config.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/api.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/quality/checker.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/postprocess/pipeline.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/graph.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/runtime/state_store.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/runtime/audit.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md

### 阶段 7：阶段 8 版本冻结与研报分支
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 扩展版本记录，增加 `frozen`、`frozen_at`、`report_eligible` 字段
  - 新增 frozen version 本地存储，固化通过质检后的冻结快照
  - 在任务持久化时自动冻结合格版本并记录审计事件
  - 新增 report service，只基于 frozen version 生成研报结果
  - 新增 `/tasks/<task_id>/frozen` 与 `/tasks/<task_id>/report` 接口
  - 限制未冻结任务无法获取 frozen version 或生成 report
  - 增加冻结版本与报告边界测试
  - 清理临时验证目录
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/config.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/versioning/recorder.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/api.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/runtime/frozen_store.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/reporting/report_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md

### 阶段 8：env 配置接入真实调用层
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 将 `.env` / `.env.example` 的 LLM、Embedding、Neo4j、MySQL、ChromaDB 配置统一接入 `AppConfig`
  - 新增 OpenAI 兼容聊天与 Embedding 客户端
  - 将 `QueryEngine` 改为通过配置注入的聊天与 Embedding 客户端生成查询摘要和向量
  - 新增 Neo4j 图谱客户端，并将 `Neo4jPathMapper` 改为尝试实际写入图数据库
  - 在图谱不可达时保留明确错误信息，但默认不阻塞本地主链路
  - 新增 `/config/status` 用于查看配置状态，不暴露密钥
  - 补充调用层集成测试与配置加载测试
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/pyproject.toml
  - /Users/lpb/workspace/myProjects/KnowledgeForge/.gitignore
  - /Users/lpb/workspace/myProjects/KnowledgeForge/.env.example
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/config.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/api.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/llms/openai_compatible.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/graph/client.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/graph/neo4j_adapter.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/postprocess/pipeline.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_integration_layers.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md

### 阶段 9：QueryEngine 节点化重构与单引擎测试
- **状态：** complete-with-followup
- **开始时间：** 2026-04-24
- 执行的操作：
  - 参考 BettaFish 的 QueryEngine 设计思路，将 `QueryEngine` 从单文件占位实现重构为 `search -> summary -> formatting` 的节点化结构
  - 新增 `state/`、`prompts/`、`tools/crawler.py`、`utils/` 等配套模块
  - 明确检索策略为“官方文档优先，教程补充”
  - 新增三引擎单独测试脚本 `scripts/test_single_engines.py`
  - 新增 `tests/test_query_engine.py`
  - 在依赖中补充 `beautifulsoup4`
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/base_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/summary_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/prompts/prompts.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/utils/ranking.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/utils/text_processing.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/scripts/test_single_engines.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_query_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/pyproject.toml

## 会话：2026-04-25

### 阶段 10：MediaEngine 节点化重构与趋势观点补充
- **状态：** complete-with-followup
- **开始时间：** 2026-04-24
- 执行的操作：
  - 参考 BettaFish 的 MediaEngine 设计思路，将 `MediaEngine` 从占位实现重构为 `search -> summary -> formatting` 的节点化结构
  - 新增 `state/`、`prompts/`、`tools/crawler.py`、`utils/` 等配套模块
  - 明确 `MediaEngine` 职责为“补充当下观点与未来走向”，不与 QueryEngine 的权威事实检索重叠
  - 为技术领域加入“中外技术社区混合”的默认来源策略，优先 `X / Reddit / Hacker News / GitHub Discussions / 技术博客`，同时补充 `V2EX / 掘金 / 知乎`
  - 新增 MediaEngine 专项测试 `tests/test_media_engine.py`
  - 更新三引擎单独测试脚本，使 `media` 路径支持真实构造和更短超时的 smoke test
  - 在 `TaskService` 中为 MediaEngine 注入真实 chat client
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/base_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/summary_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/prompts/prompts.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/utils/ranking.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/utils/text_processing.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/scripts/test_single_engines.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_media_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - MediaEngine 专项测试已通过
  - `scripts/test_single_engines.py --engine media ...` 可运行
  - 真实网络抓取仍可能退回到 query-plan 型趋势输出，因此 crawler 抓取质量仍需继续收敛
  - `tests/test_workflow.py` 本轮未重新做全量最终确认

### 阶段 11：仓库协作规则补充
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 在 `AGENTS.md` 与 `CLAUDE.md` 中新增“Completion Discipline”规则
  - 明确每次有意义任务完成后，必须同步 `progress.md`
  - 明确当任务改变实现方向时，需要同步 `task_plan.md` 与 `findings.md`
  - 明确默认需要检查 git 状态并提交，除非用户明确要求不提交
  - 明确仓库级规则变更时，`AGENTS.md` 与 `CLAUDE.md` 必须保持一致
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/AGENTS.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/CLAUDE.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md

### 阶段 12：QueryEngine / MediaEngine ReAct 闭环升级
- **状态：** complete-with-followup
- **开始时间：** 2026-04-24
- 执行的操作：
  - 为 `QueryEngine` 新增 `reflection_node`，将内部流程升级为“首次检索 -> 反思 -> 补检索 -> 总结”
  - 为 `MediaEngine` 新增 `reflection_node`，将内部流程升级为“首次观点检索 -> 反思 -> 补检索 -> 趋势总结”
  - 在两个 Engine 的 state 中补充 `search_history`、`observation_notes`、`reflection_notes`、`iteration_count`
  - 在 prompt 中补充反思阶段的 structured output 约束
  - 在 formatting 输出中加入 `反思结论`、`缺口` 和 `检索轨迹`
  - 更新专项测试，验证反思后会触发补检索查询
  - 重新验证单引擎脚本，确认 Query / Insight / Media 的独立运行路径仍可用
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/reflection_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/summary_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/prompts/prompts.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/reflection_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/summary_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/prompts/prompts.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_query_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_media_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - 两个 Engine 已具备最小 ReAct 闭环，但当前补检索轮次固定为 1
  - 反思节点已经能输出缺口和补检索 query，但策略仍偏规则化，后续可以继续增强
  - `tests/test_workflow.py` 本轮仍未重新做全量最终确认

### 阶段 13：QueryEngine 预定义优先来源策略
- **状态：** complete-with-followup
- **开始时间：** 2026-04-24
- 执行的操作：
  - 在 QueryEngine 代码中预定义教程/参考类优先来源集合
  - 将 tutorial 查询扩展为“通用查询 + 预定义高质量站点 site 查询”
  - 保持官方文档查询不写死域名，仍通过通用检索和自动识别来发现真正官方来源
  - 扩展 crawler 排序逻辑，使预定义高质量来源在教程/参考类结果中获得更高优先级
  - 更新 QueryEngine 与集成层测试，验证会生成带 `site:github.com` 等限定的 tutorial 查询
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/utils/ranking.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_query_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_integration_layers.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - 预定义来源优先策略已生效，但目前主要作用于 tutorial / reference 类查询
  - 官方来源仍依赖自动识别，符合“不写死官方文档域名”的要求
  - 真实网页抓取命中率仍受网络与 crawler 超时影响，后续可继续增强

### 阶段 14：QueryEngine 官方来源自动识别
- **状态：** complete-with-followup
- **开始时间：** 2026-04-24
- 执行的操作：
  - 在 QueryEngine 首轮搜索结果中增加候选官方域名自动识别
  - 根据标题、URL 和 snippet 的规则信号提取候选官方域名
  - 将候选官方域名写入 state，并透传到反思阶段
  - 让第二轮官方补检索优先使用这些候选官方域名做结果加权
  - 在格式化输出中增加 `候选官方域名`，便于观察自动识别效果
  - 更新 QueryEngine 与集成层测试，验证候选官方域名会出现在输出中
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/utils/ranking.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/reflection_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/prompts/prompts.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_query_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_integration_layers.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - 首轮结果已有候选官方域名自动识别能力
  - 第二轮官方补检索已能使用候选官方域名增权，但仍属于轻量规则识别
  - 真实网络未命中时，输出会明确显示 `候选官方域名：无`，不会伪造官方来源

### 阶段 15：单引擎脚本切换为真实联调模式
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 将 `scripts/test_single_engines.py` 默认模式切换为 `live`
  - 为 live 模式拉长 LLM 和 crawler 超时，避免过早把真实联调退化成 smoke test
  - 增加真实来源检查逻辑，不再把 `example.com` / `query-plan` / `media-plan` 这类 fallback 输出当作成功
  - 在未拿到真实 Query / Media 来源时，脚本明确报错并返回非零退出码
  - 保留 `--allow-fallback` 开关，供只想做 smoke test 的场景使用
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/scripts/test_single_engines.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - 脚本现在确实是在“测真实 agent”，而不是默认接受 fallback
  - 对 `python scripts/test_single_engines.py --domain ML` 的复测结果是 `query, media` 未拿到真实来源，脚本按预期以错误退出
  - 如果只想快速 smoke test，可显式使用 `--allow-fallback`

### 阶段 16：单引擎脚本增加过程日志
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 为 `scripts/test_single_engines.py` 增加 LLM、Embedding、Query crawler、Media crawler 的跟踪包装
  - 输出配置日志、Engine 启动日志、LLM 阶段日志、query 日志、命中站点日志、抓取 URL 日志
  - 在 live 模式下复测 `ML`，确认日志能够直接暴露 `query.plan` 的 LLM 超时以及 DuckDuckGo HTML 查询无命中的事实
  - 修正 LLM 阶段识别顺序，避免将反思阶段误标成规划阶段
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/scripts/test_single_engines.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - 现在线路问题已经可以从脚本日志直接定位，而不需要只看最终 fallback 输出猜原因
  - `ML` 这个例子暴露出的真实问题是 “LLM 首轮超时 + 搜索结果无命中”，不是“agent 没跑”

### 阶段 17：Query / Media crawler 接入 agent-browser
- **状态：** complete-with-followup
- **开始时间：** 2026-04-24
- 执行的操作：
  - 参考 `agent-browser` skill，将浏览器式搜索与正文抓取接入 QueryEngine / MediaEngine 的 crawler
  - 新增 `knowledgeforge/tools/agent_browser_cli.py`，封装 `agent-browser` 的搜索页打开、结果提取、正文抓取与清理逻辑
  - 调整 Query / Media crawler 为“优先走 browser，失败再退回 httpx” 的双路径
  - 保持现有测试接口不变，避免影响 Engine 其余节点与主流程
  - 复测 `ML` 场景，确认真实问题已从“只看最终 fallback”转为“可以观察浏览器抓取是否命中”
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/tools/agent_browser_cli.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - Query / Media crawler 现在已经具备 browser-first 抓取能力
  - `ML` 场景下浏览器抓取并没有立刻解决无命中问题，说明 query 质量仍是关键瓶颈
  - 现阶段最稳的路径是“浏览器抓取增强 + query normalization”组合，而不是只切换抓取后端

### 阶段 18：LLM 术语归一化接入 Query / Media
- **状态：** complete-with-followup
- **开始时间：** 2026-04-24
- 执行的操作：
  - 新增基于 LLM 的术语归一化模块，在搜索规划前先做缩写补全与搜索词扩展
  - 为 QueryEngine / MediaEngine state 增加 `normalized_domain`、`aliases`、`search_terms`、`normalization_reasoning`
  - 将 Query / Media 的 fallback 搜索规划改为优先使用归一化后的完整术语
  - 在输出中增加 `术语归一化` 与 `归一化说明`
  - 增加测试覆盖，验证 `ML` 会被扩展成 `machine learning`
  - 用 live 脚本复测 `ML`，确认日志中已经出现 `normalize.domain -> query.plan` 的链路
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/utils/query_normalization.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_query_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_media_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_integration_layers.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/scripts/test_single_engines.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - `ML` 这类缩写现在已经会先归一化成 `Machine Learning`
  - 当前剩余问题已从“缩写 query 太差”收敛成“LLM 规划超时与搜索命中率”问题
  - 归一化模块同时保留了本地缩写表回退，不会因为 LLM 不可用而完全失效

### 阶段 19：agent-browser 独立联调诊断
- **状态：** complete-with-followup
- **开始时间：** 2026-04-24
- 执行的操作：
  - 在 `tests/` 下新增 `tests/test_agent_browser_live.py`，专门绕过 Query / Media agent，直接调用 `agent-browser` 做独立联调
  - 为测试封装带超时与进程组强制回收的 `run_agent_browser(...)`，避免 `agent-browser` 卡住时把整个 pytest 一起拖死
  - 分别验证“打开 DuckDuckGo HTML 搜索页并抽取结果”和“打开 LangGraph 官网并抓取正文”两条最小真实路径
  - 额外检查 `agent-browser session list`、帮助信息和后台 Chrome for Testing 进程，确认 daemon 能启动、问题集中在 `open/get/snapshot` 交互层
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_agent_browser_live.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - `agent-browser` 二进制和 daemon 本身可用，但当前环境中 `open` 在 30 秒内无法稳定返回
  - 这说明 Query / Media 的真实联网失败，至少有一部分根因在浏览器抓取底座，而不只是 query 质量
  - 在 `agent-browser` 稳定性未解决前，crawler 需要继续保留非浏览器兜底路径

### 阶段 20：单引擎调用日志持久化与 API 地址追踪
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 为 `scripts/test_single_engines.py` 增加按时间命名的运行日志文件，默认保存到 `logs/single-engines-YYYYMMDD-HHMMSS.log`
  - 将 LLM / Embedding 日志扩展为包含 method、endpoint、model、timeout、payload 尺寸、耗时、返回 keys 或异常
  - 为 Query / Media crawler 增加 trace callback，记录 browser-first 搜索、httpx fallback 搜索、正文抓取 URL、状态码、命中数和失败原因
  - 为 `AgentBrowserCLI` 增加命令级 trace，并压缩 `eval` 日志为脚本长度，避免整段 JS 污染输出
  - 将 `logs/` 加入 `.gitignore`，避免运行记录进入版本库
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/scripts/test_single_engines.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/tools/agent_browser_cli.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/.gitignore
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - 单引擎脚本现在能输出并持久化每次关键外部调用的 API 地址和失败原因
  - `ML` smoke 复测确认日志能同时观察 LLM 超时、browser 搜索 URL、httpx URL、fetch URL、Embedding endpoint 和耗时
  - 真实网络命中质量仍未解决，本次只增强可观测性和运行记录保存

### 阶段 21：Intake 澄清入口收口
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 将 intake 会话主线收口为 `create -> append message -> confirm -> task` 的后端入口
  - 补齐 `ClarificationResult`、`IntakeSession`、`ContextBuilder`、`IntakeSessionStore`、`TaskService` 和 API 路由之间的契约
  - 明确 `append_intake_message` 基于完整消息历史重新澄清，而不是只处理最后一句
  - 固化 `concept_explanation` / `qa` 不能直接 confirm 成知识采集任务的规则
  - 为 QueryEngine / MediaEngine 增加“已确认领域优先”的测试覆盖，避免确认后的领域再次被偏移性归一化
  - 新增 intake API 回归测试，覆盖创建、追加、确认、空消息和缺失 session 的错误路径
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/intake/context_builder.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/intake/clarifier.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/runtime/intake_session_store.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/api.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_query_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_media_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - intake 入口现在已经从“可跑雏形”收口成了可稳定回归的后端会话层
  - 推荐路径已变为“模糊输入先走 intake，会话确认后再启动 task”，但 `/tasks` 直跑仍保留
  - 真实联网抓取与 `agent-browser` 排障继续保留到下一优先级，不纳入本轮主目标

### 阶段 22：crawler 降级策略与 browser 短路
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 审计当前未提交改动，确认保留 `tests/test_agent_browser_live.py`，还原 `AGENTS.md`、`tests/test_workflow.py` 的临时试验改动以及 `tmp-fast*` 运行产物删改
  - 为 `AgentBrowserCLI` 增加健康状态与失败原因记录；browser 搜索或抓取超时后，当前实例会标记为不健康并短路后续 browser 调用
  - 将 Query / Media crawler 的 HTTP 兜底改为 provider 链，先尝试 DuckDuckGo HTML，再尝试 Bing HTML
  - 新增 `tests/test_browser_fallbacks.py`，覆盖 browser 超时后短路、以及 Query / Media crawler 会落到第二条 HTTP provider 的路径
  - 复跑 `tests/test_agent_browser_live.py`，确认当前“预热 daemon + page 级 close”的测试版本可通过
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/tools/agent_browser_cli.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_agent_browser_live.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_browser_fallbacks.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 当前保守结论：
  - `agent-browser` 不是完全不可用，但默认调用方式仍偏脆弱
  - browser 超时后的实例级短路已显著降低重复卡顿风险
  - Query / Media crawler 现在具备更明确的 HTTP 链式降级策略，不再只依赖单一 fallback provider

### 阶段 23：整体构建进度盘点与未完成任务登记
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 复核当前 `task_plan.md`、`progress.md`、最近 git 提交和工作区状态
  - 确认阶段 1-8 主链路已完成：Flask、LangGraph、三路采集、完整性评估、Markdown 落盘、后置治理、质量闭环、版本冻结和研报分支均已落地
  - 确认阶段 9-22 增强链路已完成或 complete-with-followup：QueryEngine / MediaEngine 节点化、ReAct、术语归一化、intake 澄清入口、单引擎日志和 crawler 降级策略均已接入
  - 记录当前最新实现提交为 `06a99d3 Harden crawler browser fallback`
  - 确认本轮检查时仅 `AGENTS.md` 存在会话记忆类本地变更，不登记为项目未完成任务
- 当前整体状态：
  - 主链路已闭合，可从领域输入进入采集、评估、落盘、治理、冻结和研报消费边界
  - 推荐入口已升级为 `intake session -> clarify -> append message -> confirm -> task`
  - Query / Media 已具备节点化、最小 ReAct、术语归一化、来源类型标注和失败可追踪日志
  - crawler 已具备 browser-first、browser 失败短路和 HTTP provider 链式降级
- 未完成任务：
  - 真实联网抓取命中质量仍需提升：browser-first 能运行并有降级，但真实 source 命中率还没有达到稳定可用标准
  - `agent-browser` 会话稳定性仍需继续观察：当前通过预热 daemon、page 级 close、失败短路降低风险，但默认调用仍偏脆弱
  - Query planning LLM 超时仍需治理：需要更长或可配置 timeout、重试策略，或更轻量的 fallback query planner
  - 官方来源自动识别仍需验证：目前能提取候选官方域名，但还缺“候选域名是否真官方”的验证步骤
  - MediaEngine 观点源质量仍需增强：需要更细的平台白名单、低质量帖子过滤，以及博客、社区、社交热度的区分
  - workflow 全量稳定回归仍需最终确认：默认回归要继续避免真实网络扰动，live 测试单独保留
  - 单引擎真实联调仍需再次跑 `ML` / `LangGraph` / `深度学习` 等场景，确认 fallback 不再产生 `example.com` 占位来源作为 live 成功结果
- 当前保守结论：
  - KnowledgeForge 已完成端到端骨架和主要后端能力闭环
  - 下一轮构建应优先聚焦“真实查询质量”，而不是继续扩展新模块
  - 未完成任务集中在联网质量、来源真实性验证和稳定回归隔离

## 测试结果
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| session-catchup | 项目根目录 | 输出恢复信息或安静完成 | 安静完成，无需额外同步 | 通过 |
| planning-review | task_plan.md | 形成可执行实施阶段与首批批次 | 已形成 8 个阶段、3 个批次与实现顺序 | 通过 |
| pytest | `python3 -m pytest tests/test_workflow.py` | 主链路与参数校验通过 | 2 个测试通过 | 通过 |
| uv-pytest | `uv run pytest tests/test_workflow.py` | uv 环境可安装项目并通过测试 | 2 个测试通过 | 通过 |
| governance-pytest | `uv run pytest tests/test_workflow.py` | 后置治理骨架接入后主链路与治理结果通过 | 3 个测试通过 | 通过 |
| recovery-pytest | `uv run pytest tests/test_workflow.py` | 回流分类、恢复与最大轮次保护通过 | 5 个测试通过 | 通过 |
| frozen-report-pytest | `uv run pytest tests/test_workflow.py` | 冻结版本与研报边界通过 | 7 个测试通过 | 通过 |
| env-layer-pytest | `uv run pytest tests/test_workflow.py tests/test_integration_layers.py` | env 配置接入真实调用层后仍通过 | 10 个测试通过 | 通过 |
| query-engine-pytest | `uv run pytest tests/test_query_engine.py tests/test_integration_layers.py` | QueryEngine 节点化重构后的专项测试与集成层验证通过 | 通过 | 通过 |
| single-engine-script | `uv run python scripts/test_single_engines.py --engine all --domain LangGraph --subdomain 工作流编排 --subdomain 状态持久化 --focus-point 官方文档` | 三引擎单独测试脚本可运行 | 可运行 | 通过 |
| media-engine-pytest | `uv run pytest tests/test_media_engine.py tests/test_query_engine.py tests/test_integration_layers.py` | MediaEngine 节点化重构后专项测试与既有 Query/集成层验证通过 | 6 个测试通过 | 通过 |
| media-single-engine-script | `uv run python scripts/test_single_engines.py --engine media --domain LangGraph --subdomain 工作流编排 --subdomain 状态持久化 --focus-point 社区观点` | MediaEngine 单独脚本可运行 | 可运行 | 通过 |
| react-engine-pytest | `uv run pytest tests/test_media_engine.py tests/test_query_engine.py tests/test_integration_layers.py` | QueryEngine / MediaEngine ReAct 闭环升级后仍通过专项测试与集成层验证 | 6 个测试通过 | 通过 |
| react-single-engine-script | `uv run python scripts/test_single_engines.py --engine all --domain LangGraph --subdomain 工作流编排 --subdomain 状态持久化 --focus-point 官方文档 --focus-point 社区观点` | 三引擎脚本在 ReAct 升级后仍可运行 | 可运行 | 通过 |
| query-priority-pytest | `uv run pytest tests/test_query_engine.py tests/test_integration_layers.py tests/test_media_engine.py` | QueryEngine 引入预定义优先来源策略后仍通过专项测试与集成层验证 | 6 个测试通过 | 通过 |
| query-priority-script | `uv run python scripts/test_single_engines.py --engine query --domain LangGraph --subdomain 工作流编排 --focus-point 官方文档 --focus-point 最佳实践` | QueryEngine 单引擎脚本在优先来源策略下可运行 | 可运行 | 通过 |
| official-domain-pytest | `uv run pytest tests/test_query_engine.py tests/test_integration_layers.py tests/test_media_engine.py` | QueryEngine 官方来源自动识别接入后仍通过专项测试与集成层验证 | 6 个测试通过 | 通过 |
| official-domain-script | `uv run python scripts/test_single_engines.py --engine query --domain LangGraph --subdomain 工作流编排 --focus-point 官方文档 --focus-point 最佳实践` | QueryEngine 单引擎脚本可展示候选官方域名识别结果 | 可运行 | 通过 |
| live-script-ml | `uv run python scripts/test_single_engines.py --domain ML` | 脚本默认要求真实来源，未命中时应明确失败退出 | `query, media` 未拿到真实来源，脚本以 exit 2 退出 | 通过 |
| live-script-ml-logs | `uv run python scripts/test_single_engines.py --domain ML --allow-fallback` | 脚本应输出 LLM、query、抓取站点等过程日志 | 已确认输出 `LLM timeout`、query 明细、站点命中/无命中和抓取日志 | 通过 |
| browser-crawler-pytest | `uv run pytest tests/test_query_engine.py tests/test_integration_layers.py tests/test_media_engine.py` | 接入 browser-first crawler 后既有测试仍通过 | 6 个测试通过 | 通过 |
| normalization-pytest | `uv run pytest tests/test_query_engine.py tests/test_media_engine.py tests/test_integration_layers.py` | LLM 术语归一化接入后 Query / Media / 集成层仍通过 | 8 个测试通过 | 通过 |
| normalization-script | `uv run python scripts/test_single_engines.py --engine query --domain ML --allow-fallback` | `ML` 应先归一化为 `Machine Learning` 再进入 query planning | 已确认日志出现 `normalize.domain`，后续 query 为 `Machine Learning ...` | 通过 |
| agent-browser-live-pytest | `uv run pytest tests/test_agent_browser_live.py -q` | 独立验证 `agent-browser` 能打开真实页面并提取结果 | 2 个测试失败；DuckDuckGo HTML 和 LangGraph 官网的 `open` 均在 30 秒超时 | 已记录 |
| logging-pycompile | `python3 -m py_compile scripts/test_single_engines.py knowledgeforge/tools/agent_browser_cli.py agent/QueryEngine/tools/crawler.py agent/MediaEngine/tools/crawler.py` | 日志增强代码语法正确 | 通过 | 通过 |
| logging-unit-pytest | `uv run pytest tests/test_query_engine.py tests/test_media_engine.py tests/test_integration_layers.py -q` | 日志 callback 不破坏 Query / Media / 集成测试 | 8 个测试通过 | 通过 |
| logging-insight-script | `uv run python scripts/test_single_engines.py --engine insight --domain ML --allow-fallback --log-dir logs` | 创建时间戳日志并保持脚本可运行 | 生成 `logs/single-engines-20260424-144313.log`，脚本通过 | 通过 |
| logging-query-smoke | `uv run python scripts/test_single_engines.py --engine query --domain ML --mode smoke --allow-fallback --log-dir logs` | 输出并保存 LLM / Embedding / browser / httpx 的 endpoint 与失败原因 | 生成 `logs/single-engines-20260424-144323.log`，脚本通过 | 通过 |
| intake-regression-pytest | `uv run pytest tests/test_workflow.py tests/test_query_engine.py tests/test_media_engine.py -q` | intake 会话、确认后上下文映射、已确认领域优先规则和既有主流程同时通过 | 21 个测试通过 | 通过 |
| browser-fallback-pytest | `uv run pytest tests/test_browser_fallbacks.py tests/test_query_engine.py tests/test_media_engine.py tests/test_agent_browser_live.py -q` | browser 超时短路、HTTP 链式降级和 live agent-browser 诊断同时通过 | 13 个测试通过 | 通过 |
| progress-audit | `git status --short` + `git log --oneline -8` + `progress.md` / `task_plan.md` 复核 | 整体进度和未完成任务可被明确登记 | 已登记阶段 23；本轮只更新进度文档，不改运行代码 | 通过 |

## 错误日志
| 时间戳 | 错误 | 尝试次数 | 解决方案 |
|--------|------|---------|---------|
| 2026-04-24 | `agent-browser` 在默认真实 smoke 中仍可能出现 wait/eval/get 超时 | 1 | 已增加实例级 browser 短路与 HTTP provider 链式降级；live 测试改为预热 daemon + page 级 close 后通过 |

### 阶段 24：Flask 功能展示前端
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 新增 Flask 首页路由，渲染 KnowledgeForge 功能工作台
  - 新增模板与本地 CSS / JavaScript 静态资源
  - 页面覆盖配置状态、intake 会话、任务创建、查询、恢复、冻结版本和研报生成等现有 API
  - 新增首页渲染与状态接口回归测试
- 验证结果：
  - `uv run pytest tests/test_dashboard.py tests/test_workflow.py -q`：17 个测试通过
  - `uv run pytest -q`：32 个测试通过
  - 本地 Flask smoke：`http://127.0.0.1:5001/` 首页 200，CSS / JS 静态资源 200

### 阶段 25：Machine Learning 输出质量诊断
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 检查 `save/Machine Learning/README.md` 与 `save/Machine Learning/基础概念/20260424-machine-learning-mixed.md`
  - 复核 `.knowledgeforge/tasks/32bd2f1a6e484e24b40a17257742ae60.json`、audit 与 intake session
  - 追查 QueryEngine / MediaEngine 的 search、crawler、ranking、summary、formatting 节点
  - 追查 CompletenessEvaluator、MarkdownKnowledgeWriter、QualityChecker 和 VersionRecorder 的门禁逻辑
- 诊断结论：
  - intake 已正确将 `ML` 归一化为 `Machine Learning`，不是入口识别失败
  - 搜索规划 LLM 超时后触发 fallback；browser 无结果、DuckDuckGo 超时后，Bing fallback 返回 Weblio 词典页
  - crawler 与 ranking 没有进行完整领域短语相关性校验，且把请求类型 `official` 误当作结果可信度依据
  - Media 平台分类没有硬过滤，非社区/社交/博客页面会被包装为 requested platform type
  - 完整性评估和质量检测只检查“是否有来源/章节/实体”，没有检查来源是否相关、权威、可支撑结论
  - 因此错误文档被写入、通过质检、冻结为 verified

### 阶段 26：质量流水线来源门禁优化
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 执行 `docs/superpowers/plans/2026-04-24-quality-pipeline-optimization.md`
  - Query / Media crawler 新增 Google、Bing、DuckDuckGo、Brave HTTP provider 顺序，并解析 Google / Brave 结果
  - Query crawler 新增 Bing redirect URL 解码、领域短语相关性过滤和 Wikipedia summary supplement
  - Media crawler 复用领域短语过滤，并将未知平台分类从 requested_type 回退改为 `unknown`
  - Query source reliability 改为结合 URL 与候选官方域名判断，避免 `source_type=official` 自动获得 `high`
  - CompletenessEvaluator 新增来源可信度门禁和 `failure_categories`
  - QualityChecker 新增 source quality checks，弱来源或无来源会进入 `research_flow`
  - Markdown Writer 根据 completeness 状态输出动态结论，并在证据表优先使用 source snippet
  - 新增多 provider、来源相关性、完整性来源门禁、质量来源门禁、writer 状态文案和 ML Weblio 回归测试
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/tools/wikipedia_fetcher.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/utils/ranking.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/tools/crawler.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/utils/ranking.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/evaluation/completeness.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/quality/checker.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/storage/markdown_writer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_multi_provider_search.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_source_relevance_filter.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_completeness_source_gate.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_quality_source_checks.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_writer_dynamic_status.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_ml_regression.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_browser_fallbacks.py
- 验证结果：
  - `python3 -m py_compile agent/QueryEngine/tools/crawler.py agent/MediaEngine/tools/crawler.py agent/QueryEngine/nodes/search_node.py agent/MediaEngine/nodes/search_node.py agent/QueryEngine/nodes/formatting_node.py knowledgeforge/models.py knowledgeforge/evaluation/completeness.py knowledgeforge/quality/checker.py knowledgeforge/storage/markdown_writer.py`：通过
  - `uv run pytest tests/test_multi_provider_search.py tests/test_source_relevance_filter.py tests/test_completeness_source_gate.py tests/test_quality_source_checks.py tests/test_writer_dynamic_status.py tests/test_ml_regression.py -q`：45 个测试通过
  - `uv run pytest tests/test_browser_fallbacks.py tests/test_query_engine.py tests/test_media_engine.py tests/test_integration_layers.py -q`：13 个测试通过
  - `uv run pytest tests/ -q --ignore=tests/test_agent_browser_live.py`：75 个测试通过
- 当前保守结论：
  - Weblio / sewing machine 这类低相关噪声现在会在相关性、可信度、完整性和质量检查多个层级被拦截
  - 未通过来源质量门禁的文档不会被标记为可进入治理 / 冻结 / 报告流程
  - live 浏览器诊断测试本轮未运行，仍按既有策略与默认回归隔离

### 阶段 27：QueryEngine 查询计划决策化
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 新增 `SearchQuestion` 结构，扩展 `SearchPlan.questions`
  - 重写 QueryEngine 搜索规划 prompt，要求先输出查询决策表，再执行检索
  - 调整 search node，使初始检索按计划问题逐项执行，并记录 question / expected_info / hits / status
  - 调整 reflection node，使反思输入包含问题清单与检索轨迹，并在 fallback 中只针对 `insufficient` 问题补检索
  - 调整 formatting node，在 `raw_material` 中输出查询计划、预期信息、满足标准、fallback 查询和逐项检索轨迹
  - 将无真实网页结果的 query-plan fallback 来源降级为 `unknown`
  - 扩展 QueryEngine 专项测试，覆盖结构化计划、执行顺序、fallback plan、insufficient 状态和补检索范围
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/state/__init__.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/prompts/prompts.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/reflection_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_query_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_query_engine.py`：6 个测试通过
  - `uv run pytest tests/test_source_relevance_filter.py tests/test_completeness_source_gate.py tests/test_quality_source_checks.py`：23 个测试通过
  - `uv run pytest tests/test_workflow.py`：15 个测试通过
- 当前保守结论：
  - QueryEngine 已具备“先决策、后检索”的可审计计划阶段
  - 只有 query-plan 而无真实网页证据时不会再输出高可信来源

### 阶段 28：QueryEngine 中间日志输出与前端可见化
- **状态：** complete
- **开始时间：** 2026-04-24
- 执行的操作：
  - 为 `EngineRunResult` 增加可选 `execution_log`
  - QueryEngine 在计划生成、逐项检索、问题完成、文档抓取、Embedding、反思和总结 fallback 时写入结构化事件
  - `TaskService` 聚合各 Engine 的 execution log 到任务响应顶层，并同步写入 audit jsonl
  - `AuditLogger` 增加读取能力，新增 `/tasks/<task_id>/logs`
  - 前端结果区新增“QueryEngine 查询计划”和“调用与执行日志”面板，并在任务操作中增加“查看日志”
  - 验证 5000 当前被 macOS AirTunes 占用，使用 5001 启动 Flask smoke
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/reflection_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/summary_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/runtime/audit.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/api.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/templates/index.html
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_dashboard.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_query_engine.py tests/test_workflow.py tests/test_dashboard.py`：24 个测试通过
  - `uv run pytest tests/ -q --ignore=tests/test_agent_browser_live.py`：79 个测试通过
  - `curl http://127.0.0.1:5001/`：页面包含 QueryEngine 查询计划、调用与执行日志、查看日志
  - `curl http://127.0.0.1:5001/tasks/<task_id>/logs`：返回 `query_plan_created` 与 `query_search_executed`
- 当前保守结论：
  - 任务响应、前端和 audit jsonl 现在都能看到 QueryEngine 查询计划与中间执行事件
  - 浏览器中的 5000 不是当前 Flask 服务；本轮可用地址是 `http://127.0.0.1:5001/`

### 阶段 29：任务列表保存与查看
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - `TaskStateStore` 增加持久化任务列表扫描能力
  - `TaskService` 增加 `list_tasks()`，返回任务摘要列表
  - 新增 `GET /tasks` API，与现有 `POST /tasks` 共用路径
  - 前端任务操作区新增“查看任务列表”按钮
  - 结果区新增“任务列表”面板，列表项点击后回填 Task ID
  - 新增任务列表 API、跨 app 重建持久化列表和前端文案测试
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/runtime/state_store.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/api.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/templates/index.html
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_dashboard.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_workflow.py tests/test_dashboard.py`：20 个测试通过
  - `uv run pytest tests/ -q --ignore=tests/test_agent_browser_live.py`：81 个测试通过
- 当前保守结论：
  - 已保存任务可通过 `GET /tasks` 查看摘要列表
  - 前端可查看任务列表，并从列表项回填 Task ID 继续操作

### 阶段 30：QueryEngine 查询计划文件落盘
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 确认原 Writer 只写综述文档和领域 README，未保存 QueryEngine 中间查询计划文件
  - 在 Markdown Writer 中新增 QueryEngine 查询计划文档生成逻辑
  - 查询计划文档保存到 `save/{领域}/{子领域}/`，使用 `doc_type=note`、`source_type=query`
  - 查询计划文档包含 YAML front matter、摘要、关键结论、背景、查询计划、执行事件、证据与来源、实体关系候选、不确定性、后续动作和变更记录
  - 主综述文档的“后续动作”引用查询计划文件路径
  - 实际生成验证 `save/Machine Learning/最新论文方向/20260425-machine-learning-queryengine-query.md`
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/storage/markdown_writer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_writer_dynamic_status.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 本地生成但不纳入 git 的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/save/Machine Learning/最新论文方向/20260425-machine-learning-queryengine-query.md
- 验证结果：
  - `uv run pytest tests/test_writer_dynamic_status.py tests/test_workflow.py`：22 个测试通过
  - `uv run pytest tests/ -q --ignore=tests/test_agent_browser_live.py`：82 个测试通过
- 当前保守结论：
  - 后续 Machine Learning / 最新论文方向任务会在对应 save 子目录下生成查询计划 Markdown 文件
  - `save/` 被 `.gitignore` 忽略，因此生成的知识文档保留在本地，不随代码提交

### 阶段 31：QueryEngine 查询计划清单化与前端显示优化
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 为 `SearchQuestion` 增加 `plan_item_id`、`search_targets`、`completed_at`
  - 将查询状态调整为 `planned`、`in_progress`、`completed`、`insufficient`
  - 搜索规划 prompt 要求输出 `search_targets`，作为需要查询/确认的内容列表
  - QuerySearchNode 在每个计划项开始、执行查询、完成后写入结构化事件
  - QueryFormattingNode 输出 `☑/☐` 勾选标记、查询内容、预期信息、满足标准和补查查询
  - Markdown Writer 兼容新的勾选格式并写入查询计划文件
  - 前端 QueryEngine 查询计划面板改为从 `execution_log` 重建结构化卡片，显示勾选、状态、查询语句、查询内容和满足标准
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/state/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/prompts/prompts.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/formatting_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/storage/markdown_writer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_query_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_writer_dynamic_status.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_query_engine.py tests/test_writer_dynamic_status.py tests/test_workflow.py tests/test_dashboard.py`：30 个测试通过
  - `uv run pytest tests/ -q --ignore=tests/test_agent_browser_live.py`：82 个测试通过
- 当前保守结论：
  - 查询计划现在以清单形式构建和展示，每条查询执行完成后会立即记录 completed 或 insufficient
  - 前端不再依赖 raw_material 文本解析，展示效果更适合浏览和排障

### 阶段 32：前端实时展示查询进度
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 新增 `POST /tasks/async`，创建任务后立即返回 `running` 状态和 `task_id`
  - TaskService 使用后台线程继续执行 workflow，并先保存初始任务状态，保证 `/tasks/<task_id>` 与 `/tasks/<task_id>/logs` 可立即读取
  - QueryEngine 节点统一通过 `_record_event` 记录执行事件，并在运行中实时写入 audit log
  - RequestContext 增加 `task_id`，让并行执行中的 QueryEngine 能可靠关联当前任务
  - 前端直接创建任务改为异步启动，并轮询任务日志和任务状态
  - QueryEngine 查询计划面板从实时日志重建卡片，展示“待查询 / 查询中 / 已完成 / 需补检索”和每条查询执行记录
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/base_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/reflection_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/summary_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/api.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/templates/index.html
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_query_engine.py tests/test_workflow.py tests/test_dashboard.py`：27 个测试通过
- 当前保守结论：
  - 前端启动任务后无需等待 workflow 完成，即可看到查询计划生成、单项开始查询、查询执行和完成状态
  - 同步 `/tasks` 仍保留，现有 API 与回归测试不受异步前端入口影响

### 阶段 33：任务管理修改与删除
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 新增 `PATCH /tasks/<task_id>`，支持修改任务上下文字段、状态和管理备注
  - 新增 `DELETE /tasks/<task_id>`，支持删除任务状态与冻结版本记录
  - 运行中的任务禁止修改和删除，避免后台线程写回已删除任务
  - TaskStateStore 与 FrozenVersionStore 增加 delete 能力
  - 前端任务操作区新增“任务修改 JSON”“保存修改”“删除任务”
  - 任务列表项点击后回填 Task ID，并填充可编辑 JSON 草稿
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/api.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/runtime/state_store.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/runtime/frozen_store.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/templates/index.html
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `node --check knowledgeforge/static/js/dashboard.js`：通过
  - `uv run pytest tests/test_workflow.py tests/test_dashboard.py`：23 个测试通过
  - `uv run pytest tests/ -q --ignore=tests/test_agent_browser_live.py`：85 个测试通过
- 当前保守结论：
  - 任务管理只处理任务元数据与任务记录，不自动删除 `save/` 下已经生成的知识文档

### 阶段 34：顶部能力与配置面板默认收起
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 将“主流程能力”面板改为原生 `details/summary` 折叠面板
  - 将“配置状态”面板改为原生 `details/summary` 折叠面板
  - 两个面板默认收起，点击标题区可展开或收起
  - 增加折叠状态按钮样式，展开时显示“收起”
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/templates/index.html
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `node --check knowledgeforge/static/js/dashboard.js`：通过
  - `uv run pytest tests/test_dashboard.py tests/test_workflow.py`：23 个测试通过
  - `uv run pytest tests/ -q --ignore=tests/test_agent_browser_live.py`：85 个测试通过
- 当前保守结论：
  - 首页默认更聚焦任务操作区域，同时仍可展开查看主流程能力和配置状态

### 阶段 35：配置状态详情增强
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - `/config/status` 从布尔摘要扩展为分组运行配置
  - LLM 组展示 provider、OpenAI-compatible chat 模型、chat base_url、embedding 模型、embedding base_url、维度和 key 是否存在
  - 增加 storage、retrieval、graph、database、runtime 分组
  - 保留 legacy 布尔字段，避免旧调用方完全断裂
  - 前端配置状态改为分组卡片，支持嵌套字段扁平展示
  - 不展示 API key 明文，只展示 `api_key_present`
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/config.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_dashboard.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `node --check knowledgeforge/static/js/dashboard.js`：通过
  - `uv run pytest tests/test_dashboard.py tests/test_workflow.py`：23 个测试通过
- 当前保守结论：
  - 配置状态面板现在能直接看到 LLM provider、模型名和 API 地址，同时不会泄露密钥

### 阶段 36：前端动作实时展示修复
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 排查 `/tasks/async`、`/tasks/{task_id}/logs`、`dashboard.js` 和 QueryEngine 实时事件链路
  - 将 intake 确认任务改为复用异步启动路径，避免确认按钮同步阻塞到任务结束
  - 前端在 intake 确认返回 task_id 后立即启动轮询
  - QueryEngine 实时事件写入 audit log 的同时刷新运行中 task state
  - 新增 `current_action`，让摘要区展示当前查询计划、搜索、抓取等动作
  - 补充回归测试覆盖 intake 确认异步启动与实时任务详情
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_workflow.py -q`：22 passed
  - `uv run pytest tests/test_dashboard.py -q`：2 passed
  - `uv run pytest -q`：88 passed
- 当前保守结论：
  - 前端现在能在直接任务和 intake 确认任务中看到 QueryEngine 的中间动作；日志和任务详情都保持可轮询。

### 阶段 37：logs 新日志落盘补写
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 复查 `/tasks/{task_id}/logs` 与 task state `execution_log` 的数据来源差异
  - 将 logs 接口改为读取 audit jsonl 前后合并任务快照里的 `execution_log`
  - 当 audit jsonl 缺少任务快照中的执行事件时，自动补写到 audit 文件
  - 增加去重 key，避免重复追加同一条 QueryEngine 执行事件
  - 补充回归测试确认 logs 返回新事件且 audit jsonl 已落盘
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_workflow.py -q`：23 passed
  - `uv run pytest -q`：89 passed
- 当前保守结论：
  - 即使新的执行事件只先进入任务快照，访问 logs 时也会被补写进 audit jsonl，后续刷新和重启后仍能看到。

### 阶段 38：三路 Agent 计划确认与流程可视化
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 新增统一 `EnginePlan`、`EnginePlanItem`、`WorkflowStepEvent` 模型
  - 为 Insight / Query / Media 三路 Engine 增加 `plan(...)` 入口
  - 将 `/tasks/async` 与 intake confirm 改为先生成三路计划并停在 `awaiting_plan_confirmation`
  - 新增 `GET /tasks/<task_id>/plan` 与 `POST /tasks/<task_id>/plan/confirm`
  - 确认计划后再异步启动 LangGraph 三路并行采集
  - 扩展 workflow step 事件，前端 Flow Map 可按 planning / awaiting_confirmation / collecting / evaluating / writing / governing / versioning 聚焦
  - 前端将 QueryEngine 单计划面板升级为“三路 Agent 执行计划”，并增加确认计划按钮
  - 补充三路计划生成、已确认计划执行、API 确认闸门和 dashboard 回归测试
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/base.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/InsightEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/graph.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/templates/index.html
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_engine_plans.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_dashboard.py
- 验证结果：
  - `uv run pytest tests/test_engine_plans.py tests/test_query_engine.py tests/test_media_engine.py tests/test_dashboard.py tests/test_workflow.py -q`：39 passed
- 当前保守结论：
  - 默认异步任务现在必须经过用户确认计划后才会执行采集；旧同步 `/tasks` 仍可完成端到端回归。

### 阶段 39：verified 任务计划进度收口修复
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 修复已 verified 任务前端仍显示部分计划项 `insufficient` 的问题
  - 后端在任务成功 verified 持久化前，将三路 `agent_plans` 的计划项统一收口为 `completed`
  - 前端在 successful terminal 状态下优先展示计划项完成态，避免旧执行日志覆盖最终状态
  - 补充 workflow 回归断言，确认 verified 响应中的三路计划项均为 completed
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `node --check knowledgeforge/static/js/dashboard.js`：通过
  - `uv run pytest tests/test_workflow.py::test_task_workflow_writes_markdown tests/test_dashboard.py tests/test_engine_plans.py -q`：6 passed
- 当前保守结论：
  - verified 任务结束后，“计划进度”应显示全部完成，不再混入采集过程中的临时不足状态。

### 阶段 40：查询计划不足门禁与主文档可读性修复
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 将 QueryEngine `query_question_completed: insufficient` 纳入完整性评估门禁
  - 当查询计划存在未完成项时，任务进入 `supplement_required`，不再继续生成 verified 文档
  - 优化 QueryEngine fallback plan，将常见中文子主题映射为英文检索 topic，减少中英混杂 query 空命中
  - 主知识文档不再展开完整 QueryEngine 查询计划清单，只保留摘要并引用独立 query plan 文档
  - 离线 `_NoopQueryCrawler` 改为返回稳定 fixture 命中，避免测试环境因关闭 live crawler 被误判为真实失败
  - 补充完整性、QueryEngine fallback 和 Writer 可读性回归测试
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/evaluation/completeness.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/storage/markdown_writer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_completeness_source_gate.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_query_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_writer_dynamic_status.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_workflow.py tests/test_completeness_source_gate.py tests/test_query_engine.py tests/test_writer_dynamic_status.py -q`：40 passed
- 当前保守结论：
  - 后续如果 Q4/Q5 仍为 insufficient，任务会停在补检索状态；不会再产出“看似完成但无有效信息”的 verified 文档。

### 阶段 41：计划阶段取消规则 fallback
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - QueryEngine / MediaEngine 计划生成不再回退到规则计划；LLM 缺失、超时或返回无效结构会直接失败
  - InsightEngine 计划生成改为 LLM 生成，不再使用本地规则计划
  - TaskService 捕获计划阶段异常，将任务保存为 `plan_failed`
  - 计划失败时写入 `agent_plan_failed` audit log 与 blocked workflow step，前端摘要区通过 `current_action` 展示失败原因
  - 前端将 `plan_failed` 识别为终态，避免继续轮询
  - 测试层用 fake OpenAI-compatible chat 保持服务级回归稳定，同时验证真实代码路径仍走 LLM plan 接口
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/InsightEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/graph.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/conftest.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_engine_plans.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
- 验证结果：
  - `node --check knowledgeforge/static/js/dashboard.js`：通过
  - `uv run pytest -q`：98 passed
- 当前保守结论：
  - 计划阶段现在只有 LLM 成功这一条路径；失败会提前结束并在前端和日志中明确显示。

### 阶段 42：计划阶段 LLM 超时配置化
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 将计划阶段 LLM timeout 从硬编码 1.5 秒改为 `PLAN_LLM_TIMEOUT`
  - 默认计划超时调整为 15 秒，降低 InsightEngine planning 因短超时失败的概率
  - `/config/status` runtime 分组展示 `plan_llm_timeout`
  - 保留 LLM 失败即 `plan_failed` 的行为，不恢复规则 fallback
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/config.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_dashboard.py tests/test_workflow.py::test_async_task_stops_when_llm_plan_generation_fails -q`：3 passed
  - `uv run pytest -q`：98 passed
- 当前保守结论：
  - 如果 LLM 45 秒内仍超时，任务仍会 `plan_failed` 并提示；可通过 `.env` 设置 `PLAN_LLM_TIMEOUT=60` 继续放宽。

### 阶段 43：计划阶段 LLM 并发超时修复
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 排查 task `7b709b0f8e1443e2a8c11cc6a549e285`，确认 InsightEngine 在 15 秒 planning timeout 后失败
  - 将三路计划生成从并发 LLM 调用改为按 Insight / Query / Media 顺序调用
  - 每路计划开始时写入 workflow step，便于前端和 logs 看到当前卡在哪个 Agent
  - 默认 `PLAN_LLM_TIMEOUT` 从 15 秒放宽到 45 秒，减少本地模型排队或首 token 慢导致的误失败
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/graph.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/config.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_workflow.py::test_async_task_stops_when_llm_plan_generation_fails tests/test_engine_plans.py tests/test_dashboard.py -q`：8 passed
  - `uv run pytest -q`：98 passed
- 当前保守结论：
  - LLM-only 行为不变；修复点是避免三路同时压同一个 LLM 服务导致排队超时。

### 阶段 44：MediaEngine 计划超时客户端修复
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 排查前端 `MediaEngine plan generation failed: timed out`，确认 MediaEngine 计划阶段仍误用 `execution_chat_client`
  - 为 `MediaEngine` 增加 `planning_chat_client` 注入，计划与领域归一化使用计划阶段 timeout
  - `TaskService` 注入 MediaEngine 时同时传入 execution client 与 planning client，保持执行阶段短超时策略不变
  - 增加回归测试，确保 `MediaEngine.plan()` 不会误用 execution chat client
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_media_engine.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_media_engine.py::test_media_engine_plan_uses_planning_chat_client tests/test_workflow.py::test_async_task_stops_when_llm_plan_generation_fails -q`：2 passed
  - `uv run pytest -q`：99 passed
- 当前保守结论：
  - MediaEngine 计划失败不应再由 5 秒 execution timeout 触发；如果 LLM 在 `PLAN_LLM_TIMEOUT` 内仍失败，仍按 LLM-only 规则进入 `plan_failed`。

### 阶段 45：基于实时知识 index 的补充决策优化
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 新增 `SupplementDecisionPlanner`，读取 `save/{领域}/README.md`、`*-query.md` 和领域下已保存 Markdown 内容作为实时知识 index 上下文
  - 在完整性不足时调用 LLM 分析缺陷，生成 QueryEngine 专用补检索计划；LLM 不可用时回退到基于完整性结果的规则决策
  - 将 LangGraph 的不完整分支改为“补充决策 -> QueryEngine 定向补采 -> 重新完整性评估”，并保留最大轮次保护
  - 将补充决策写入 `CompletenessResult.supplement_decision`，通过后仍保留决策审计信息
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/evaluation/supplement_decision.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/graph.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/models.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_supplement_decision.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
- 验证结果：
  - `uv run pytest tests/test_supplement_decision.py tests/test_completeness_source_gate.py tests/test_engine_plans.py`：12 passed
- 当前保守结论：
  - 补充模块现在不再只依赖静态规则 query；它会优先读取实时保存的领域 index，并把 LLM 判断出的缺陷分发给 QueryEngine 做权威事实补采。

### 阶段 46：Query / Media 计划去重与生成计划落盘
- **状态：** complete
- **开始时间：** 2026-04-26
- 执行的操作：
  - QueryEngine 计划生成与批准计划执行前增加标准化去重，避免重复问题/重复 query 出现在确认页面
  - MediaEngine 按平台类型和 query 去重，并在执行日志中写入稳定 `plan_item_id`
  - Markdown Writer 新增 `write_agent_plan_documents`，在计划生成阶段把 Agent 计划保存为 `doc_type=note`、`source_type=agent_plan` 文档
  - Workflow 在三路计划生成后立即保存计划文档，并把 `plan_document_paths` 写入任务状态和 workflow event
  - 前端计划卡片合并增加去重与 attempts/saved_paths 合并，避免 `agent_plans` 与执行日志回填重复展示
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/QueryEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/agent.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/agent/MediaEngine/nodes/search_node.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/storage/markdown_writer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/graph.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/orchestrator/state.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_engine_plans.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_writer_dynamic_status.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_engine_plans.py tests/test_writer_dynamic_status.py tests/test_workflow.py tests/test_dashboard.py`：40 passed
  - `uv run pytest`：107 passed
- 当前保守结论：
  - 等待确认阶段现在会在 `save/{领域}/{子领域}` 看到生成计划文档；Query / Media 的重复计划项会在生成、执行转换和页面合并三层被抑制。

### 阶段 47：计划项编辑后同步 Markdown 计划文档
- **状态：** complete
- **开始时间：** 2026-04-26
- 执行的操作：
  - 确认 `PATCH /tasks/{task_id}/plan/items/{agent}/{item}` 此前只更新 task state 与 audit，不会重写已生成的 `*-plan.md`
  - 为 `MarkdownKnowledgeWriter` 增加单个计划文档重写入口，复用生成计划文档的格式规范
  - `TaskService.update_plan_item()` 与 `delete_plan_item()` 在状态变更后同步重写 `plan_document_paths[agent]` 指向的 Markdown 文件
  - 同步失败时记录 `plan_document_sync_failed` audit 事件，避免静默丢失文件写入问题
  - 增加回归测试覆盖 MediaEngine 计划项 PATCH 与 QueryEngine 计划项 DELETE 后的 md 文件同步
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/storage/markdown_writer.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/services/task_service.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_workflow.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `uv run pytest tests/test_workflow.py::test_plan_item_patch_updates_saved_plan_markdown tests/test_workflow.py::test_plan_item_delete_updates_saved_plan_markdown tests/test_writer_dynamic_status.py::test_writer_saves_generated_query_and_media_plan_documents -q`：3 passed
  - `python -m py_compile knowledgeforge/services/task_service.py knowledgeforge/storage/markdown_writer.py`：通过
  - `uv run pytest`：109 passed
- 当前保守结论：
  - 等待确认阶段编辑或删除计划项后，对应 `save/{领域}/{子领域}/*-plan.md` 会同步更新；如果用户仍看到旧内容，优先检查是否打开了修改前生成的旧计划文件或浏览器/编辑器缓存。

### 阶段 41：前端实时流程图 X6 优化
- **状态：** complete
- **开始时间：** 2026-04-25
- 执行的操作：
  - 参考 AntV X6 官方快速上手，用 UMD 脚本引入 `@antv/x6`
  - 将首页 Flow Map 默认展开，并增加 X6 画布、状态图例和实时流程节点/边渲染
  - 前端继续复用 `WorkflowStepEvent`，由 `planning -> awaiting_confirmation -> collecting -> evaluating -> writing -> governing -> versioning` 生成 X6 JSON 数据
  - 保留原 HTML 流程卡片作为 X6 未加载时的回退展示
  - 补充 dashboard 页面回归断言，确认 X6 容器和脚本已输出
  - 本地 Playwright 检查发现 unpkg 被 ORB 拦截，已切换到 X6 官方文档同样列出的 jsDelivr CDN
  - 去掉 X6 `autoResize`，改为手动按容器宽高 resize，避免画布把首页撑高
- 创建/修改的文件：
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/templates/index.html
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/js/dashboard.js
  - /Users/lpb/workspace/myProjects/KnowledgeForge/knowledgeforge/static/css/dashboard.css
  - /Users/lpb/workspace/myProjects/KnowledgeForge/tests/test_dashboard.py
  - /Users/lpb/workspace/myProjects/KnowledgeForge/task_plan.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/findings.md
  - /Users/lpb/workspace/myProjects/KnowledgeForge/progress.md
- 验证结果：
  - `node --check knowledgeforge/static/js/dashboard.js`：通过
  - `uv run pytest tests/test_dashboard.py -q`：2 passed
  - `uv run pytest tests/test_dashboard.py tests/test_workflow.py -q`：26 passed
  - Playwright 桌面检查：`hasX6=true`，7 个节点、6 条边，回退卡片隐藏，画布高度 336px
  - Playwright 移动检查：7 个节点、6 条边，画布宽 272px、高 756px，无横向溢出
- 当前保守结论：
  - 首页实时流程图已由 X6 负责主展示，状态仍来自现有 workflow events，不改变后端执行链路。

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 阶段 35 已完成；配置状态已展示更完整的 provider、模型和运行配置 |
| 我要去哪里？ | 继续收敛真实联网抓取稳定性、query planning 超时治理、官方来源验证和 Media 观点源质量 |
| 目标是什么？ | 在不改写阶段 1-8 基线的前提下，进一步提升真实查询成功率，并保证弱来源不能进入冻结或报告流程 |
| 我学到了什么？ | 见 findings.md |
| 我做了什么？ | 见上方记录 |

---
*每个阶段完成后或遇到错误时更新此文件*
