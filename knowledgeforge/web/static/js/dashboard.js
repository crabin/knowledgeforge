const state = {
  lastPayload: null,
  eventSource: null,
  pollTaskId: null,
  workflowGraph: null,
  workflowGraphReady: false,
  neo4jGraph: null,
  neo4jViz: null,
  neo4jGraphSnapshot: null,
  neo4jGraphRefreshTimer: null,
  neo4jAutoFollow: true,
  neo4jSelectedNodeId: "",
  neo4jIssueInspection: null,
  neo4jPendingFocusNodeId: "",
  neo4jShowCompressedEdges: false,
};

const output = document.querySelector("#response-output");
const summaryStrip = document.querySelector("#summary-strip");
const configGrid = document.querySelector("#config-grid");
const healthDot = document.querySelector("#health-dot");
const healthLabel = document.querySelector("#health-label");
const intakeSessionInput = document.querySelector("#intake-session-id");
const taskIdInput = document.querySelector("#task-id");
const taskUpdateInput = document.querySelector("#task-update-payload");
const queueOutput = document.querySelector("#agent-plan-output");
const queuePanelHint = document.querySelector("#plan-panel-hint");
const learningPlanOutput = document.querySelector("#learning-plan-output");
const tokenUsageOutput = document.querySelector("#token-usage-output");
const tokenFloat = document.querySelector("#token-float");
const tokenFloatToggle = document.querySelector("#token-float-toggle");
const tokenFloatTotal = document.querySelector("#token-float-total");
const executionLogOutput = document.querySelector("#execution-log-output");
const taskListOutput = document.querySelector("#task-list-output");
const workflowMap = document.querySelector("#workflow-map");
const workflowX6Container = document.querySelector("#workflow-x6");
const neo4jGraphContainer = document.querySelector("#neo4j-graph");
const neo4jGraphDot = document.querySelector("#neo4j-graph-dot");
const neo4jGraphStatusLabel = document.querySelector("#neo4j-graph-status-label");
const neo4jGraphMetrics = document.querySelector("#neo4j-graph-metrics");
const neo4jAutoFollowInput = document.querySelector("#neo4j-auto-follow");
const refreshNeo4jGraphButton = document.querySelector("#refresh-neo4j-graph");

const workflowSteps = [
  { id: "intent_recognition", order: "01", title: "意图识别", description: "识别真实领域意图并归一化缩写。" },
  { id: "structure_graph_planning", order: "02", title: "图谱生成", description: "根据用户意图生成知识架构图谱。" },
  { id: "neo4j_structure_sync", order: "03", title: "Neo4j呈现", description: "先将知识架构图谱同步到 Neo4j。" },
  { id: "structure_review", order: "04", title: "两段Review", description: "先审结构覆盖，再审执行准备度。" },
  { id: "graph_completion", order: "05", title: "图谱补全", description: "写入补全文档所需的图谱上下文。" },
  { id: "evidence_link_query", order: "06", title: "查询填充", description: "用户触发后联网补充可信证据。" },
  { id: "governing", order: "07", title: "治理质检", description: "抽取、Neo4j 路径关联、质量检测和回流分类。" },
  { id: "evidence_link_recorded", order: "08", title: "图谱证据写入", description: "写入证据链接、来源类型和 claim 到 Neo4j。", optional: false },
  { id: "document_completion", order: "09", title: "补全文档", description: "可选：验证后生成本地知识文档。", optional: true },
  { id: "versioning", order: "10", title: "版本研报", description: "可选：冻结版本并生成研报。", optional: true },
];

async function requestJson(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { raw: text };
    }
  }
  if (!response.ok) {
    const message = payload.error || `${response.status} ${response.statusText}`;
    const error = new Error(message);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function setBusy(formOrButton, busy) {
  const buttons = formOrButton.tagName === "BUTTON" ? [formOrButton] : formOrButton.querySelectorAll("button");
  buttons.forEach((button) => {
    button.disabled = busy;
  });
}

function showPayload(payload) {
  state.lastPayload = payload;
  output.textContent = JSON.stringify(payload, null, 2);
  syncKnownIds(payload);
  renderSummary(payload);
  renderWorkflowMap(payload);
  renderQueuePanel(payload);
  renderLearningPlan(payload);
  renderTokenUsage(payload);
  renderExecutionLog(payload);
  renderTaskList(payload);
}

function showError(error) {
  const payload = {
    error: error.message,
    status: error.status || "client_error",
    details: error.payload || null,
  };
  output.textContent = JSON.stringify(payload, null, 2);
  renderSummary(payload);
  renderWorkflowMap(payload);
  renderQueuePanel(payload);
  renderLearningPlan(payload);
  renderTokenUsage(payload);
  renderExecutionLog(payload);
  renderTaskList(payload);
}

function mergeTaskPayload(payload) {
  const base = state.lastPayload && (state.lastPayload.task_id === payload.task_id || state.lastPayload.task_id === payload.task?.task_id)
    ? state.lastPayload
    : {};
  return {
    ...base,
    ...payload,
    logs: payload.logs || base.logs,
    execution_log: payload.execution_log || base.execution_log,
    token_usage: payload.token_usage || base.token_usage,
  };
}

function syncKnownIds(payload) {
  const sessionId = payload.session_id || payload.intake_session?.session_id;
  const taskId = payload.task_id || payload.task?.task_id || payload.intake_session?.task_id;
  if (sessionId) intakeSessionInput.value = sessionId;
  if (taskId) taskIdInput.value = taskId;
}

function getNested(payload, path) {
  return path.split(".").reduce((value, key) => {
    if (value && Object.prototype.hasOwnProperty.call(value, key)) return value[key];
    return undefined;
  }, payload);
}

function renderSummary(payload) {
  if (!summaryStrip) return;
  const queueSummary = payload.queue_summary || {};
  const latestLlmDetails = payload.llm_activity?.latest_event?.details || {};
  const latestError = (payload.recent_errors || []).at(-1) || {};
  const items = [
    ["Task ID", payload.task_id || payload.task?.task_id || payload.intake_session?.task_id],
    ["Session ID", payload.session_id || payload.intake_session?.session_id],
    ["状态", payload.task_status || payload.status || payload.task?.task_status || payload.intake_session?.status],
    ["产出模式", formatCompletionMode(getNested(payload, "request_context.completion_mode") || getNested(payload, "task.request_context.completion_mode") || payload.completion_mode || payload.intake_session?.completion_mode)],
    ["补全文档", formatFullDocumentStatus(payload.document_completion_status || payload.full_document_status || payload.task?.document_completion_status || payload.task?.full_document_status)],
    ["补全文档数", summarizeDocumentCompletion(payload)],
    ["执行耗时", summarizeTaskTiming(payload)],
    ["当前步骤", payload.current_step || payload.task?.current_step],
    ["当前动作", payload.current_action || payload.task?.current_action],
    ["两段Review", summarizeStructureReview(payload)],
    ["生成进度", summarizeGenerationProgress(payload)],
    ["队列进度", summarizeQueueProgress(payload)],
    ["当前图谱节点", summarizeCurrentFile(payload)],
    ["当前链接任务", summarizeCurrentEvidenceTask(payload)],
    ["图谱完成", summarizeGraphCompletion(payload)],
    ["最近链接", payload.file_update?.selected_link || payload.file_update?.path],
    ["轮次验证", summarizeValidationRounds(payload)],
    ["队列状态", queueSummary.final_status],
    ["队列统计", summarizeQueueCountSummary(queueSummary.counts)],
    ["最新 LLM", summarizeLatestLlm(latestLlmDetails)],
    ["最近错误", latestError.error || latestError.event],
    ["治理摘要", getNested(payload, "document_artifact.path")],
    ["质量检查", getNested(payload, "post_storage_result.quality_check.status")],
    ["冻结版本", getNested(payload, "post_storage_result.version_record.version") || payload.version],
    ["研报资格", getNested(payload, "post_storage_result.version_record.report_eligible")],
    ["Token", summarizeTokenUsageLabel(payload)],
    ["日志文件", payload.log_files?.application_log],
    ["错误", payload.error],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");

  if (!items.length) {
    summaryStrip.innerHTML = '<div class="empty-state">暂无可提取的关键字段。</div>';
    return;
  }

  summaryStrip.innerHTML = items
    .map(([label, value]) => `<div class="summary-item"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(String(value))}</span></div>`)
    .join("");
}

function summarizeDocumentCompletion(payload) {
  const result = payload.document_completion_result || payload.task?.document_completion_result;
  if (!result) return "";
  const completed = Array.isArray(result.completed_files) ? result.completed_files.length : 0;
  const total = result.total_files ?? completed;
  return `${completed}/${total}`;
}

function formatCompletionMode(mode) {
  if (!mode) return "";
  return {
    framework: "Neo4j 图谱与证据",
    full_document: "Neo4j 图谱与证据",
    file_level: "Neo4j 图谱与证据",
  }[mode] || mode;
}

function formatFullDocumentStatus(status) {
  if (!status) return "";
  return {
    pending: "待生成",
    generated: "已生成",
    skipped: "按需后置",
  }[status] || status;
}

function summarizeStructureReview(payload) {
  const rounds = normalizeStructureReviewRounds(payload.structure_review_rounds || payload.task?.structure_review_rounds || []);
  if (!rounds.length) return "";
  const latest = rounds.at(-1) || {};
  const status = latest.status || (latest.is_complete ? "passed" : "needs_repair");
  const label = formatStructureReviewType(latest.review_type || (rounds.length === 1 ? "structure_coverage" : "completion_readiness"));
  return `${rounds.length}/2 · ${label} · ${status === "passed" ? "通过" : "需修补"}`;
}

function formatStructureReviewType(type) {
  return {
    structure_coverage: "结构覆盖",
    completion_readiness: "准备度",
  }[type] || "Review";
}

function normalizeStructureReviewRounds(rounds) {
  if (!Array.isArray(rounds)) return [];
  const byRound = new Map();
  rounds.forEach((round, index) => {
    const roundNumber = Number(round?.round || index + 1);
    if ([1, 2].includes(roundNumber)) byRound.set(roundNumber, round);
  });
  return [...byRound.entries()].sort(([left], [right]) => left - right).map(([, round]) => round);
}

function renderConfig(payload) {
  if (!configGrid) return;
  const entries = Object.entries(payload);
  if (!entries.length) {
    configGrid.innerHTML = '<div class="empty-state">未返回配置状态。</div>';
    return;
  }
  configGrid.innerHTML = entries
    .filter(([key]) => key !== "legacy")
    .map(([key, value]) => renderConfigGroup(key, value))
    .join("");
}

function renderConfigGroup(key, value) {
  const label = formatConfigLabel(key);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return `<div class="config-item"><strong>${escapeHtml(label)}</strong>${renderConfigValue(value)}</div>`;
  }
  const rows = flattenConfig(value)
    .map(([itemKey, itemValue]) => `<div class="config-row"><span>${escapeHtml(formatConfigLabel(itemKey))}</span>${renderConfigValue(itemValue)}</div>`)
    .join("");
  return `<div class="config-item config-group"><strong>${escapeHtml(label)}</strong>${rows}</div>`;
}

function flattenConfig(value, prefix = "") {
  const rows = [];
  Object.entries(value).forEach(([key, item]) => {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (item && typeof item === "object" && !Array.isArray(item)) rows.push(...flattenConfig(item, nextKey));
    else rows.push([nextKey, item]);
  });
  return rows;
}

function renderConfigValue(value) {
  if (typeof value === "boolean") return `<span class="${value ? "tone-ok" : "tone-bad"}">${value ? "是" : "否"}</span>`;
  if (Array.isArray(value)) return `<span>${escapeHtml(value.join(", "))}</span>`;
  return `<span>${escapeHtml(value ?? "")}</span>`;
}

function formatConfigLabel(key) {
  const labels = {
    llm: "LLM",
    storage: "存储",
    retrieval: "检索",
    graph: "图谱",
    database: "数据库",
    runtime: "运行时",
    "chat.configured": "Chat 已配置",
    "chat.provider_family": "Chat Provider",
    "chat.model": "Chat 模型",
    "chat.base_url": "Chat API",
    "chat.api_key_present": "Chat Key",
    "embedding.configured": "Embedding 已配置",
    "embedding.provider_family": "Embedding Provider",
    "embedding.model": "Embedding 模型",
    "embedding.base_url": "Embedding API",
    "embedding.dimensions": "Embedding 维度",
    "embedding.api_key_present": "Embedding Key",
  };
  return labels[key] || String(key).replaceAll("_", " ").replaceAll(".", " / ");
}

function normalizeWorkflowEvents(payload) {
  const taskEvents = payload.workflow_events || payload.task?.workflow_events || [];
  const logs = payload.logs || payload.execution_log || payload.task?.execution_log || [];
  const logEvents = logs.filter((entry) => entry.event === "workflow_step").map((entry) => entry.details || {});
  return [...taskEvents, ...logEvents].filter((event) => event.step_id);
}

function getCurrentWorkflowStep(payload, events) {
  const explicitStep = normalizeWorkflowStepId(payload.current_step || payload.task?.current_step || "");
  if (workflowSteps.some((step) => step.id === explicitStep)) return explicitStep;
  const latestEventStep = normalizeWorkflowStepId(events.at(-1)?.step_id || "");
  if (workflowSteps.some((step) => step.id === latestEventStep)) return latestEventStep;
  return "intent_recognition";
}

function normalizeWorkflowStepId(stepId) {
  const aliases = {
    structure_graph_ready: "structure_graph_planning",
    blueprint_ready: "structure_graph_planning",
    structure_repair: "structure_review",
    repair_structure_graph_round_1: "structure_review",
    repair_structure_graph_round_2: "structure_review",
    architecture_documents: "graph_completion",
    llm_generating: "graph_completion",
    query_queue_running: "evidence_link_query",
    evidence_realtime_write: "evidence_link_recorded",
    evidence_filling: "evidence_link_query",
    documents_completed: "document_completion",
    planning: "intent_recognition",
    awaiting_confirmation: "intent_recognition",
    collecting: "evidence_link_query",
    evaluating: "governing",
    writing: "graph_completion",
  };
  return aliases[stepId] || stepId;
}

function renderWorkflowMap(payload) {
  const events = normalizeWorkflowEvents(payload);
  const byStep = new Map(events.map((event) => [normalizeWorkflowStepId(event.step_id), { ...event, step_id: normalizeWorkflowStepId(event.step_id) }]));
  if ((payload.document_completion_status || payload.full_document_status || payload.task?.document_completion_status || payload.task?.full_document_status) === "generated") {
    byStep.set("document_completion", { step_id: "document_completion", status: "completed", label: "本地知识文档已补全" });
  }
  const current = getCurrentWorkflowStep(payload, events);
  renderWorkflowFallback(byStep, current, payload);
}

function initializeWorkflowMap() {
  renderWorkflowMap(state.lastPayload || {});
}

function renderWorkflowFallback(byStep, current, payload = {}) {
  if (!workflowMap) return;
  workflowMap.querySelectorAll("[data-step-id]").forEach((step) => {
    const stepId = step.dataset.stepId;
    const event = byStep.get(stepId);
    const status = getWorkflowStepStatus(stepId, byStep, current, payload);
    step.dataset.status = status;
    step.dataset.statusLabel = getWorkflowStatusLabel(status, stepId);
    step.setAttribute("aria-current", status === "active" ? "step" : "false");
    if (event?.label) step.setAttribute("title", event.label);
    step.classList.toggle("active", status === "active");
    step.classList.toggle("focused", status === "active");
    step.classList.toggle("done", status === "completed");
    step.classList.toggle("pending", status === "pending");
    step.classList.toggle("blocked", status === "blocked");
    step.classList.toggle("error", status === "error");
  });
}

function renderWorkflowX6(byStep, current) {
  const graph = ensureWorkflowGraph();
  if (!graph) return;
  const data = buildWorkflowGraphData(byStep, current);
  const width = workflowX6Container.clientWidth || 960;
  const height = data.meta?.height || workflowX6Container.clientHeight || 360;
  workflowX6Container.style.height = `${height}px`;
  graph.resize(width, height);
  graph.fromJSON(data);
  fitGraphToContainer(graph, workflowX6Container, 18, 1);
}

function ensureWorkflowGraph() {
  if (!workflowX6Container || !window.X6?.Graph) return null;
  if (state.workflowGraph) return state.workflowGraph;
  const { Graph } = window.X6;
  state.workflowGraph = new Graph({
    container: workflowX6Container,
    width: workflowX6Container.clientWidth || 960,
    height: workflowX6Container.clientHeight || 360,
    panning: false,
    mousewheel: false,
    interacting: {
      nodeMovable: false,
      edgeMovable: false,
      arrowheadMovable: false,
      vertexMovable: false,
      magnetConnectable: false,
    },
    background: { color: "#fffdf8" },
    grid: {
      size: 12,
      visible: true,
      type: "dot",
      args: { color: "rgba(23, 33, 31, 0.12)" },
    },
  });
  state.workflowGraphReady = true;
  document.body.classList.add("x6-flow-ready");
  return state.workflowGraph;
}

function buildWorkflowGraphData(byStep, current) {
  const width = workflowX6Container?.clientWidth || 960;
  const compact = width < 760;
  const nodeWidth = compact ? Math.max(220, width - 48) : Math.max(160, Math.floor((width - 48 - Math.max(0, workflowSteps.length - 1) * 22) / workflowSteps.length));
  const nodeHeight = compact ? 96 : 116;
  const startX = 24;
  const startY = 24;
  const gapX = compact ? 0 : 22;
  const gapY = compact ? 18 : 0;
  const nodes = workflowSteps.map((step, index) => {
    const position = compact
      ? { x: startX, y: startY + index * (nodeHeight + gapY) }
      : { x: startX + index * (nodeWidth + gapX), y: startY };
    const status = getWorkflowStepStatus(step.id, byStep, current);
    return {
      id: step.id,
      shape: "rect",
      x: position.x,
      y: position.y,
      width: nodeWidth,
      height: nodeHeight,
      ports: workflowNodePorts(compact),
      data: { status },
      markup: [
        { tagName: "rect", selector: "body" },
        { tagName: "text", selector: "order" },
        { tagName: "text", selector: "title" },
        { tagName: "text", selector: "description" },
      ],
      attrs: getWorkflowNodeAttrs(step, status),
    };
  });
  const edges = workflowSteps.slice(0, -1).map((step, index) => {
    const next = workflowSteps[index + 1];
    const sourceStatus = getWorkflowStepStatus(step.id, byStep, current);
    const targetStatus = getWorkflowStepStatus(next.id, byStep, current);
    const edgeStatus = targetStatus === "error" ? "error" : targetStatus === "blocked" ? "blocked" : sourceStatus === "completed" ? "completed" : targetStatus === "active" ? "active" : "pending";
    return {
      id: `${step.id}-${next.id}`,
      shape: "edge",
      source: { cell: step.id, port: compact ? "bottom" : "right" },
      target: { cell: next.id, port: compact ? "top" : "left" },
      connector: { name: "normal" },
      attrs: getWorkflowEdgeAttrs(edgeStatus),
    };
  });
  const height = compact
    ? startY * 2 + workflowSteps.length * nodeHeight + Math.max(0, workflowSteps.length - 1) * gapY
    : startY * 2 + nodeHeight;
  return { nodes, edges, meta: { height } };
}

function workflowNodePorts(compact) {
  return {
    groups: {
      left: { position: "left", attrs: { circle: { r: 0, magnet: false, stroke: "transparent", fill: "transparent" } } },
      right: { position: "right", attrs: { circle: { r: 0, magnet: false, stroke: "transparent", fill: "transparent" } } },
      top: { position: "top", attrs: { circle: { r: 0, magnet: false, stroke: "transparent", fill: "transparent" } } },
      bottom: { position: "bottom", attrs: { circle: { r: 0, magnet: false, stroke: "transparent", fill: "transparent" } } },
    },
    items: compact
      ? [{ id: "top", group: "top" }, { id: "bottom", group: "bottom" }]
      : [{ id: "left", group: "left" }, { id: "right", group: "right" }],
  };
}

function graphNodePorts() {
  return {
    groups: {
      top: { position: "top", attrs: { circle: { r: 0, magnet: false, stroke: "transparent", fill: "transparent" } } },
      bottom: { position: "bottom", attrs: { circle: { r: 0, magnet: false, stroke: "transparent", fill: "transparent" } } },
    },
    items: [{ id: "top", group: "top" }, { id: "bottom", group: "bottom" }],
  };
}

function fitGraphToContainer(graph, container, padding = 24, maxScale = 1) {
  if (!graph || !container) return;
  const width = container.clientWidth || 1;
  const height = container.clientHeight || 1;
  let bbox;
  try {
    bbox = graph.getContentBBox();
  } catch {
    graph.centerContent({ padding });
    return;
  }
  if (!bbox || !bbox.width || !bbox.height) {
    graph.centerContent({ padding });
    return;
  }
  const scale = Math.min(maxScale, (width - padding * 2) / bbox.width, (height - padding * 2) / bbox.height);
  graph.zoomTo(Math.max(0.18, scale));
  graph.centerContent({ padding });
}

function getWorkflowStepStatus(stepId, byStep, current, payload = {}) {
  const event = byStep.get(stepId);
  const taskStatus = payload.task_status || payload.task?.task_status || "";
  if (isWorkflowErrorStatus(event?.status)) return "error";
  if (stepId === current && isWorkflowErrorStatus(taskStatus)) return "error";
  if (event?.status === "blocked") return "blocked";
  if (event?.status === "completed") return "completed";
  if (stepId === current) return "active";
  if (stepId === "document_completion") {
    return (payload.document_completion_status || payload.full_document_status || payload.task?.document_completion_status || payload.task?.full_document_status) === "generated" ? "completed" : "pending";
  }
  if (stepId === "versioning") {
    const versionRecord = getNested(payload, "post_storage_result.version_record") || getNested(payload, "task.post_storage_result.version_record");
    if (versionRecord?.frozen || versionRecord?.report_eligible) return "completed";
    return "pending";
  }
  const stepIndex = workflowSteps.findIndex((step) => step.id === stepId);
  const currentIndex = workflowSteps.findIndex((step) => step.id === current);
  if (stepIndex >= 0 && currentIndex >= 0 && stepIndex < currentIndex) return "completed";
  return "pending";
}

function getWorkflowStatusLabel(status, stepId = "") {
  const step = workflowSteps.find((item) => item.id === stepId);
  if (status === "pending" && step?.optional) return "可选";
  return {
    completed: "已完成",
    active: "执行中",
    blocked: "需处理",
    error: "错误",
    pending: "待处理",
  }[status] || "待处理";
}

function isWorkflowErrorStatus(status) {
  return ["failed", "error", "errored", "plan_failed"].includes(String(status || "").toLowerCase());
}

function getWorkflowNodeAttrs(step, status) {
  const palette = {
    pending: { fill: "#fbf8ee", stroke: "#d8d1c2", title: "#17211f", meta: "#5d6a66" },
    active: { fill: "#edf6ee", stroke: "#1e7b64", title: "#17211f", meta: "#1e7b64" },
    completed: { fill: "#f1f8f2", stroke: "#1e7b64", title: "#17211f", meta: "#1e7b64" },
    blocked: { fill: "#fff7e8", stroke: "#bb8b27", title: "#17211f", meta: "#9b6f12" },
    error: { fill: "#fff0ee", stroke: "#a9483f", title: "#17211f", meta: "#a9483f" },
  }[status] || {};
  return {
    body: {
      rx: 8,
      ry: 8,
      fill: palette.fill,
      stroke: palette.stroke,
      strokeWidth: status === "active" ? 3 : 1.5,
      filter: status === "active" ? "drop-shadow(0 8px 14px rgba(30, 123, 100, 0.18))" : "none",
    },
    order: {
      text: step.order,
      fill: palette.meta,
      fontSize: 12,
      fontWeight: 900,
      refX: 16,
      refY: 16,
      textAnchor: "start",
      textVerticalAnchor: "top",
    },
    title: {
      text: step.title,
      fill: palette.title,
      fontSize: 15,
      fontWeight: 800,
      lineHeight: 20,
      refX: 16,
      refY: 36,
      refWidth: -32,
      textAnchor: "start",
      textVerticalAnchor: "top",
      textWrap: { width: -32, height: 34, ellipsis: true },
    },
    description: {
      text: step.description,
      fill: palette.meta,
      fontSize: 12,
      fontWeight: 600,
      lineHeight: 17,
      refX: 16,
      refY: 64,
      refWidth: -32,
      textAnchor: "start",
      textVerticalAnchor: "top",
      textWrap: { width: -32, height: 40, ellipsis: true },
    },
  };
}

function getWorkflowEdgeAttrs(status) {
  const color = { pending: "#d8d1c2", active: "#2f5f91", completed: "#1e7b64", blocked: "#bb8b27", error: "#a9483f" }[status] || "#d8d1c2";
  return {
    line: {
      stroke: color,
      strokeWidth: status === "active" ? 3 : 2,
      targetMarker: { name: "classic", size: 8 },
      strokeDasharray: status === "pending" ? "6 5" : "",
    },
  };
}

function getTaskIdFromPayload(payload = {}) {
  payload = payload && typeof payload === "object" ? payload : {};
  return payload.task_id || payload.task?.task_id || payload.intake_session?.task_id || taskIdInput?.value?.trim() || "";
}

function scheduleNeo4jGraphRefresh(taskId, options = {}) {
  if (!neo4jGraphContainer || !taskId) return;
  if (!options.force && !state.neo4jAutoFollow) return;
  if (state.neo4jGraphRefreshTimer) return;
  const delay = options.force ? 0 : 900;
  state.neo4jGraphRefreshTimer = window.setTimeout(() => {
    state.neo4jGraphRefreshTimer = null;
    refreshNeo4jGraph(taskId, { force: options.force });
  }, delay);
}

function normalizeGraphPayload(graph) {
  const source = graph && typeof graph === "object" && !Array.isArray(graph) ? graph : {};
  const nested = source.graph && typeof source.graph === "object" && !Array.isArray(source.graph) ? source.graph : source;
  return {
    nodes: Array.isArray(nested.nodes) ? nested.nodes : [],
    edges: Array.isArray(nested.edges) ? nested.edges : [],
  };
}

function hasGraphPayload(graph) {
  const normalized = normalizeGraphPayload(graph);
  return Boolean(normalized.nodes.length || normalized.edges.length);
}

async function refreshNeo4jGraph(taskId = getTaskIdFromPayload(state.lastPayload), options = {}) {
  if (!neo4jGraphContainer) return;
  if (!taskId) {
    setNeo4jGraphStatus("idle", "等待任务");
    renderNeo4jGraphMetrics({ domain: "暂无", graph: { nodes: [], edges: [] } });
    renderNeo4jGraphFallback("选择或启动任务后显示当前领域的 Neo4j 图谱");
    return;
  }
  if (!options.silent) setNeo4jGraphStatus("loading", "读取 Neo4j");
  try {
    const payload = await requestJson(`/tasks/${encodeURIComponent(taskId)}/graph`);
    renderNeo4jGraphSnapshot(payload, state.neo4jGraphSnapshot);
    state.neo4jGraphSnapshot = payload;
  } catch (error) {
    setNeo4jGraphStatus("unavailable", "读取失败");
    renderNeo4jGraphMetrics({ domain: "暂无", graph: { nodes: [], edges: [] } });
    renderNeo4jGraphFallback(`Neo4j 图谱读取失败：${error.message}`);
  }
}

function renderNeo4jGraphSnapshot(payload, previousPayload) {
  const graph = normalizeGraphPayload(payload.graph || payload.graph_snapshot);
  renderNeo4jGraphMetrics(payload);
  if (payload.status === "ok" || payload.status === "local" || payload.graph_snapshot) {
    setNeo4jGraphStatus("ok", graph.nodes.length ? "已连接" : "无图谱数据");
  } else {
    setNeo4jGraphStatus("unavailable", payload.error || "Neo4j 不可用");
  }
  renderNeo4jGraphHtml(graph, payload, previousPayload);
}

function renderNeo4jGraphHtml(graph, payload, previousPayload) {
  if (!neo4jGraphContainer) return;
  const previousGraph = normalizeGraphPayload(previousPayload?.graph || previousPayload?.graph_snapshot);
  const previousNodeIds = new Set(previousGraph.nodes.map((node) => node.id));
  const previousEdgeIds = new Set(previousGraph.edges.map((edge) => edge.id));
  const nodes = graph.nodes;
  const edges = filterNeo4jDisplayEdges(graph.edges, nodes);
  neo4jGraphContainer.style.height = "";
  state.neo4jViz = null;
  if (!nodes.length) {
    renderNeo4jGraphFallback(payload.error || "选择或启动任务后显示当前领域的 Neo4j 图谱");
    return;
  }
  if (!nodes.some((node) => node.id === state.neo4jSelectedNodeId)) {
    state.neo4jSelectedNodeId = chooseDefaultNeo4jSelectedNode(nodes)?.id || "";
  }
  const counts = summarizeNeo4jNodeStates(nodes);
  const generatingCount = counts.generating + counts.generated + counts.completion_ready + counts.document_generating;
  const evidenceCount = counts.evidence_pending + counts.evidence_running + counts.link_querying;
  const completedCount = counts.completed + counts.approved + counts.documented + counts.link_verified;
  const visibleIssueNodeIds = getNeo4jIssueNodeIds(state.neo4jIssueInspection, nodes);
  const visibleNodes = selectNeo4jMapNodes(nodes, visibleIssueNodeIds);
  const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
  const selectedNode = nodes.find((node) => node.id === state.neo4jSelectedNodeId) || visibleNodes[0];
  const visibleEdges = buildNeo4jReadableEdges(visibleNodes, edges).filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target));
  const compressedEdges = buildNeo4jCompressedEdges(visibleNodes, edges).filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target));
  const renderedEdges = state.neo4jShowCompressedEdges ? [...visibleEdges, ...compressedEdges] : visibleEdges;
  const connectedNodeIds = selectedNode ? getNeo4jConnectedNodeIds(selectedNode.id, renderedEdges) : new Set();
  const hiddenNodeCount = Math.max(0, nodes.length - visibleNodes.length);
  const hiddenEdgeCount = compressedEdges.length;
  neo4jGraphContainer.innerHTML = `
    <div class="neo4j-html-graph neo4j-neovis-graph" data-node-count="${escapeHtml(String(nodes.length))}">
      <div class="neo4j-state-strip" aria-label="图谱状态统计">
        ${renderNeo4jStateBadge("规划", counts.planned)}
        ${renderNeo4jStateBadge("生成中", generatingCount)}
        ${renderNeo4jStateBadge("证据中", evidenceCount)}
        ${renderNeo4jStateBadge("完成", completedCount)}
        ${renderNeo4jStateBadge("失败", counts.failed)}
      </div>
      <div class="neo4j-neovis-layout">
        <section class="neo4j-neovis-frame" aria-label="Neovis.js Neo4j 知识图谱">
          <div class="neo4j-neovis-head">
            <span>Neovis.js force graph</span>
            <span>显示 ${escapeHtml(String(visibleNodes.length))}/${escapeHtml(String(nodes.length))} 个节点</span>
            ${hiddenNodeCount ? `<span>隐藏 ${escapeHtml(String(hiddenNodeCount))} 个低优先级节点</span>` : ""}
            ${hiddenEdgeCount ? `<span>收起 ${escapeHtml(String(hiddenEdgeCount))} 条重复或跨层关系</span>` : ""}
            ${hiddenEdgeCount ? `<button class="neo4j-toggle-edges" type="button" data-toggle-compressed-edges>${state.neo4jShowCompressedEdges ? "收起压缩边" : "显示全部边"}</button>` : ""}
            <button class="neo4j-check-issues" type="button" data-check-graph-issues>检查知识点</button>
          </div>
          <div id="neo4j-neovis-viz" class="neo4j-neovis-viz"></div>
        </section>
        ${renderNeo4jNodeInspector(selectedNode, nodes, edges)}
      </div>
    </div>`;
  renderNeo4jNeovisNetwork({
    nodes: visibleNodes,
    edges: renderedEdges,
    selectedNodeId: selectedNode?.id || "",
    connectedNodeIds,
    issueNodeIds: visibleIssueNodeIds,
    previousNodeIds,
    previousEdgeIds,
    graph,
    payload,
    previousPayload,
  });
  bindNeo4jGraphInteractions(graph, payload, previousPayload);
}

function summarizeNeo4jNodeStates(nodes) {
  const counts = {
    planned: 0,
    generating: 0,
    generated: 0,
    evidence_pending: 0,
    evidence_running: 0,
    reviewing: 0,
    repairing: 0,
    approved: 0,
    completion_ready: 0,
    document_generating: 0,
    documented: 0,
    link_querying: 0,
    link_verified: 0,
    completed: 0,
    failed: 0,
  };
  nodes.forEach((node) => {
    const stateName = getNeo4jGenerationState(node);
    counts[stateName] = (counts[stateName] || 0) + 1;
  });
  return counts;
}

function renderNeo4jStateBadge(label, count) {
  return `<span class="neo4j-state-badge"><strong>${escapeHtml(String(count))}</strong>${escapeHtml(label)}</span>`;
}

function chooseDefaultNeo4jSelectedNode(nodes) {
  return [...nodes].sort((a, b) => getNeo4jHtmlNodePriority(a) - getNeo4jHtmlNodePriority(b) || compareNeo4jNodesForLayout(a, b))[0];
}

function getNeo4jIssueNodeIds(inspection, nodes = []) {
  const issues = Array.isArray(inspection?.issues) ? inspection.issues : [];
  const graphNodeIds = new Set(nodes.map((node) => node.id));
  return new Set(
    issues
      .map((issue) => String(issue.graph_id || ""))
      .filter((graphId) => graphId && (!graphNodeIds.size || graphNodeIds.has(graphId)))
  );
}

function selectNeo4jMapNodes(nodes, issueNodeIds = new Set()) {
  const sorted = [...nodes].sort((a, b) => getNeo4jHtmlNodePriority(a) - getNeo4jHtmlNodePriority(b) || compareNeo4jNodesForLayout(a, b));
  const structural = sorted.filter((node) => node.type === "Domain" || isNeo4jStructureNode(node));
  const others = sorted.filter((node) => node.type !== "Domain" && !isNeo4jStructureNode(node));
  const selected = nodes.find((node) => node.id === state.neo4jSelectedNodeId);
  const issueNodes = nodes.filter((node) => issueNodeIds.has(node.id));
  const byId = new Map(
    [...structural, ...issueNodes, ...others.slice(0, Math.max(0, 72 - structural.length)), selected]
      .filter(Boolean)
      .map((node) => [node.id, node])
  );
  return [...byId.values()].slice(0, 80);
}

function selectNeo4jHtmlNodes(nodes) {
  return [...nodes]
    .sort((a, b) => {
      const priorityA = getNeo4jHtmlNodePriority(a);
      const priorityB = getNeo4jHtmlNodePriority(b);
      return priorityA - priorityB || compareNeo4jNodesForLayout(a, b);
    })
    .slice(0, 14);
}

function getNeo4jHtmlNodePriority(node) {
  const stateName = getNeo4jGenerationState(node);
  const stateOrder = {
    link_querying: 0,
    reviewing: 1,
    repairing: 2,
    completion_ready: 3,
    document_generating: 3,
    link_failed: 4,
    documented: 5,
    link_verified: 6,
    planned: 6,
  }[stateName] ?? 7;
  const typeOrder = {
    Domain: 0,
    SubTopic: 1,
    KnowledgeStructureNode: 2,
    Article: 3,
    Entity: 4,
  }[node.type] ?? 8;
  return stateOrder * 10 + typeOrder;
}

function renderNeo4jHtmlNode(node, isNew) {
  const stateName = getNeo4jGenerationState(node);
  const statusLabel = formatNeo4jGenerationState(stateName);
  const kind = formatNeo4jNodeKind(node);
  const path = node.properties?.generated_path || node.path || node.properties?.id || node.id;
  return `
    <article class="neo4j-node-card state-${escapeHtml(sanitizeClassName(stateName))}${isNew ? " is-new" : ""}" title="${escapeHtml(path)}">
      <span>${escapeHtml(statusLabel)} · ${escapeHtml(kind)}</span>
      <strong>${escapeHtml(node.title || node.id)}</strong>
      <small>${escapeHtml(path)}</small>
    </article>`;
}

function renderNeo4jHtmlEdge(edge, nodes, isNew) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const source = byId.get(edge.source);
  const target = byId.get(edge.target);
  return `
    <div class="neo4j-edge-row${isNew ? " is-new" : ""}">
      <span>${escapeHtml(edge.type || "RELATED")}</span>
      <strong>${escapeHtml(source?.title || edge.source)}</strong>
      <em aria-hidden="true">&rarr;</em>
      <strong>${escapeHtml(target?.title || edge.target)}</strong>
    </div>`;
}

function buildNeo4jReadableMap(nodes, edges) {
  const containerWidth = neo4jGraphContainer?.clientWidth || 920;
  const width = Math.max(containerWidth < 900 ? 560 : 920, containerWidth < 900 ? containerWidth - 28 : containerWidth - 340);
  const compact = width < 720;
  const nodeWidth = compact ? 220 : 210;
  const nodeHeight = 78;
  const layout = nodes.some((node) => isNeo4jStructureNode(node))
    ? layoutNeo4jStructureNodes(nodes, compact, width, nodeWidth, nodeHeight)
    : layoutNeo4jNodesByType(nodes, compact, width, nodeWidth, nodeHeight);
  const layoutNodes = layout.nodes.map((item) => ({ ...item, width: nodeWidth, height: nodeHeight }));
  const byId = new Map(layoutNodes.map((item) => [item.node.id, item]));
  const layoutEdges = edges
    .filter((edge) => byId.has(edge.source) && byId.has(edge.target))
    .map((edge) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      return {
        ...edge,
        sourceX: source.x + nodeWidth / 2,
        sourceY: source.y + nodeHeight,
        targetX: target.x + nodeWidth / 2,
        targetY: target.y,
      };
    });
  return { nodes: layoutNodes, edges: layoutEdges, width: layout.width, height: layout.height };
}

function buildNeo4jReadableEdges(nodes, edges) {
  const structureNodes = nodes.filter((node) => isNeo4jStructureNode(node));
  if (!structureNodes.length) return filterNeo4jDisplayEdges(edges, nodes);

  const domainNode = nodes.find((node) => node.type === "Domain");
  const byLogicalId = new Map(structureNodes.map((node) => [getNeo4jLogicalId(node), node]));
  const readableEdges = [];
  const seen = new Set();
  structureNodes.forEach((node) => {
    const parentId = String(node.properties?.parent_node_id || "");
    const parent = byLogicalId.get(parentId);
    const source = parent || (domainNode && node.id !== domainNode.id ? domainNode : null);
    if (!source || source.id === node.id) return;
    const edgeId = `readable:${source.id}:${node.id}`;
    if (seen.has(edgeId)) return;
    seen.add(edgeId);
    readableEdges.push({
      id: edgeId,
      source: source.id,
      target: node.id,
      type: "PARENT_CHILD",
      properties: { readable: true },
    });
  });
  return readableEdges;
}

function buildNeo4jCompressedEdges(nodes, edges) {
  const visibleNodeIds = new Set(nodes.map((node) => node.id));
  return edges
    .filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target))
    .map((edge) => ({
      ...edge,
      id: `compressed:${edge.id}`,
      properties: { ...(edge.properties || {}), compressed: true },
    }));
}

function renderNeo4jNeovisNetwork({ nodes, edges, selectedNodeId, connectedNodeIds, issueNodeIds, previousNodeIds, previousEdgeIds, graph, payload, previousPayload }) {
  const vizContainer = document.querySelector("#neo4j-neovis-viz");
  const NeoVisConstructor = window.NeoVis?.default || window.NeoVis?.NeoVis || window.NeoVis;
  if (!vizContainer || !NeoVisConstructor) {
    if (vizContainer) {
      vizContainer.innerHTML = '<div class="neo4j-graph-empty">Neovis.js 加载失败，请检查网络或 CDN。</div>';
    }
    return;
  }

  const neoViz = new NeoVisConstructor({
    containerId: "neo4j-neovis-viz",
    dataFunction: async function* emptyNeovisData() {},
    labels: {},
    relationships: {},
    visConfig: buildNeo4jNeovisConfig(),
  });
  state.neo4jViz = neoViz;
  neoViz.render();
  window.setTimeout(() => {
    if (state.neo4jViz !== neoViz || !neoViz.network) return;
    const visNodes = nodes.map((node) => toNeo4jVisNode(node, {
      isNew: !previousNodeIds.has(node.id),
      isSelected: node.id === selectedNodeId,
      isConnected: connectedNodeIds.has(node.id),
      isIssue: issueNodeIds.has(node.id),
    }));
    const visEdges = edges.map((edge) => toNeo4jVisEdge(edge, {
      isNew: !previousEdgeIds.has(edge.id),
      isConnected: isNeo4jEdgeConnectedToNode(edge, selectedNodeId),
    }));
    neoViz.nodes.clear();
    neoViz.edges.clear();
    neoViz.nodes.update(visNodes);
    neoViz.edges.update(visEdges);
    neoViz.network.setData({ nodes: neoViz.nodes, edges: neoViz.edges });
    neoViz.network.setOptions(buildNeo4jNeovisConfig());
    neoViz.network.fit({ animation: false });
    if (state.neo4jPendingFocusNodeId && nodes.some((node) => node.id === state.neo4jPendingFocusNodeId)) {
      neoViz.network.selectNodes([state.neo4jPendingFocusNodeId]);
      neoViz.network.focus(state.neo4jPendingFocusNodeId, {
        scale: 1.18,
        animation: { duration: 480, easingFunction: "easeInOutQuad" },
      });
      state.neo4jPendingFocusNodeId = "";
    }
    neoViz.network.on("click", (params) => {
      if (!params.nodes?.length) return;
      state.neo4jSelectedNodeId = String(params.nodes[0]);
      renderNeo4jGraphHtml(graph, payload, previousPayload);
    });
  }, 0);
}

function buildNeo4jNeovisConfig() {
  return {
    autoResize: true,
    interaction: {
      hover: true,
      navigationButtons: true,
      keyboard: false,
      multiselect: false,
      tooltipDelay: 120,
    },
    layout: {
      improvedLayout: true,
      hierarchical: { enabled: false },
    },
    physics: {
      enabled: true,
      solver: "forceAtlas2Based",
      forceAtlas2Based: {
        gravitationalConstant: -86,
        centralGravity: 0.012,
        springLength: 132,
        springConstant: 0.08,
        damping: 0.58,
        avoidOverlap: 0.7,
      },
      stabilization: {
        enabled: true,
        iterations: 320,
        updateInterval: 20,
        fit: true,
      },
      adaptiveTimestep: true,
    },
    nodes: {
      shape: "dot",
      borderWidth: 2,
      size: 24,
      chosen: true,
      font: {
        color: "#17302b",
        size: 13,
        face: "Avenir Next, PingFang SC, Microsoft YaHei, sans-serif",
        strokeWidth: 4,
        strokeColor: "#fffdf8",
        vadjust: -2,
      },
      scaling: {
        min: 18,
        max: 34,
        label: { enabled: true, min: 12, max: 18 },
      },
      shadow: {
        enabled: true,
        color: "rgba(23, 33, 31, 0.16)",
        size: 10,
        x: 0,
        y: 4,
      },
    },
    edges: {
      width: 1.3,
      color: {
        color: "rgba(93, 106, 102, 0.42)",
        highlight: "#2f5f91",
        hover: "#2f5f91",
        inherit: false,
      },
      smooth: {
        enabled: true,
        type: "dynamic",
        roundness: 0.38,
      },
      arrows: {
        to: { enabled: true, scaleFactor: 0.48 },
      },
      font: {
        color: "#66736e",
        size: 9,
        face: "Avenir Next, PingFang SC, Microsoft YaHei, sans-serif",
        strokeWidth: 4,
        strokeColor: "#fffdf8",
        align: "middle",
      },
      selectionWidth: 2.4,
    },
  };
}

function toNeo4jVisNode(node, { isNew, isSelected, isConnected, isIssue }) {
  const stateName = getNeo4jGenerationState(node);
  const palette = getNeo4jVisNodePalette(node, stateName, isIssue);
  const label = shortenNeo4jVisLabel(node.title || node.id, isSelected ? 18 : 12);
  const path = node.properties?.generated_path || node.path || node.properties?.id || node.id;
  const selectedBackground = isIssue ? "#b6463a" : "#2f5f91";
  const selectedBorder = isIssue ? "#7f2419" : "#17211f";
  return {
    id: node.id,
    label,
    title: `${node.title || node.id}\n${formatNeo4jGenerationState(stateName)} · ${formatNeo4jNodeKind(node)}\n${path}`,
    group: formatNeo4jNodeKind(node),
    value: getNeo4jVisNodeValue(node),
    color: {
      background: isSelected ? selectedBackground : palette.background,
      border: isSelected ? selectedBorder : isConnected && !isIssue ? "#2f5f91" : palette.border,
      highlight: { background: selectedBackground, border: selectedBorder },
      hover: { background: palette.hover, border: isIssue ? "#a53e33" : "#17211f" },
    },
    font: {
      color: isSelected ? "#ffffff" : "#17302b",
      size: isSelected ? 15 : 13,
      strokeWidth: isSelected ? 2 : 4,
      strokeColor: isSelected ? selectedBackground : "#fffdf8",
    },
    borderWidth: isNew || isConnected || isSelected ? 3 : 2,
    opacity: isConnected || isSelected ? 1 : 0.84,
  };
}

function getNeo4jVisNodePalette(node, stateName, isIssue = false) {
  if (isIssue) {
    return { background: "#f5b5ae", border: "#b6463a", hover: "#ffd7d2" };
  }
  if (stateName === "failed" || stateName === "link_failed") {
    return { background: "#f6aaa1", border: "#a9483f", hover: "#ffd6d1" };
  }
  if (stateName === "reviewing" || stateName === "repairing" || stateName === "document_generating" || stateName === "link_querying") {
    return { background: "#91bdf4", border: "#2f5f91", hover: "#cfe2fb" };
  }
  if (stateName === "approved" || stateName === "documented" || stateName === "link_verified" || stateName === "completed" || stateName === "generated") {
    return { background: "#8fd6b2", border: "#1e7b64", hover: "#c9efda" };
  }
  if (node.type === "Domain") return { background: "#7fb4ff", border: "#2f5f91", hover: "#cfe2fb" };
  return { background: "#86b7ff", border: "#5e88bd", hover: "#d8e8ff" };
}

function getNeo4jVisNodeValue(node) {
  const kind = String(formatNeo4jNodeKind(node)).toLowerCase();
  if (node.type === "Domain" || kind === "domain") return 34;
  if (kind === "index" || kind === "section") return 27;
  if (kind === "subtopic") return 23;
  return 19;
}

function shortenNeo4jVisLabel(value, maxLength) {
  const text = String(value || "");
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(1, maxLength - 1))}…`;
}

function toNeo4jVisEdge(edge, { isNew, isConnected }) {
  const isCompressed = edge.properties?.compressed === true;
  return {
    id: edge.id,
    from: edge.source,
    to: edge.target,
    label: isConnected && !isCompressed ? formatNeo4jEdgeType(edge.type) : "",
    title: formatNeo4jEdgeType(edge.type),
    width: isCompressed ? 1.1 : isConnected || isNew ? 2.2 : 1.2,
    color: {
      color: isCompressed ? "rgba(93, 106, 102, 0.38)" : isConnected ? "#2f5f91" : "rgba(93, 106, 102, 0.42)",
      highlight: isCompressed ? "rgba(93, 106, 102, 0.6)" : "#2f5f91",
      hover: isCompressed ? "rgba(93, 106, 102, 0.6)" : "#2f5f91",
      inherit: false,
    },
    dashes: isCompressed,
    smooth: isCompressed ? { enabled: true, type: "curvedCW", roundness: 0.16 } : undefined,
    arrows: { to: { enabled: true, scaleFactor: isCompressed ? 0.35 : isConnected ? 0.62 : 0.45 } },
  };
}

function getNeo4jConnectedNodeIds(nodeId, edges) {
  const connected = new Set([nodeId]);
  edges.forEach((edge) => {
    if (edge.source === nodeId) connected.add(edge.target);
    if (edge.target === nodeId) connected.add(edge.source);
  });
  return connected;
}

function isNeo4jEdgeConnectedToNode(edge, nodeId) {
  return edge.source === nodeId || edge.target === nodeId;
}

function renderNeo4jMapEdge(edge, isNew, isConnected) {
  const midY = Math.max(edge.sourceY + 24, Math.floor((edge.sourceY + edge.targetY) / 2));
  const path = `M ${edge.sourceX} ${edge.sourceY} C ${edge.sourceX} ${midY}, ${edge.targetX} ${midY}, ${edge.targetX} ${edge.targetY}`;
  const labelX = Math.floor((edge.sourceX + edge.targetX) / 2);
  const labelY = Math.floor(midY - 5);
  return `
    <g class="neo4j-map-edge${isNew ? " is-new" : ""}${isConnected ? " is-connected" : ""}">
      <path d="${escapeHtml(path)}"></path>
      <text x="${escapeHtml(String(labelX))}" y="${escapeHtml(String(labelY))}">${escapeHtml(formatNeo4jEdgeType(edge.type))}</text>
    </g>`;
}

function renderNeo4jMapNode(item, isNew, isSelected, isConnected) {
  const node = item.node;
  const stateName = getNeo4jGenerationState(node);
  const statusLabel = formatNeo4jGenerationState(stateName);
  const kind = formatNeo4jNodeKind(node);
  const path = node.properties?.generated_path || node.path || node.properties?.id || node.id;
  return `
    <button class="neo4j-map-node state-${escapeHtml(sanitizeClassName(stateName))}${isNew ? " is-new" : ""}${isSelected ? " is-selected" : ""}${isConnected ? " is-connected" : " is-dimmed"}"
      type="button"
      data-neo4j-node-id="${escapeHtml(node.id)}"
      style="left:${escapeHtml(String(item.x))}px; top:${escapeHtml(String(item.y))}px; width:${escapeHtml(String(item.width))}px; height:${escapeHtml(String(item.height))}px;"
      title="${escapeHtml(path)}">
      <span>${escapeHtml(statusLabel)} · ${escapeHtml(kind)}</span>
      <strong>${escapeHtml(node.title || node.id)}</strong>
      <small>${escapeHtml(path)}</small>
    </button>`;
}

function renderNeo4jNodeInspector(node, nodes, edges) {
  if (!node) return '<aside class="neo4j-node-inspector"><div class="neo4j-edge-empty">暂无可查看节点</div></aside>';
  const incoming = edges.filter((edge) => edge.target === node.id).slice(0, 10);
  const outgoing = edges.filter((edge) => edge.source === node.id).slice(0, 10);
  const childCount = edges.filter((edge) => edge.source === node.id && (edge.properties?.type === "CONTAINS" || edge.type === "STRUCTURE_EDGE")).length;
  const path = node.properties?.generated_path || node.path || node.properties?.id || node.id;
  const logicalNodeId = getNeo4jLogicalId(node);
  const canExpand = isNeo4jStructureNode(node);
  return `
    <aside class="neo4j-node-inspector" aria-label="选中节点详情">
      <div class="neo4j-inspector-head">
        <span>${escapeHtml(formatNeo4jGenerationState(getNeo4jGenerationState(node)))}</span>
        <strong>${escapeHtml(node.title || node.id)}</strong>
        <small>${escapeHtml(formatNeo4jNodeKind(node))}</small>
      </div>
      <dl class="neo4j-node-fields">
        ${renderNeo4jNodeField("路径", path)}
        ${renderNeo4jNodeField("待查证据", node.properties?.pending_task_count)}
        ${renderNeo4jNodeField("已完成证据", node.properties?.completed_task_count)}
        ${renderNeo4jNodeField("Task", node.properties?.task_id)}
      </dl>
      ${canExpand ? `<div class="neo4j-node-actions">
        <button class="neo4j-expand-node" type="button" data-expand-node-id="${escapeHtml(logicalNodeId)}"${childCount ? ' title="该节点已有子分支，将作为强制扩展继续追加。"' : ""}>
          扩展知识点
        </button>
      </div>` : ""}
      <div class="neo4j-inspector-relations">
        <h3>相邻关系</h3>
        ${renderNeo4jInspectorRelationGroup("来自", incoming, node, nodes)}
        ${renderNeo4jInspectorRelationGroup("指向", outgoing, node, nodes)}
      </div>
      ${renderNeo4jGraphIssueList(state.neo4jIssueInspection, node.id, nodes)}
    </aside>`;
}

function renderNeo4jInspectorRelationGroup(label, relations, selectedNode, nodes) {
  return `
    <div class="neo4j-inspector-relation-group">
      <h4>${escapeHtml(label)}</h4>
      ${relations.length ? relations.map((edge) => renderNeo4jInspectorEdge(edge, selectedNode, nodes)).join("") : '<div class="neo4j-edge-empty">暂无</div>'}
    </div>`;
}

function focusNeo4jNode(nodeId, graph, payload, previousPayload) {
  if (!nodeId) return;
  state.neo4jSelectedNodeId = String(nodeId);
  state.neo4jPendingFocusNodeId = String(nodeId);
  renderNeo4jGraphHtml(graph, payload, previousPayload);
}

function bindNeo4jGraphInteractions(graph, payload, previousPayload) {
  if (!neo4jGraphContainer) return;
  neo4jGraphContainer.querySelectorAll("[data-neo4j-node-id]").forEach((button) => {
    button.addEventListener("click", () => {
      focusNeo4jNode(button.dataset.neo4jNodeId || "", graph, payload, previousPayload);
    });
  });
  neo4jGraphContainer.querySelectorAll("[data-focus-node-id]").forEach((item) => {
    item.addEventListener("click", (event) => {
      if (event.target.closest(".neo4j-issue-actions")) return;
      focusNeo4jNode(item.dataset.focusNodeId || "", graph, payload, previousPayload);
    });
  });
  const toggleEdgesButton = neo4jGraphContainer.querySelector("[data-toggle-compressed-edges]");
  if (toggleEdgesButton) {
    toggleEdgesButton.addEventListener("click", () => {
      state.neo4jShowCompressedEdges = !state.neo4jShowCompressedEdges;
      renderNeo4jGraphHtml(graph, payload, previousPayload);
    });
  }
  const checkIssuesButton = neo4jGraphContainer.querySelector("[data-check-graph-issues]");
  if (checkIssuesButton) {
    checkIssuesButton.addEventListener("click", async () => {
      const taskId = getTaskIdFromPayload(state.lastPayload) || payload.task_id;
      if (!taskId) return;
      setBusy(checkIssuesButton, true);
      try {
        state.neo4jIssueInspection = await requestJson(`/tasks/${encodeURIComponent(taskId)}/graph/issues`);
        renderNeo4jGraphHtml(graph, payload, previousPayload);
      } catch (error) {
        showError(error);
      } finally {
        setBusy(checkIssuesButton, false);
      }
    });
  }
  neo4jGraphContainer.querySelectorAll("[data-delete-issue-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const taskId = getTaskIdFromPayload(state.lastPayload) || payload.task_id;
      const graphId = button.dataset.deleteIssueId || "";
      if (!taskId || !graphId) return;
      setBusy(button, true);
      try {
        const result = await requestJson(`/tasks/${encodeURIComponent(taskId)}/graph/issues/delete`, {
          method: "POST",
          body: JSON.stringify({ graph_id: graphId }),
        });
        state.neo4jIssueInspection = await requestJson(`/tasks/${encodeURIComponent(taskId)}/graph/issues`);
        renderNeo4jGraphSnapshot({
          task_id: taskId,
          status: "local",
          domain: result.domain || payload.domain || "",
          graph: result.graph_snapshot,
          refreshed_at: result.updated_at || new Date().toISOString(),
        }, state.neo4jGraphSnapshot);
        state.neo4jGraphSnapshot = { task_id: taskId, status: "local", graph: result.graph_snapshot };
      } catch (error) {
        showError(error);
      } finally {
        setBusy(button, false);
      }
    });
  });
  neo4jGraphContainer.querySelectorAll("[data-link-issue-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const taskId = getTaskIdFromPayload(state.lastPayload) || payload.task_id;
      const graphId = button.dataset.linkIssueId || "";
      const targetNodeId = button.dataset.targetNodeId || "";
      if (!taskId || !graphId || !targetNodeId) return;
      setBusy(button, true);
      try {
        const result = await requestJson(`/tasks/${encodeURIComponent(taskId)}/graph/issues/link`, {
          method: "POST",
          body: JSON.stringify({ graph_id: graphId, target_node_id: targetNodeId, relationship_type: "RELATED_TO" }),
        });
        state.neo4jIssueInspection = await requestJson(`/tasks/${encodeURIComponent(taskId)}/graph/issues`);
        renderNeo4jGraphSnapshot({
          task_id: taskId,
          status: "local",
          domain: result.domain || payload.domain || "",
          graph: result.graph_snapshot,
          refreshed_at: result.updated_at || new Date().toISOString(),
        }, state.neo4jGraphSnapshot);
        state.neo4jGraphSnapshot = { task_id: taskId, status: "local", graph: result.graph_snapshot };
      } catch (error) {
        showError(error);
      } finally {
        setBusy(button, false);
      }
    });
  });
  const expandButton = neo4jGraphContainer.querySelector("[data-expand-node-id]");
  if (!expandButton) return;
  expandButton.addEventListener("click", async () => {
    const taskId = getTaskIdFromPayload(state.lastPayload) || payload.task_id;
    const nodeId = expandButton.dataset.expandNodeId || "";
    if (!taskId || !nodeId) return;
    setBusy(expandButton, true);
    expandButton.textContent = "扩展中...";
    try {
      const result = await requestJson(`/tasks/${encodeURIComponent(taskId)}/graph/nodes/expand`, {
        method: "POST",
        body: JSON.stringify({ node_id: nodeId, force: true }),
      });
      showPayload(mergeTaskPayload(result.task || result));
      renderNeo4jGraphSnapshot({
        task_id: taskId,
        status: "local",
        domain: result.task?.request_context?.domain || payload.domain || "",
        graph: result.graph_snapshot,
        refreshed_at: result.task?.updated_at || new Date().toISOString(),
      }, state.neo4jGraphSnapshot);
      state.neo4jGraphSnapshot = {
        task_id: taskId,
        status: "local",
        graph: result.graph_snapshot,
      };
      scheduleNeo4jGraphRefresh(taskId, { force: true });
    } catch (error) {
      showError(error);
    } finally {
      setBusy(expandButton, false);
    }
  });
}

function renderNeo4jGraphIssueList(inspection, selectedNodeId = "", nodes = []) {
  if (!inspection) return "";
  const graphNodeIds = new Set(nodes.map((node) => node.id));
  const issues = (Array.isArray(inspection.issues) ? inspection.issues : []).filter((issue) => {
    const graphId = String(issue.graph_id || "");
    return graphId && (!graphNodeIds.size || graphNodeIds.has(graphId));
  });
  if (!issues.length) {
    return `
      <div class="neo4j-issue-panel">
        <h3>问题知识点</h3>
        <div class="neo4j-edge-empty">未发现重名或独立的非结构知识点。</div>
      </div>`;
  }
  return `
    <div class="neo4j-issue-panel">
      <h3>问题知识点 · ${escapeHtml(String(issues.length))}</h3>
      ${issues.map((issue) => renderNeo4jGraphIssue(issue, selectedNodeId)).join("")}
    </div>`;
}

function renderNeo4jGraphIssue(issue, selectedNodeId = "") {
  const targetNodeId = String(issue.matching_structure_node_id || "");
  const focusNodeId = String(issue.graph_id || "");
  const isSelected = focusNodeId && focusNodeId === selectedNodeId;
  return `
    <div class="neo4j-issue-item${isSelected ? " is-selected" : ""}" data-focus-node-id="${escapeHtml(focusNodeId)}">
      <span>${escapeHtml(issue.reason || "duplicate_non_structure_knowledge_point")}</span>
      <strong>${escapeHtml(issue.title || issue.logical_id || issue.graph_id)}</strong>
      <small>${escapeHtml(formatIssueMatch(issue))}</small>
      <div class="neo4j-issue-actions">
        <button type="button" data-delete-issue-id="${escapeHtml(issue.graph_id)}">清除多余节点</button>
        ${targetNodeId ? `<button type="button" data-link-issue-id="${escapeHtml(issue.graph_id)}" data-target-node-id="${escapeHtml(targetNodeId)}">连接到结构节点</button>` : ""}
      </div>
    </div>`;
}

function formatIssueMatch(issue) {
  const match = [issue.matching_structure_title, issue.matching_structure_type, issue.relationship_types?.join("/")].filter(Boolean).join(" · ");
  return match || issue.graph_id || "";
}

function renderNeo4jNodeField(label, value) {
  if (value === undefined || value === null || value === "") return "";
  return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`;
}

function renderNeo4jInspectorEdge(edge, selectedNode, nodes) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const isOutgoing = edge.source === selectedNode.id;
  const peer = byId.get(isOutgoing ? edge.target : edge.source);
  const focusNodeId = String(peer?.id || (isOutgoing ? edge.target : edge.source) || "");
  return `
    <div class="neo4j-inspector-edge${focusNodeId ? " is-clickable" : ""}"${focusNodeId ? ` data-focus-node-id="${escapeHtml(focusNodeId)}"` : ""}>
      <span>${escapeHtml(isOutgoing ? "指向" : "来自")} · ${escapeHtml(formatNeo4jEdgeType(edge.type))}</span>
      <strong>${escapeHtml(peer?.title || (isOutgoing ? edge.target : edge.source))}</strong>
    </div>`;
}

function formatNeo4jEdgeType(type) {
  return {
    PARENT_CHILD: "包含",
    STRUCTURE_EDGE: "结构",
    HAS_STRUCTURE_NODE: "包含",
    HAS_SUBTOPIC: "子领域",
    HAS_ARTICLE: "文章",
    MENTIONS: "提及",
  }[type] || type || "关联";
}

function getNeo4jGenerationState(node) {
  if (node.properties?.generation_state) return String(node.properties.generation_state);
  if (node.generation_state) return String(node.generation_state);
  if (node.properties?.is_completed === true) return "completed";
  if (node.properties?.is_generated === true) return "generated";
  return "planned";
}

function formatNeo4jGenerationState(stateName) {
  return {
    planned: "TODO",
    reviewing: "审查中",
    repairing: "修补中",
    approved: "已通过",
    completion_ready: "可补全",
    document_generating: "补全中",
    documented: "已落盘",
    link_querying: "查链接",
    link_verified: "链接OK",
    link_failed: "链接失败",
    failed: "失败",
  }[stateName] || stateName;
}

function sanitizeClassName(value) {
  return String(value || "unknown").toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
}

function ensureNeo4jGraph() {
  if (!neo4jGraphContainer || !window.X6?.Graph) return null;
  if (state.neo4jGraph) return state.neo4jGraph;
  const { Graph } = window.X6;
  state.neo4jGraph = new Graph({
    container: neo4jGraphContainer,
    width: neo4jGraphContainer.clientWidth || 960,
    height: neo4jGraphContainer.clientHeight || 420,
    panning: true,
    mousewheel: {
      enabled: true,
      modifiers: ["ctrl", "meta"],
      minScale: 0.5,
      maxScale: 1.6,
    },
    interacting: {
      nodeMovable: false,
      edgeMovable: false,
      arrowheadMovable: false,
      vertexMovable: false,
      magnetConnectable: false,
    },
    background: { color: "#fffdf8" },
    grid: {
      size: 14,
      visible: true,
      type: "dot",
      args: { color: "rgba(23, 33, 31, 0.1)" },
    },
  });
  document.body.classList.add("neo4j-graph-ready");
  return state.neo4jGraph;
}

function buildNeo4jGraphData(graph, previousNodeIds, previousEdgeIds) {
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  const width = neo4jGraphContainer?.clientWidth || 960;
  const compact = width < 700;
  const nodeWidth = compact ? Math.max(220, width - 56) : 210;
  const nodeHeight = 74;
  const useStructureLayout = nodes.some((node) => isNeo4jStructureNode(node));
  const layout = useStructureLayout
    ? layoutNeo4jStructureNodes(nodes, compact, width, nodeWidth, nodeHeight)
    : layoutNeo4jNodesByType(nodes, compact, width, nodeWidth, nodeHeight);
  const positioned = layout.nodes.map((item) => ({
    id: item.node.id,
    shape: "rect",
    x: item.x,
    y: item.y,
    width: nodeWidth,
    height: nodeHeight,
    ports: graphNodePorts(),
    markup: [
      { tagName: "rect", selector: "body" },
      { tagName: "text", selector: "kind" },
      { tagName: "text", selector: "title" },
      { tagName: "text", selector: "path" },
    ],
    attrs: getNeo4jNodeAttrs(item.node, !previousNodeIds.has(item.node.id)),
  }));
  const visibleNodeIds = new Set(positioned.map((node) => node.id));
  const displayEdges = filterNeo4jDisplayEdges(edges, nodes);
  const x6Edges = displayEdges
    .filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      shape: "edge",
      source: { cell: edge.source, port: "bottom" },
      target: { cell: edge.target, port: "top" },
      connector: { name: "rounded" },
      router: { name: "manhattan", args: { padding: 14 } },
      attrs: getNeo4jEdgeAttrs(!previousEdgeIds.has(edge.id), edge.type),
    }));
  return { nodes: positioned, edges: x6Edges, meta: { height: layout.height, width: layout.width } };
}

function layoutNeo4jStructureNodes(nodes, compact, width, nodeWidth, nodeHeight) {
  const startX = 28;
  const startY = 28;
  const gapY = 30;
  const gapX = compact ? 18 : 32;
  const domainNodes = nodes.filter((node) => node.type === "Domain");
  const structureNodes = nodes.filter((node) => isNeo4jStructureNode(node));
  const otherNodes = nodes.filter((node) => node.type !== "Domain" && !isNeo4jStructureNode(node));
  const depthByLogicalId = buildStructureDepthMap(structureNodes);
  const nodesByLogicalId = new Map(structureNodes.map((node) => [getNeo4jLogicalId(node), node]));
  const positioned = [];
  let cursorY = startY;
  const placeRow = (rowNodes, depth) => {
    const sorted = [...rowNodes].sort(compareNeo4jNodesForLayout);
    const rowWidth = sorted.length * nodeWidth + Math.max(0, sorted.length - 1) * gapX;
    const availableWidth = Math.max(width - startX * 2, rowWidth);
    const rowStartX = Math.max(startX, startX + Math.floor((availableWidth - rowWidth) / 2));
    sorted.forEach((node, index) => {
      positioned.push({ node, x: rowStartX + index * (nodeWidth + gapX), y: cursorY, depth });
    });
    cursorY += nodeHeight + gapY;
  };

  if (domainNodes.length) placeRow(domainNodes, 0);
  const rootStructureNodes = structureNodes.filter((node) => {
    const parentId = String(node.properties?.parent_node_id || "");
    return !parentId || !nodesByLogicalId.has(parentId);
  });
  const maxDepth = Math.max(0, ...structureNodes.map((node) => depthByLogicalId.get(getNeo4jLogicalId(node)) || 0));
  for (let depth = 0; depth <= maxDepth; depth += 1) {
    const row = structureNodes.filter((node) => {
      if ((depthByLogicalId.get(getNeo4jLogicalId(node)) || 0) !== depth) return false;
      if (depth === 0) return rootStructureNodes.includes(node);
      return true;
    });
    if (row.length) placeRow(row, domainNodes.length ? depth + 1 : depth);
  }
  if (otherNodes.length) placeRow(otherNodes, maxDepth + 2);
  const maxRight = positioned.length ? Math.max(...positioned.map((item) => item.x + nodeWidth)) : width;
  return {
    nodes: positioned,
    width: Math.max(width, maxRight + startX),
    height: Math.max(460, cursorY + startY),
  };
}

function layoutNeo4jNodesByType(nodes, compact, width, nodeWidth, nodeHeight) {
  const groupOrder = ["Domain", "SubTopic", "Article", "Entity", "KnowledgeStructureNode"];
  const grouped = groupNeo4jNodes(nodes, groupOrder);
  const gapX = compact ? 18 : 32;
  const gapY = 30;
  const startX = 28;
  const startY = 28;
  const positioned = [];
  let cursorY = startY;
  grouped.forEach((group, groupIndex) => {
    const rowWidth = group.nodes.length * nodeWidth + Math.max(0, group.nodes.length - 1) * gapX;
    const rowStartX = Math.max(startX, startX + Math.floor((Math.max(width - startX * 2, rowWidth) - rowWidth) / 2));
    group.nodes.forEach((node, nodeIndex) => {
      positioned.push({
        node,
        x: rowStartX + nodeIndex * (nodeWidth + gapX),
        y: cursorY,
      });
    });
    cursorY += nodeHeight + gapY;
  });
  const maxRight = positioned.length ? Math.max(...positioned.map((item) => item.x + nodeWidth)) : width;
  return {
    nodes: positioned,
    width: Math.max(width, maxRight + startX),
    height: Math.max(460, cursorY + startY),
  };
}

function groupNeo4jNodes(nodes, groupOrder) {
  const byGroup = new Map();
  nodes.forEach((node) => {
    const group = groupOrder.includes(node.type) ? node.type : node.labels?.includes("Entity") ? "Entity" : node.type || "Node";
    if (!byGroup.has(group)) byGroup.set(group, []);
    byGroup.get(group).push(node);
  });
  return [...byGroup.entries()]
    .sort(([a], [b]) => {
      const indexA = groupOrder.indexOf(a);
      const indexB = groupOrder.indexOf(b);
      return (indexA === -1 ? 99 : indexA) - (indexB === -1 ? 99 : indexB) || a.localeCompare(b);
    })
    .map(([type, groupNodes]) => ({
      type,
      nodes: groupNodes.sort((a, b) => String(a.title || "").localeCompare(String(b.title || ""))),
    }));
}

function isNeo4jStructureNode(node) {
  return node.type === "KnowledgeStructureNode" || node.labels?.includes("KnowledgeStructureNode");
}

function getNeo4jLogicalId(node) {
  return String(node.properties?.id || node.id || "");
}

function buildStructureDepthMap(structureNodes) {
  const byLogicalId = new Map(structureNodes.map((node) => [getNeo4jLogicalId(node), node]));
  const memo = new Map();
  const visit = (node) => {
    const logicalId = getNeo4jLogicalId(node);
    if (memo.has(logicalId)) return memo.get(logicalId);
    const parentId = String(node.properties?.parent_node_id || "");
    const parent = byLogicalId.get(parentId);
    const depth = parent ? visit(parent) + 1 : 0;
    memo.set(logicalId, depth);
    return depth;
  };
  structureNodes.forEach((node) => visit(node));
  return memo;
}

function compareNeo4jNodesForLayout(a, b) {
  const kindOrder = { domain: 0, index: 1, section: 2, subtopic: 3, article: 4 };
  const kindA = String(a.properties?.node_type || "").toLowerCase();
  const kindB = String(b.properties?.node_type || "").toLowerCase();
  const orderA = kindOrder[kindA] ?? 20;
  const orderB = kindOrder[kindB] ?? 20;
  return orderA - orderB || String(a.title || "").localeCompare(String(b.title || ""));
}

function filterNeo4jDisplayEdges(edges, nodes) {
  const hasStructureEdges = edges.some((edge) => edge.type === "STRUCTURE_EDGE");
  if (!hasStructureEdges) return edges;
  const byId = new Map(nodes.map((node) => [node.id, node]));
  return edges.filter((edge) => {
    if (edge.type === "STRUCTURE_EDGE") return true;
    if (edge.type !== "HAS_STRUCTURE_NODE") return true;
    const target = byId.get(edge.target);
    return target && isNeo4jStructureNode(target) && !String(target.properties?.parent_node_id || "").trim();
  });
}

function getNeo4jNodeAttrs(node, isNew) {
  const generated = node.properties?.is_generated === true;
  const stateLabel = generated ? "DONE" : "TODO";
  const palette = {
    Domain: { fill: "#edf6ee", stroke: "#1e7b64", kind: "#1e7b64" },
    SubTopic: { fill: "#f2f6fb", stroke: "#2f5f91", kind: "#2f5f91" },
    Article: { fill: "#fff8e8", stroke: "#bb8b27", kind: "#8a6517" },
    Entity: { fill: "#fff3ef", stroke: "#a9483f", kind: "#a9483f" },
    KnowledgeStructureNode: { fill: generated ? "#f1f8f2" : "#fbf8ee", stroke: generated ? "#1e7b64" : "#5d6a66", kind: generated ? "#1e7b64" : "#5d6a66" },
  }[node.type] || { fill: "#fffdf8", stroke: "#d8d1c2", kind: "#5d6a66" };
  return {
    body: {
      rx: 8,
      ry: 8,
      fill: palette.fill,
      stroke: isNew ? "#17211f" : palette.stroke,
      strokeWidth: isNew ? 3 : 1.5,
      filter: isNew ? "drop-shadow(0 10px 16px rgba(23, 33, 31, 0.18))" : "none",
    },
    kind: {
      text: `${stateLabel} · ${formatNeo4jNodeKind(node)}`,
      fill: palette.kind,
      fontSize: 11,
      fontWeight: 900,
      refX: 12,
      refY: 11,
      textAnchor: "start",
      textVerticalAnchor: "top",
    },
    title: {
      text: node.title || node.id,
      fill: "#17211f",
      fontSize: 14,
      fontWeight: 850,
      refX: 12,
      refY: 31,
      textAnchor: "start",
      textVerticalAnchor: "top",
      textWrap: { width: -24, height: 28, ellipsis: true },
    },
    path: {
      text: node.properties?.generated_path || node.path || node.properties?.id || node.id,
      fill: "#5d6a66",
      fontSize: 11,
      fontWeight: 700,
      refX: 12,
      refY: 60,
      textAnchor: "start",
      textVerticalAnchor: "top",
      textWrap: { width: -24, height: 18, ellipsis: true },
    },
  };
}

function formatNeo4jNodeKind(node) {
  return node.properties?.node_type || node.type || "Node";
}

function getNeo4jEdgeAttrs(isNew, edgeType = "") {
  return {
    line: {
      stroke: edgeType === "STRUCTURE_EDGE" ? "#7f8c86" : isNew ? "#17211f" : "#b4beb8",
      strokeWidth: edgeType === "STRUCTURE_EDGE" ? 1.6 : isNew ? 2.4 : 1.4,
      targetMarker: { name: "classic", size: 8 },
      strokeDasharray: edgeType === "STRUCTURE_EDGE" ? "" : "7 5",
    },
  };
}

function setNeo4jGraphStatus(status, label) {
  if (neo4jGraphStatusLabel) neo4jGraphStatusLabel.textContent = label;
  if (!neo4jGraphDot) return;
  neo4jGraphDot.classList.remove("ok", "fail", "loading");
  if (status === "ok") neo4jGraphDot.classList.add("ok");
  else if (status === "unavailable") neo4jGraphDot.classList.add("fail");
  else if (status === "loading") neo4jGraphDot.classList.add("loading");
}

function renderNeo4jGraphMetrics(payload) {
  if (!neo4jGraphMetrics) return;
  const graph = normalizeGraphPayload(payload.graph || payload.graph_snapshot);
  const nodes = graph.nodes;
  const edges = graph.edges;
  const generated = nodes.filter((node) => node.properties?.is_generated === true).length;
  const lastUpdated = payload.refreshed_at ? `刷新：${payload.refreshed_at}` : "刷新：暂无";
  neo4jGraphMetrics.innerHTML = `
    <span>领域：${escapeHtml(payload.domain || "暂无")}</span>
    <span>节点 ${escapeHtml(String(nodes.length))}</span>
    <span>关系 ${escapeHtml(String(edges.length))}</span>
    <span>已落实 ${escapeHtml(String(generated))}</span>
    <span>${escapeHtml(lastUpdated)}</span>`;
}

function renderNeo4jGraphFallback(message) {
  if (!neo4jGraphContainer) return;
  neo4jGraphContainer.innerHTML = `<div class="neo4j-graph-empty">${escapeHtml(message)}</div>`;
}

function renderQueuePanel(payload) {
  if (!queueOutput) return;
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const generation = payload.generation_progress || payload.task?.generation_progress || queue.generation_status || {};
  const tasks = Array.isArray(queue.tasks) ? queue.tasks : [];
  const rounds = Array.isArray(queue.round_summaries) ? queue.round_summaries : [];
  const counts = summarizeQueueTaskCounts(tasks);
  const runningTask = tasks.find((task) => task.status === "running");

  if (queuePanelHint) {
    queuePanelHint.textContent = buildQueueStatusHint(queue.final_status, queue.current_round, runningTask);
  }

  if (!Object.keys(generation).length && !tasks.length) {
    queueOutput.innerHTML = '<div class="empty-state">暂无文件生成或查询队列状态。</div>';
    return;
  }

  const cards = [
    `<article class="plan-card active">
      <div class="plan-card-head">
        <span class="checkmark" aria-hidden="true"></span>
        <div>
          <strong>图谱上下文进度</strong>
          <span>${escapeHtml(`${generation.completed_files || 0}/${generation.total_files || 0} 节点`)}</span>
        </div>
      </div>
      <div class="plan-query">${escapeHtml(generation.current_file || "等待生成任务")}</div>
      <div class="plan-lists">
        <div><b>最近保存</b><ul><li>${escapeHtml(generation.last_saved_path || "暂无")}</li></ul></div>
        <div><b>当前轮次</b><ul><li>${escapeHtml(String(queue.current_round || 1))}</li></ul></div>
      </div>
    </article>`,
    `<article class="plan-card active">
      <div class="plan-card-head">
        <span class="checkmark" aria-hidden="true"></span>
        <div>
          <strong>查询队列概况</strong>
          <span>${escapeHtml(buildQueueCountLabel(counts))}</span>
        </div>
      </div>
      <div class="plan-query">${escapeHtml(runningTask?.query_text || "当前没有运行中的队列任务")}</div>
      <div class="plan-lists">
        <div><b>当前任务</b><ul><li>${escapeHtml(runningTask?.task_id || "暂无")}</li></ul></div>
        <div><b>目标位置</b><ul><li>${escapeHtml(runningTask?.target_file_path || "暂无")}</li></ul></div>
      </div>
    </article>`,
  ];

  if (rounds.length) {
    const lastRound = rounds.at(-1);
    cards.push(`<article class="plan-card active">
      <div class="plan-card-head">
        <span class="checkmark" aria-hidden="true"></span>
        <div>
          <strong>轮次验证记录</strong>
          <span>${escapeHtml(`${rounds.length} 轮`)}</span>
        </div>
      </div>
      <div class="plan-query">${escapeHtml(lastRound?.reasoning || "暂无验证摘要")}</div>
      <div class="plan-lists">
        <div><b>最近一轮</b><ul><li>${escapeHtml(formatRoundSummary(lastRound))}</li></ul></div>
        <div><b>缺口数量</b><ul><li>${escapeHtml(String((lastRound?.missing_evidence || []).length))}</li></ul></div>
      </div>
    </article>`);
  }

  tasks.slice(0, 20).forEach((item) => {
    const done = item.status === "completed";
    const active = item.status === "running";
    const statusLabel = done ? "已完成" : active ? "执行中" : item.status === "insufficient" ? "需补充" : "待执行";
    const citations = (item.citations || []).map((citation) => `<li>${escapeHtml(citation.title || citation.url || "来源")}</li>`).join("");
    const expected = (item.expected_evidence || []).map((value) => `<li>${escapeHtml(value)}</li>`).join("");
    cards.push(`<article class="plan-card ${done ? "done" : active ? "active" : "pending"}">
      <div class="plan-card-head">
        <span class="checkmark" aria-hidden="true">${done ? "✓" : ""}</span>
        <div>
          <strong>${escapeHtml(item.task_type || "task")} · ${escapeHtml(item.task_id || "")}</strong>
          <span>${escapeHtml(statusLabel)}</span>
        </div>
      </div>
      <div class="plan-query">${escapeHtml(item.query_text || item.claim_or_gap || "")}</div>
      <div class="plan-lists">
        <div><b>目标文件</b><ul><li>${escapeHtml(item.target_file_path || "")}</li></ul></div>
        <div><b>预期补充</b><ul>${expected || "<li>未提供</li>"}</ul></div>
      </div>
      ${citations ? `<div class="plan-saves"><b>已收集来源</b><ul>${citations}</ul></div>` : ""}
    </article>`);
  });

  queueOutput.innerHTML = cards.join("");
}

function renderLearningPlan(payload) {
  if (!learningPlanOutput) return;
  const plan = payload.learning_plan || payload.task?.learning_plan || {};
  const stages = Array.isArray(plan.stages) ? plan.stages : [];
  if (!stages.length) {
    learningPlanOutput.innerHTML = '<div class="empty-state">暂无学习计划。点击“生成学习计划”后会按图谱层级生成路线。</div>';
    return;
  }
  const evidence = plan.evidence_summary || {};
  const header = `
    <article class="learning-plan-overview">
      <strong>${escapeHtml(plan.domain || "知识领域")} 学习路线</strong>
      <p>${escapeHtml(plan.mastery_target || "围绕当前知识图谱完成由浅入深学习。")}</p>
      <div class="learning-plan-meta">
        <span>主题 ${escapeHtml(String(plan.graph_summary?.topic_count || 0))}</span>
        <span>证据就绪 ${escapeHtml(String(evidence.ready_count || 0))}</span>
        <span>待补证据 ${escapeHtml(String(evidence.pending_count || 0))}</span>
      </div>
    </article>`;
  const stageCards = stages
    .map((stage) => {
      const topics = Array.isArray(stage.topics) ? stage.topics : [];
      const topicItems = topics.slice(0, 8).map((topic) => renderLearningPlanTopic(topic)).join("");
      const focus = Array.isArray(stage.focus_subdomains) ? stage.focus_subdomains.filter(Boolean).join("、") : "";
      return `
        <article class="learning-stage-card">
          <div class="learning-stage-head">
            <span>${escapeHtml(String(stage.order || ""))}</span>
            <div>
              <strong>${escapeHtml(stage.title || "学习阶段")}</strong>
              <small>${escapeHtml([stage.level, stage.estimated_effort].filter(Boolean).join(" · "))}</small>
            </div>
          </div>
          <p>${escapeHtml(stage.objective || "")}</p>
          ${focus ? `<div class="learning-focus">细分领域：${escapeHtml(focus)}</div>` : ""}
          <ul class="learning-topic-list">${topicItems || "<li>暂无明确主题，先复盘前一阶段产物。</li>"}</ul>
          <div class="learning-stage-task"><b>练习</b>${escapeHtml(stage.practice || "")}</div>
          <div class="learning-stage-task"><b>检查点</b>${escapeHtml(stage.checkpoint || "")}</div>
        </article>`;
    })
    .join("");
  learningPlanOutput.innerHTML = `${header}${stageCards}`;
}

function renderLearningPlanTopic(topic) {
  const evidenceStatus = topic.evidence_status === "ready" ? "证据已就绪" : "待补证据";
  const link = (Array.isArray(topic.evidence) ? topic.evidence : []).find((item) => item.selected_link)?.selected_link || "";
  return `
    <li>
      <strong>${escapeHtml(topic.title || topic.node_id || "知识点")}</strong>
      <span>${escapeHtml([topic.learning_role, topic.relative_path].filter(Boolean).join(" · "))}</span>
      <em class="${topic.evidence_status === "ready" ? "ready" : "pending"}">${escapeHtml(evidenceStatus)}</em>
      ${link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noreferrer">证据来源</a>` : ""}
    </li>`;
}

function summarizeGenerationProgress(payload) {
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const generation = payload.generation_progress || payload.task?.generation_progress || queue.generation_status || {};
  if (!Object.keys(generation).length) return "";
  return `${generation.completed_files || 0}/${generation.total_files || 0} 图谱上下文已准备`;
}

function summarizeCurrentFile(payload) {
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const generation = payload.generation_progress || payload.task?.generation_progress || queue.generation_status || {};
  return generation.current_file || generation.last_saved_path || "";
}

function summarizeCurrentEvidenceTask(payload) {
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const tasks = Array.isArray(queue.tasks) ? queue.tasks : [];
  const running = tasks.find((task) => task.status === "running");
  return running ? `${running.task_id || ""} ${running.query_text || ""}`.trim() : "";
}

function summarizeGraphCompletion(payload) {
  const graph = payload.graph_snapshot || state.neo4jGraphSnapshot?.graph || {};
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  if (!nodes.length) return "";
  const completed = nodes.filter((node) => node.properties?.is_completed === true || node.properties?.generation_state === "completed").length;
  return `${completed}/${nodes.length} 节点完成`;
}

function summarizeParentGraphStatus(payload) {
  const graph = payload.graph_snapshot || state.neo4jGraphSnapshot?.graph || {};
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const parent = nodes.find((node) => node.properties?.node_type === "domain") || nodes.find((node) => node.type === "Domain");
  if (!parent) return "";
  return `${parent.title || "Domain"} · ${parent.properties?.generation_state || ""}`;
}

function summarizeQueueProgress(payload) {
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const tasks = Array.isArray(queue.tasks) ? queue.tasks : [];
  if (!tasks.length) return "";
  return buildQueueCountLabel(summarizeQueueTaskCounts(tasks));
}

function summarizeValidationRounds(payload) {
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const rounds = Array.isArray(queue.round_summaries) ? queue.round_summaries : [];
  if (!rounds.length) return "";
  return formatRoundSummary(rounds.at(-1));
}

function summarizeQueueTaskCounts(tasks) {
  return {
    total: tasks.length,
    completed: tasks.filter((task) => task.status === "completed").length,
    running: tasks.filter((task) => task.status === "running").length,
    pending: tasks.filter((task) => task.status === "pending").length,
    insufficient: tasks.filter((task) => task.status === "insufficient").length,
  };
}

function buildQueueCountLabel(counts) {
  if (!counts.total) return "暂无任务";
  const labels = [`${counts.completed}/${counts.total} 完成`];
  if (counts.running) labels.push(`${counts.running} 执行中`);
  if (counts.pending) labels.push(`${counts.pending} 待执行`);
  if (counts.insufficient) labels.push(`${counts.insufficient} 需补充`);
  return labels.join("，");
}

function buildQueueStatusHint(finalStatus, currentRound, runningTask) {
  const labels = {
    pending: "等待生成",
    generated: "文件生成完成",
    needs_more_evidence: "等待下一轮补充",
    ready_for_fill: "可执行统一回填",
  };
  const parts = [];
  if (finalStatus) parts.push(`队列状态：${labels[finalStatus] || finalStatus}`);
  if (currentRound) parts.push(`第 ${currentRound} 轮`);
  if (runningTask?.task_id) parts.push(`当前任务：${runningTask.task_id}`);
  return parts.join(" · ");
}

function formatRoundSummary(round) {
  if (!round) return "暂无验证结果";
  const status = round.is_complete ? "已完成" : "待补充";
  return `第 ${round.round_number || "?"} 轮 · ${status}`;
}

function summarizeTokenUsageLabel(payload) {
  const usage = payload.token_usage || payload.task?.token_usage;
  if (!usage || !usage.request_count) return "";
  return `${formatNumber(usage.total_tokens)} total / ${formatNumber(usage.request_count)} 次调用`;
}

function summarizeTaskTiming(payload) {
  const timing = payload.task_timing || payload.task?.task_timing || {};
  const startedAt = timing.started_at || payload.started_at || payload.task?.started_at;
  const dynamicSeconds = timing.is_running && startedAt ? secondsSince(startedAt) : null;
  const seconds = dynamicSeconds ?? Number(timing.elapsed_seconds);
  if (Number.isFinite(seconds) && seconds > 0) {
    const suffix = formatTaskTimingStatus(payload, timing);
    return `${formatDuration(seconds)} · ${suffix}`;
  }
  if (startedAt) return `0 秒 · ${formatTaskTimingStatus(payload, timing)}`;
  return "";
}

function formatTaskTimingStatus(payload, timing = {}) {
  if (timing.is_running) return "运行中";
  const status = payload.task_status || payload.status || payload.task?.task_status || payload.intake_session?.status || "";
  return {
    graph_ready: "图谱已生成，待查询填充",
    verified: "已完成",
    repair_required: "待系统修复",
    research_required: "待补检索",
    supplement_required: "待补充",
    max_rounds_reached: "已停止",
    failed: "失败",
    plan_failed: "计划失败",
  }[status] || "已停止";
}

function secondsSince(isoTimestamp) {
  const started = Date.parse(isoTimestamp);
  if (!Number.isFinite(started)) return null;
  return Math.max(0, Math.floor((Date.now() - started) / 1000));
}

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const restSeconds = seconds % 60;
  const parts = [];
  if (hours) parts.push(`${hours} 小时`);
  if (minutes) parts.push(`${minutes} 分钟`);
  if (restSeconds || !parts.length) parts.push(`${restSeconds} 秒`);
  return parts.join(" ");
}

function summarizeQueueCountSummary(counts = {}) {
  const total = Number(counts.total || 0);
  if (!total) return "";
  return [
    `总 ${formatNumber(total)}`,
    `待处理 ${formatNumber(counts.pending || 0)}`,
    `运行中 ${formatNumber(counts.running || 0)}`,
    `完成 ${formatNumber(counts.completed || 0)}`,
    `补充 ${formatNumber(counts.insufficient || 0)}`,
  ].join(" · ");
}

function summarizeLatestLlm(details = {}) {
  const operation = details.operation || "";
  const status = details.status || "";
  if (!operation && !status) return "";
  const parts = [operation, status];
  if (details.attempt && details.max_attempts) parts.push(`第 ${details.attempt}/${details.max_attempts} 次`);
  if (details.error) parts.push(details.error);
  return parts.filter(Boolean).join(" · ");
}

function renderTokenUsage(payload) {
  if (!tokenUsageOutput) return;
  const usage = payload.token_usage || payload.task?.token_usage || {};
  const totalTokens = usage.total_tokens || 0;
  if (tokenFloatTotal) tokenFloatTotal.textContent = formatNumber(totalTokens);
  if (!usage.request_count) {
    tokenUsageOutput.innerHTML = '<div class="empty-state">暂无 token 记录。</div>';
    return;
  }
  tokenUsageOutput.innerHTML = `
    <div class="token-metrics">
      <div class="token-metric"><span>发送</span><strong>${escapeHtml(formatNumber(usage.prompt_tokens))}</strong></div>
      <div class="token-metric"><span>接收</span><strong>${escapeHtml(formatNumber(usage.completion_tokens))}</strong></div>
      <div class="token-metric"><span>总计</span><strong>${escapeHtml(formatNumber(usage.total_tokens))}</strong></div>
      <div class="token-metric"><span>调用</span><strong>${escapeHtml(formatNumber(usage.request_count))}</strong></div>
    </div>`;
}

function renderExecutionLog(payload) {
  if (!executionLogOutput) return;
  const logs = payload.logs || payload.execution_log || payload.task?.execution_log || [];
  if (!logs.length) {
    executionLogOutput.innerHTML = '<div class="empty-state">暂无调用或执行日志。</div>';
    return;
  }
  executionLogOutput.innerHTML = logs
    .slice(-36)
    .map((entry) => renderExecutionLogEntry(entry))
    .join("");
}

function renderExecutionLogEntry(entry) {
  const event = entry.event || "event";
  const timestamp = entry.timestamp || "";
  const details = entry.details || {};
  const agent = entry.agent || details.agent || "";
  const meta = [
    timestamp,
    agent,
    details.operation,
    details.step_id,
    details.task_id,
    details.status,
  ].filter(Boolean).join(" · ");
  const highlights = buildLogHighlights(details);
  const error = details.error ? `<div class="trace-error">${escapeHtml(String(details.error))}</div>` : "";
  const detailBlock = highlights.length
    ? `<div class="trace-meta-grid">${highlights.map(([label, value]) => `<span><strong>${escapeHtml(label)}</strong>${escapeHtml(String(value))}</span>`).join("")}</div>`
    : "";
  const rawJson = `<code>${escapeHtml(JSON.stringify(details, null, 2))}</code>`;
  return `<div class="trace-item ${details.error ? "is-error" : ""}"><strong>${escapeHtml(event)}</strong><span>${escapeHtml(meta)}</span>${detailBlock}${error}${rawJson}</div>`;
}

function buildLogHighlights(details = {}) {
  const items = [
    ["文件", details.file_path || details.target_file_path],
    ["章节", details.target_section],
    ["查询", details.query || details.query_text],
    ["轮次", details.round_number || details.round],
    ["尝试", details.attempt && details.max_attempts ? `${details.attempt}/${details.max_attempts}` : details.attempts],
    ["来源数", details.document_count],
    ["任务类型", details.task_type],
    ["当前文件", details.current_file],
  ];
  return items.filter(([, value]) => value !== undefined && value !== null && value !== "");
}

function renderTaskList(payload) {
  if (!taskListOutput) return;
  const tasks = payload.tasks || payload.task_list || [];
  if (!tasks.length) {
    taskListOutput.innerHTML = '<div class="empty-state">暂无已保存任务。</div>';
    return;
  }
  taskListOutput.innerHTML = tasks
    .map((task) => {
      const title = task.domain || task.normalized_domain || task.task_id;
      const meta = [task.task_status, task.version, task.updated_at].filter(Boolean).join(" · ");
      const subdomains = Array.isArray(task.subdomains) ? task.subdomains.join(", ") : "";
      return `<button class="task-list-item" type="button" data-task-id="${escapeHtml(task.task_id)}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(meta)}</span><small>${escapeHtml(subdomains || task.document_path || task.task_id)}</small></button>`;
    })
    .join("");
  taskListOutput.querySelectorAll("[data-task-id]").forEach((button) => {
    button.addEventListener("click", () => {
      taskIdInput.value = button.dataset.taskId || "";
      fillTaskUpdateForm(button.dataset.taskId || "");
    });
  });
}

function fillTaskUpdateForm(taskId) {
  if (!taskId || !state.lastPayload) return;
  const tasks = state.lastPayload.tasks || state.lastPayload.task_list || [];
  const task = tasks.find((item) => item.task_id === taskId);
  if (!task) return;
  taskUpdateInput.value = JSON.stringify({
    request_context: {
      domain: task.domain || task.normalized_domain || "",
      normalized_domain: task.normalized_domain || task.domain || "",
      subdomains: task.subdomains || [],
    },
    task_status: task.task_status || "",
    management_note: "人工调整任务信息",
  }, null, 2);
}

function stopTaskStream() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
  state.pollTaskId = null;
}

function startTaskStream(taskId) {
  stopTaskStream();
  state.pollTaskId = taskId;
  const es = new EventSource(`/tasks/${encodeURIComponent(taskId)}/stream`);
  state.eventSource = es;

  es.onmessage = (e) => {
    try {
      const payload = JSON.parse(e.data);
      if (payload.error) { showError(new Error(payload.error)); stopTaskStream(); return; }
      const merged = mergeTaskPayload(payload);
      showPayload(merged);
      if (hasGraphPayload(merged.graph_snapshot)) {
        renderNeo4jGraphSnapshot(
          {
            task_id: getTaskIdFromPayload(merged),
            domain: merged.request_context?.domain || merged.domain || "本地任务图",
            status: "local",
            refreshed_at: merged.graph_event?.timestamp || merged.updated_at,
            graph: merged.graph_snapshot,
          },
          state.neo4jGraphSnapshot,
        );
        state.neo4jGraphSnapshot = {
          status: "local",
          graph: merged.graph_snapshot,
        };
      }
    } catch (err) {
      showError(err);
      stopTaskStream();
    }
  };

  es.addEventListener("done", () => {
    stopTaskStream();
  });

  es.onerror = () => {
    showError(new Error("SSE 连接断开"));
    stopTaskStream();
  };
}

function isTerminalStatus(status) {
  return ["graph_ready", "verified", "research_required", "repair_required", "supplement_required", "max_rounds_reached", "failed", "plan_failed"].includes(status);
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number.toLocaleString("en-US") : "0";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function refreshStatus() {
  try {
    const health = await requestJson("/health");
    healthDot.classList.remove("fail");
    healthDot.classList.add("ok");
    healthLabel.textContent = health.status === "ok" ? "运行正常" : health.status;
  } catch {
    healthDot.classList.remove("ok");
    healthDot.classList.add("fail");
    healthLabel.textContent = "连接失败";
  }

  try {
    renderConfig(await requestJson("/config/status"));
  } catch (error) {
    if (configGrid) configGrid.innerHTML = `<div class="empty-state">配置状态读取失败：${escapeHtml(error.message)}</div>`;
  }
}

document.querySelector("#refresh-status").addEventListener("click", refreshStatus);

if (tokenFloatToggle && tokenFloat) {
  tokenFloatToggle.addEventListener("click", () => {
    const collapsed = tokenFloat.classList.toggle("collapsed");
    tokenFloatToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  });
}

if (neo4jAutoFollowInput) {
  state.neo4jAutoFollow = neo4jAutoFollowInput.checked;
  neo4jAutoFollowInput.addEventListener("change", () => {
    state.neo4jAutoFollow = neo4jAutoFollowInput.checked;
    if (state.neo4jAutoFollow) scheduleNeo4jGraphRefresh(getTaskIdFromPayload(state.lastPayload), { force: true });
  });
}

if (refreshNeo4jGraphButton) {
  refreshNeo4jGraphButton.addEventListener("click", () => refreshNeo4jGraph(getTaskIdFromPayload(state.lastPayload), { force: true }));
}

document.querySelector("#create-intake-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = form.elements.message.value.trim();
  setBusy(form, true);
  try {
    showPayload(await requestJson("/intake/sessions", { method: "POST", body: JSON.stringify({ message }) }));
  } catch (error) {
    showError(error);
  } finally {
    setBusy(form, false);
  }
});

document.querySelector("#append-intake-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const sessionId = form.elements.session_id.value.trim();
  const message = form.elements.message.value.trim();
  setBusy(form, true);
  try {
    showPayload(await requestJson(`/intake/sessions/${encodeURIComponent(sessionId)}/messages`, { method: "POST", body: JSON.stringify({ message }) }));
  } catch (error) {
    showError(error);
  } finally {
    setBusy(form, false);
  }
});

document.querySelector("#confirm-intake").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const sessionId = intakeSessionInput.value.trim();
  setBusy(button, true);
  try {
    const payload = await requestJson(`/intake/sessions/${encodeURIComponent(sessionId)}/confirm`, { method: "POST" });
    showPayload(payload);
    const taskId = payload.task?.task_id || payload.task_id || payload.intake_session?.task_id;
    if (taskId) startTaskStream(taskId);
    else stopTaskStream();
  } catch (error) {
    showError(error);
    stopTaskStream();
  } finally {
    setBusy(button, false);
  }
});

document.querySelector("#direct-task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  setBusy(form, true);
  try {
    const payload = JSON.parse(form.elements.payload.value);
    const task = await requestJson("/tasks/async", { method: "POST", body: JSON.stringify(payload) });
    showPayload(task);
    const createdTaskId = task.task_id || task.task?.task_id;
    if (createdTaskId) startTaskStream(createdTaskId);
    else stopTaskStream();
  } catch (error) {
    showError(error);
    stopTaskStream();
  } finally {
    setBusy(form, false);
  }
});

document.querySelectorAll("[data-task-action]").forEach((button) => {
  button.addEventListener("click", async () => {
    const taskId = taskIdInput.value.trim();
    const action = button.dataset.taskAction;
    if (action !== "list" && !taskId) {
      showError(new Error("请先选择或输入 Task ID。"));
      return;
    }
    const route = {
      list: ["/tasks", "GET"],
      get: [`/tasks/${encodeURIComponent(taskId)}`, "GET"],
      queue: [`/tasks/${encodeURIComponent(taskId)}/plan`, "GET"],
      resume: [`/tasks/${encodeURIComponent(taskId)}/resume`, "POST"],
      frozen: [`/tasks/${encodeURIComponent(taskId)}/frozen`, "GET"],
      "fill-evidence": [`/tasks/${encodeURIComponent(taskId)}/evidence/fill`, "POST"],
      "learning-plan": [`/tasks/${encodeURIComponent(taskId)}/learning-plan`, "POST"],
      "complete-documents": [`/tasks/${encodeURIComponent(taskId)}/documents/complete`, "POST"],
      report: [`/tasks/${encodeURIComponent(taskId)}/report`, "POST"],
      logs: [`/tasks/${encodeURIComponent(taskId)}/logs`, "GET"],
    }[action];

    setBusy(button, true);
    try {
      const payload = await requestJson(route[0], { method: route[1] });
      showPayload(payload);
      const activeTaskId = payload.task_id || payload.task?.task_id || taskId;
      if (activeTaskId && ["get", "queue", "logs", "resume", "fill-evidence", "learning-plan", "complete-documents"].includes(action)) {
        scheduleNeo4jGraphRefresh(activeTaskId, { force: true });
      }
      if (["get", "queue", "logs", "resume", "fill-evidence"].includes(action) && activeTaskId && !isTerminalStatus(payload.task_status || payload.task?.task_status)) {
        startTaskStream(activeTaskId);
      }
    } catch (error) {
      showError(error);
    } finally {
      setBusy(button, false);
    }
  });
});

document.querySelector("#initialize-system")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const confirmed = window.confirm(
    "确认初始化开发环境？这会清空任务、session、audit、冻结版本、save/ 生成文件和 KnowledgeForge Neo4j 图谱；不会清理代码、配置、项目文档、依赖、ChromaDB、MySQL 或应用日志。"
  );
  if (!confirmed) return;
  setBusy(button, true);
  try {
    stopTaskStream();
    const payload = await requestJson("/system/initialize", { method: "POST" });
    taskIdInput.value = "";
    intakeSessionInput.value = "";
    state.neo4jGraphSnapshot = { status: "local", graph: { nodes: [], edges: [] } };
    renderNeo4jGraphSnapshot({ status: "local", domain: "暂无", graph: { nodes: [], edges: [] } }, null);
    showPayload(payload);
  } catch (error) {
    showError(error);
  } finally {
    setBusy(button, false);
  }
});

document.querySelector("#task-manage-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const taskId = taskIdInput.value.trim();
  setBusy(form, true);
  try {
    const payload = JSON.parse(form.elements.payload.value);
    showPayload(await requestJson(`/tasks/${encodeURIComponent(taskId)}`, { method: "PATCH", body: JSON.stringify(payload) }));
  } catch (error) {
    showError(error);
  } finally {
    setBusy(form, false);
  }
});

document.querySelector("#delete-task").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const taskId = taskIdInput.value.trim();
  if (!taskId) {
    showError(new Error("请先选择或输入 Task ID。"));
    return;
  }
  if (!window.confirm(`确认删除任务 ${taskId}？`)) return;
  setBusy(button, true);
  try {
    stopTaskStream();
    const deleted = await requestJson(`/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
    const listed = await requestJson("/tasks");
    showPayload({ ...deleted, tasks: listed.tasks, count: listed.count });
  } catch (error) {
    showError(error);
  } finally {
    setBusy(button, false);
  }
});

refreshStatus();
initializeWorkflowMap();
renderNeo4jGraphSnapshot({ status: "local", domain: "暂无", graph: { nodes: [], edges: [] } }, null);

window.setInterval(() => {
  if (state.lastPayload?.task_timing?.is_running || state.lastPayload?.task?.task_timing?.is_running) {
    renderSummary(state.lastPayload);
  }
}, 1000);

window.addEventListener("resize", () => {
  if (state.workflowGraphReady) renderWorkflowMap(state.lastPayload || {});
  if (state.neo4jGraphSnapshot) renderNeo4jGraphSnapshot(state.neo4jGraphSnapshot, state.neo4jGraphSnapshot);
});
