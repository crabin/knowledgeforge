const state = {
  lastPayload: null,
  eventSource: null,
  pollTaskId: null,
  workflowGraph: null,
  workflowGraphReady: false,
  neo4jGraph: null,
  neo4jGraphSnapshot: null,
  neo4jGraphRefreshTimer: null,
  neo4jAutoFollow: true,
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
  { id: "structure_graph_planning", order: "02", title: "图谱规划", description: "根据用户意图生成目录结构图谱。" },
  { id: "llm_generating", order: "03", title: "文件生成", description: "串行生成知识点 Markdown 并同步图谱状态。" },
  { id: "query_queue_running", order: "04", title: "证据查询", description: "按队列执行 Query / Media 证据任务。" },
  { id: "evidence_realtime_write", order: "05", title: "即时回写", description: "每条证据完成后立即更新文件和图谱。" },
  { id: "round_validation", order: "06", title: "父级聚合", description: "验证轮次并聚合子领域与领域完成状态。" },
  { id: "governing", order: "07", title: "治理质检", description: "抽取、Neo4j 路径关联、质量检测和回流分类。" },
  { id: "versioning", order: "08", title: "版本研报", description: "冻结通过质量检测的版本，并基于冻结知识生成研报。" },
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
    ["执行耗时", summarizeTaskTiming(payload)],
    ["当前步骤", payload.current_step || payload.task?.current_step],
    ["当前动作", payload.current_action || payload.task?.current_action],
    ["生成进度", summarizeGenerationProgress(payload)],
    ["队列进度", summarizeQueueProgress(payload)],
    ["当前文件", summarizeCurrentFile(payload)],
    ["当前证据任务", summarizeCurrentEvidenceTask(payload)],
    ["图谱完成", summarizeGraphCompletion(payload)],
    ["父级状态", summarizeParentGraphStatus(payload)],
    ["最近回写", payload.file_update?.path],
    ["轮次验证", summarizeValidationRounds(payload)],
    ["队列状态", queueSummary.final_status],
    ["队列统计", summarizeQueueCountSummary(queueSummary.counts)],
    ["最新 LLM", summarizeLatestLlm(latestLlmDetails)],
    ["最近错误", latestError.error || latestError.event],
    ["文档路径", getNested(payload, "document_artifact.path")],
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
  return normalizeWorkflowStepId(payload.current_step || payload.task?.current_step || events.at(-1)?.step_id || "intent_recognition");
}

function normalizeWorkflowStepId(stepId) {
  const aliases = {
    structure_graph_ready: "structure_graph_planning",
    blueprint_ready: "structure_graph_planning",
    evidence_filling: "evidence_realtime_write",
    planning: "intent_recognition",
    awaiting_confirmation: "intent_recognition",
    collecting: "query_queue_running",
    evaluating: "round_validation",
    writing: "evidence_realtime_write",
  };
  return aliases[stepId] || stepId;
}

function renderWorkflowMap(payload) {
  const events = normalizeWorkflowEvents(payload);
  const byStep = new Map(events.map((event) => [normalizeWorkflowStepId(event.step_id), { ...event, step_id: normalizeWorkflowStepId(event.step_id) }]));
  const current = getCurrentWorkflowStep(payload, events);
  renderWorkflowFallback(byStep, current);
}

function initializeWorkflowMap() {
  renderWorkflowMap(state.lastPayload || {});
}

function renderWorkflowFallback(byStep, current) {
  if (!workflowMap) return;
  workflowMap.querySelectorAll("[data-step-id]").forEach((step) => {
    const stepId = step.dataset.stepId;
    const event = byStep.get(stepId);
    const status = getWorkflowStepStatus(stepId, byStep, current);
    step.dataset.status = status;
    step.dataset.statusLabel = getWorkflowStatusLabel(status);
    step.setAttribute("aria-current", status === "active" ? "step" : "false");
    if (event?.label) step.setAttribute("title", event.label);
    step.classList.toggle("active", status === "active");
    step.classList.toggle("focused", status === "active");
    step.classList.toggle("done", status === "completed");
    step.classList.toggle("pending", status === "pending");
    step.classList.toggle("blocked", status === "blocked");
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
  const nodeWidth = compact ? Math.max(220, width - 48) : Math.max(178, Math.floor((width - 48 - 7 * 22) / 8));
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
    const edgeStatus = targetStatus === "blocked" ? "blocked" : sourceStatus === "completed" ? "completed" : targetStatus === "active" ? "active" : "pending";
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

function getWorkflowStepStatus(stepId, byStep, current) {
  const event = byStep.get(stepId);
  if (event?.status === "blocked") return "blocked";
  if (event?.status === "completed") return "completed";
  if (stepId === current) return "active";
  const stepIndex = workflowSteps.findIndex((step) => step.id === stepId);
  const currentIndex = workflowSteps.findIndex((step) => step.id === current);
  if (stepIndex >= 0 && currentIndex >= 0 && stepIndex < currentIndex) return "completed";
  return "pending";
}

function getWorkflowStatusLabel(status) {
  return {
    completed: "已完成",
    active: "执行中",
    blocked: "需处理",
    pending: "待处理",
  }[status] || "待处理";
}

function getWorkflowNodeAttrs(step, status) {
  const palette = {
    pending: { fill: "#fbf8ee", stroke: "#d8d1c2", title: "#17211f", meta: "#5d6a66" },
    active: { fill: "#edf6ee", stroke: "#1e7b64", title: "#17211f", meta: "#1e7b64" },
    completed: { fill: "#f1f8f2", stroke: "#1e7b64", title: "#17211f", meta: "#1e7b64" },
    blocked: { fill: "#fff3ef", stroke: "#a9483f", title: "#17211f", meta: "#a9483f" },
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
  const color = { pending: "#d8d1c2", active: "#2f5f91", completed: "#1e7b64", blocked: "#a9483f" }[status] || "#d8d1c2";
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
  const x6Graph = ensureNeo4jGraph();
  if (!x6Graph) {
    renderNeo4jGraphFallback(payload.error || "X6 图谱组件未加载。");
    return;
  }
  const previousGraph = normalizeGraphPayload(previousPayload?.graph || previousPayload?.graph_snapshot);
  const previousNodeIds = new Set(previousGraph.nodes.map((node) => node.id));
  const previousEdgeIds = new Set(previousGraph.edges.map((edge) => edge.id));
  const data = buildNeo4jGraphData(graph, previousNodeIds, previousEdgeIds);
  const width = neo4jGraphContainer.clientWidth || 960;
  const viewportHeight = Math.max(520, Math.min(760, Math.round(window.innerHeight * 0.72)));
  neo4jGraphContainer.style.height = `${viewportHeight}px`;
  x6Graph.resize(width, Math.max(viewportHeight, Math.min(data.meta.height, 1800)));
  x6Graph.fromJSON(data);
  if (data.nodes.length) fitGraphToContainer(x6Graph, neo4jGraphContainer, 28, 0.96);
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
  if (state.neo4jGraph) {
    state.neo4jGraph.fromJSON({ nodes: [], edges: [] });
    return;
  }
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
          <strong>LLM 生成进度</strong>
          <span>${escapeHtml(`${generation.completed_files || 0}/${generation.total_files || 0} 文件`)}</span>
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

function summarizeGenerationProgress(payload) {
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const generation = payload.generation_progress || payload.task?.generation_progress || queue.generation_status || {};
  if (!Object.keys(generation).length) return "";
  return `${generation.completed_files || 0}/${generation.total_files || 0} 文件已生成`;
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
    const suffix = timing.is_running ? "运行中" : "已完成";
    return `${formatDuration(seconds)} · ${suffix}`;
  }
  if (startedAt) return "0 秒 · 运行中";
  return "";
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
  return ["verified", "research_required", "repair_required", "supplement_required", "max_rounds_reached", "failed", "plan_failed"].includes(status);
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
      report: [`/tasks/${encodeURIComponent(taskId)}/report`, "POST"],
      logs: [`/tasks/${encodeURIComponent(taskId)}/logs`, "GET"],
    }[action];

    setBusy(button, true);
    try {
      const payload = await requestJson(route[0], { method: route[1] });
      showPayload(payload);
      const activeTaskId = payload.task_id || payload.task?.task_id || taskId;
      if (activeTaskId && ["get", "queue", "logs", "resume"].includes(action)) {
        scheduleNeo4jGraphRefresh(activeTaskId, { force: true });
      }
      if (["get", "queue", "logs", "resume"].includes(action) && activeTaskId && !isTerminalStatus(payload.task_status || payload.task?.task_status)) {
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

window.setInterval(() => {
  if (state.lastPayload?.task_timing?.is_running || state.lastPayload?.task?.task_timing?.is_running) {
    renderSummary(state.lastPayload);
  }
}, 1000);

window.addEventListener("resize", () => {
  if (state.workflowGraphReady) renderWorkflowMap(state.lastPayload || {});
  if (state.neo4jGraphSnapshot) renderNeo4jGraphSnapshot(state.neo4jGraphSnapshot, state.neo4jGraphSnapshot);
});
