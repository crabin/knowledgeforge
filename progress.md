# Progress

## 2026-04-27

- 完成 QueryEngine 文章级采集计划升级。
- 将 Query 计划项从笼统查询问题扩展为可序列化的文章级条目，支持 `url`、`subdomain`、`doc_type`、`planned_path` 等元数据。
- 在 Query 计划阶段加入轻量候选检索，确认前即可得到链接级采集计划；已有 URL 会在计划中标记为 `skipped`。
- 将 Query 执行流改为按 URL 抓取并按“一链接一文档”实时落盘，保留来源、计划项、路径、状态与索引同步信息。
- 新增子领域 `README.md` 索引刷新，并保留领域级 `README.md` 总索引。
- 调整最终 mixed 汇总文档，使 Query 部分优先聚合已保存的文章级文档，而不是把原始查询计划当主载体。

## Verification

- 运行 `PYTHONPATH=. pytest -q`
- 结果：`121 passed`

## Follow-up

- 当前只升级了 QueryEngine 的文章级采集与索引链路，MediaEngine 仍保持原有实时资料保存模式。
- 补检索决策已能读取领域 README、子领域 README 与已保存文章概览；若后续需要“补检索确认前也必须显式展示 URL 级计划”，可继续把 supplement planner 扩展为预检索链接生成器。
