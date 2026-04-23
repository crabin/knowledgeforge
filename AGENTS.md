# KnowledgeForge

## Source of Truth

When working in this repository, follow these documents first:

1. `docs/项目需求.md`
2. `docs/知识文档格式规范.md`
3. `docs/流程执行文档.md`

If implementation details conflict, prefer the product requirement and document-format rules.

## Project Scope

This project builds a domain knowledge engineering system with these current constraints:

- Web interface: Flask
- Workflow orchestration: LangGraph
- Document parsing: `marker-pdf`
- Primary storage: local Markdown files organized by domain / subdomain / article
- Graph storage: Neo4j, aligned with local file paths
- ChromaDB: reserved for later phases, not a required dependency in the main flow unless the user explicitly expands scope

## Architecture Constraints

Do not break these core capabilities:

- parallel collection by Insight / Query / Media agents
- state persistence and resume support
- stable local file storage and path association
- source traceability and quality-feedback loop

Use this storage pattern unless the user changes the requirement:

- `save/{领域名称}/README.md`
- `save/{领域名称}/{子领域名称}/{文档文件名}.md`

## Agent Creation Architecture

When creating or refactoring agents, follow `docs/design-paradigms/agent-architecture.md` as the architecture guide.

Prefer capability-domain Engines over loosely scoped Agent classes:

- `MediaEngine`: media parsing, extraction, conversion, summarization, and source material handling
- `InsightEngine`: analysis, synthesis, report structure, entity/relation extraction, and quality judgment
- `QueryEngine`: retrieval, Q&A, knowledge lookup, and result integration

Use an upper-layer Router / Orchestrator to choose the target Engine. Engines should not directly depend on each other.

Each Engine should keep a complete internal structure when the feature is non-trivial:

```text
agent/
  MediaEngine/
    agent.py
    nodes/
    llms/
    prompts/
    state/
    tools/
    utils/
  InsightEngine/
    agent.py
    nodes/
    llms/
    prompts/
    state/
    tools/
    utils/
  QueryEngine/
    agent.py
    nodes/
    llms/
    prompts/
    state/
    tools/
    utils/
```

Keep responsibilities separated:

- Engine: domain capability orchestration and public entry point, such as `run(...)`, `process(...)`, or `execute(...)`
- Nodes: single-purpose workflow steps that can be composed in LangGraph or another state graph
- LLMs: model clients, model configuration, retry/fallback policy, and structured-output adapters
- Prompts: prompt templates and prompt assembly logic
- State: typed state, message models, persistence and resume-related schemas
- Tools: external tool integrations and side-effecting operations
- Utils: stateless helpers only; do not put workflow decisions or orchestration in utils

For common agent behavior:

- Define a shared base interface where useful, such as `process(user_input, **kwargs) -> str` or an Engine-specific equivalent.
- Standardize messages with a typed model such as `AgentMessage(role, content, metadata)`; keep `role` constrained to `user`, `assistant`, or `system`.
- Keep conversation history separate from long-term memory.
- Route lightweight Q&A separately from planning / tool execution flows.
- Keep Planner, Core executor, and Summary responsibilities distinct when the workflow needs them.
- Use typed route results such as `Literal["qa", "technical"]` or project-specific equivalents.
- Use a factory or registry such as `get_engine(engine_type)` / `get_agent(agent_type)` with lazy loading and caching.
- Inject dependencies such as audit logging, memory, Neo4j clients, LLM clients, and tool registries through constructors or factories so tests can replace them.

Do not add ChromaDB, new storage backends, or cross-Engine shared abstractions while creating agents unless the task explicitly requires that scope.

## Working Rules

For non-trivial implementation work in this repo:

1. Use `superpowers:brainstorm` or `planning-with-files-zh` to clarify the approach.
2. Use `superpowers:write-plan` before editing multiple files or changing behavior.
3. Execute the approved approach with `superpowers:execute-plan`.
4. Before claiming completion, run `superpowers:verification-before-completion`.
5. After meaningful code changes, use `superpowers:requesting-code-review`.

## Domain Document Rules

Knowledge documents should stay traceable to source, agent, round, timestamp, and local path.

Do not save article content as only a final summary. Preserve original material or traceable citations.

If a task touches knowledge documents, ensure the output remains compatible with `docs/知识文档格式规范.md`.

## Data Responsibilities

Treat responsibilities this way unless the user says otherwise:

- Local files: authoritative storage for domain, subdomain, article, and index documents
- Neo4j: graph nodes and relationships for Domain, SubTopic, Article, entities, and path-linked metadata
- ChromaDB: placeholder only in the current phase

## Quality Loop

When quality checks fail, distinguish between:

- repair flow: extraction errors, metadata gaps, entity/relation issues
- re-search flow: weak evidence, weak sources, broken citations, unresolved conflicts

Never return a generic "failed" result without classifying the problem.

# [KnowledgeForge] recent context, 2026-04-23 11:54pm GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 2:16am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 2:14am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 2:10am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 2:07am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 2:06am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 2:03am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 2:02am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 2:01am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 1:58am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 1:58am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 1:57am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 1:50am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 1:47am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 1:46am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 1:45am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 1:44am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 12:15am GMT+9

No previous sessions found.
</claude-mem-context>


<claude-mem-context>
# Memory Context

# [KnowledgeForge] recent context, 2026-04-24 12:11am GMT+9

No previous sessions found.
</claude-mem-context>
