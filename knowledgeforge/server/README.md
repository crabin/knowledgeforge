# KnowledgeForge Server Structure

`knowledgeforge/server` is the backend boundary for the Flask application and all supporting server-side code. The package keeps the web app entry point, workflow orchestration, runtime state, persistence adapters, quality gates, and document completion services together so `knowledgeforge/` only exposes three product areas: `agent`, `server`, and `web`.

## Responsibilities

- `api.py`: Flask application factory, HTTP routes, SSE responses, and request logging.
- `services/`: application services that coordinate user actions, task lifecycle, background execution, and API-facing use cases.
- `orchestrator/`: LangGraph workflow state and graph execution for structure generation, review, evidence filling, governance, and document completion.
- `intake/`: intent recognition, domain normalization, and request context construction.
- `runtime/`: task state, audit logs, token usage, queues, frozen versions, and resume-related local stores.
- `storage/`: local Markdown writing and realtime file review for the optional document completion path.
- `graph/`: Neo4j client and path mapping adapters.
- `quality/`, `evaluation/`, `postprocess/`, `versioning/`, `reporting/`: governance, completeness, extraction, version recording, and report generation.
- `llms/`: model clients, model configuration, token tracking hooks, and provider adapters.
- `tools/`: backend-owned external integrations used by engines or services.
- `utils/`: stateless helpers for paths, time, contracts, knowledge trees, query normalization, and structure graph normalization.
- `config.py` and `models.py`: typed configuration and shared server-side data contracts.

## Boundary

`knowledgeforge/agent` keeps the capability-domain Engines (`MediaEngine`, `InsightEngine`, `QueryEngine`). Engines may import server contracts and backend-owned integrations from `knowledgeforge.server.*`, but backend orchestration should choose and call engines from the upper `server` layer rather than making Engines depend on each other.
