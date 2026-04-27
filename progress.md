# Progress

## 2026-04-27

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

## Verification

- 运行 `PYTHONPATH=. pytest -q`
- 结果：`121 passed`
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
