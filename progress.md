# Progress

## 2026-04-27

### Completed

- 将 QueryEngine / MediaEngine 的网络查询接入共享检索任务队列，统一以 `network_query_and_optional_llm_summary` 任务类型执行。
- 引入全局 `RetrievalTaskQueue`，支持网络任务并发上限控制，并为可选 LLM 后处理预留独立并发配置。
- 集成 `crawl4ai` 作为正文抓取优先通道；失败后自动回退到现有 `AgentBrowserCLI` 与 `httpx` 抓取链路。
- 为配置层新增任务队列与 Crawl4AI 开关、并发与超时配置。
- 修复 `AppConfig.from_env(...)` 在显式传入 `.env` 文件时不会覆盖已有环境变量的问题。

### Verification

- `uv run pytest tests/test_task_queue.py tests/test_browser_fallbacks.py tests/test_query_engine.py tests/test_media_engine.py`
- `uv run pytest tests/test_workflow.py tests/test_integration_layers.py tests/test_dashboard.py`
- `uv run pytest`

### Follow-up

- 如需在生产环境真正启用 Crawl4AI 浏览器抓取，建议补跑 `crawl4ai-setup` / `crawl4ai-doctor`，确认本机 Playwright 依赖完整。
- 当前队列已把“网络查询 + 可选 LLM 后处理”统一为同一任务模型；如果后续要细化 LLM 总结阶段的限流策略，可直接复用现有 `max_llm_task_concurrency` 配置。
