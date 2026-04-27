# Progress

## 2026-04-27

### Completed

- 补强补检索决策链路：在 `SupplementDecisionPlanner` 中读取 `save/{领域}` 下的 `README.md` 和历史 Markdown 文档摘要，由 LLM 基于“已保存文档概述”判断知识缺口并生成 QueryEngine 补充计划。
- 将文档审阅结果写入 `CompletenessResult.supplement_decision`，保留 `coverage_summary`、`reviewed_documents`、`defects` 和索引路径，便于审计与前端展示。
- 在补检索节点补充运行中状态与事件说明，前端计划面板新增“补检索分析”卡片和摘要栏提示，实时展示已审阅文档数量与识别出的缺口。
- 为补检索文档审阅与工作流串联增加回归测试，覆盖历史 Markdown 文档进入 LLM 输入、补检索计划生成及状态保留。
- 将 QueryEngine / MediaEngine 的网络查询接入共享检索任务队列，统一以 `network_query_and_optional_llm_summary` 任务类型执行。
- 引入全局 `RetrievalTaskQueue`，支持网络任务并发上限控制，并为可选 LLM 后处理预留独立并发配置。
- 集成 `crawl4ai` 作为正文抓取优先通道；失败后自动回退到现有 `AgentBrowserCLI` 与 `httpx` 抓取链路。
- 为配置层新增任务队列与 Crawl4AI 开关、并发与超时配置。
- 修复 `AppConfig.from_env(...)` 在显式传入 `.env` 文件时不会覆盖已有环境变量的问题。

### Verification

- `PYTHONPATH=. pytest -q tests/test_supplement_decision.py tests/test_dashboard.py`
- `python -m py_compile knowledgeforge/evaluation/supplement_decision.py knowledgeforge/orchestrator/graph.py knowledgeforge/services/task_service.py`
- `uv run pytest tests/test_task_queue.py tests/test_browser_fallbacks.py tests/test_query_engine.py tests/test_media_engine.py`
- `uv run pytest tests/test_workflow.py tests/test_integration_layers.py tests/test_dashboard.py`
- `uv run pytest`

### Follow-up

- 如果后续要把“补检索分析”做成更强实时推送，可以在当前轮询基础上再补 SSE 或 WebSocket；这次改动先复用现有任务快照轮询机制。
- 如需在生产环境真正启用 Crawl4AI 浏览器抓取，建议补跑 `crawl4ai-setup` / `crawl4ai-doctor`，确认本机 Playwright 依赖完整。
- 当前队列已把“网络查询 + 可选 LLM 后处理”统一为同一任务模型；如果后续要细化 LLM 总结阶段的限流策略，可直接复用现有 `max_llm_task_concurrency` 配置。
