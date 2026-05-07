# KnowledgeForge

KnowledgeForge 是一个面向领域知识工程的知识库构建系统。当前真实代码流程以“先规划知识结构，再按文件生成和补证据”为主线：用户输入会先做真实意图识别和领域归一化，随后由 LangGraph 生成知识结构图谱、初始化 Neo4j 任务图、串行生成知识点 Markdown 文件、执行文件级证据队列，并在每条证据完成后即时回写目标文件和图谱状态。

项目当前遵循以下约束：

- Web 界面基于 `Flask`
- 工作流编排基于 `LangGraph`
- 本地知识文档按 `save/{领域名称}/{子领域名称}/{文档文件名}.md` 存储
- 领域目录包含 `save/{领域名称}/README.md` 和 `knowledge_task_queue.json`
- 图谱存储基于 `Neo4j`，并实时承载任务进度状态
- `ChromaDB` 仅作为后续阶段预留能力，不进入当前主流程

## 核心流程

1. 输入领域或描述，统一经过 intake 真实意图识别和领域归一化，例如 `DL` 会归一化为 `Deep Learning`。
2. LangGraph 生成领域知识结构图谱，并派生二级领域、知识点文件蓝图和保存路径。
3. Neo4j 前置同步结构图谱，结构节点初始为 `planned`。
4. 系统串行生成每个知识点 Markdown 文件；文件开始生成、落盘、待证据、完成等状态会同步到任务状态和 Neo4j。
5. 从每个文件的 contract 块提取 `query_tasks`，写入领域级 `knowledge_task_queue.json`。
6. Query / Media 按队列执行证据任务；每个任务完成后立即回写目标 Markdown、队列 JSON、图谱节点状态和 SSE payload。
7. 子节点状态变化后自动聚合父级 SubTopic / Domain 完成状态。
8. 最后执行治理链路：结构化抽取、Neo4j 路径关联、质量检测、版本冻结和可选研报。

更多设计说明见：

- [docs/项目需求.md](docs/项目需求.md)
- [docs/知识文档格式规范.md](docs/知识文档格式规范.md)
- [docs/流程执行文档.md](docs/流程执行文档.md)

## 快速启动

1. 安装依赖

```bash
uv sync
```

2. 准备环境变量

```bash
cp .env.example .env
```

3. 按需填写 `.env`

- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`
- `OPENAI_EMBEDDING_API_KEY` / `OPENAI_EMBEDDING_BASE_URL`
- `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`
- `MYSQL_DATABASE_URL`

4. 启动 Web 控制台

```bash
uv run python app.py
```

默认访问地址：

- [http://127.0.0.1:5001](http://127.0.0.1:5001)

## 界面截图

### 控制台总览

展示流程图、交互式输入、任务操作、生成与查询队列状态、Neo4j 实时知识图谱。

![KnowledgeForge 控制台总览](docs/images/homepage.png)

## 目录说明

- `knowledgeforge/server/`：Flask 后端入口与 API 路由
- `knowledgeforge/web/`：前端模板与静态资源
- `knowledgeforge/agent/`：`InsightEngine`、`QueryEngine`、`MediaEngine` 的能力实现
- `knowledgeforge/orchestrator/`：LangGraph 工作流和运行状态
- `knowledgeforge/graph/`：Neo4j 写入、状态同步和快照读取
- `knowledgeforge/storage/`：Markdown 写入、即时资料保存和 contract 回写
- `save/`：领域知识文档、README 索引和领域级任务队列
- `docs/`：需求、流程、格式规范与设计资料
- `tests/`：自动化测试

## 当前状态

项目当前已具备：

- intake 澄清会话和直接任务入口的统一意图识别
- 结构图谱生成、蓝图派生和 Neo4j 前置同步
- 串行知识点文件生成和文件级 contract
- Query / Media 文件级证据任务队列
- 每条证据完成后的 Markdown / 队列 / 图谱即时回写
- SSE 直接推送任务状态、图谱快照和文件回写事件
- 领域 README、子领域 README、实时资料索引刷新
- 结构化治理、质量检测、版本冻结和研报生成入口

