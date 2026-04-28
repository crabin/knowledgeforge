const state = {
  lastPayload: null,
  pollTimer: null,
  pollTaskId: null,
  pollCount: 0,
  workflowGraph: null,
  workflowGraphReady: false,
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

const workflowSteps = [
  { id: "blueprint_ready", order: "01", title: "蓝图准备", description: "根据固定模板准备目标文件清单与目录结构。" },
  { id: "llm_generating", order: "02", title: "LLM 生成", description: "严格串行地生成单个知识文件骨架，并提取查询任务。" },
  { id: "query_queue_running", order: "03", title: "查询队列", description: "按队列一次执行一个 Query / Media 任务。" },
  { id: "round_validation", order: "04", title: "轮次验证", description: "每轮查询结束后评估是否完整或需要补充。" },
  { id: "evidence_filling", order: "05", title: "统一回填", description: "全部任务完成后统一把依据回写到目标 Markdown。" },
  { id: "governing", order: "06", title: "治理质检", description: "抽取、Neo4j 路径关联、质量检测和回流分类。" },
  { id: "versioning", order: "07", title: "版本与研报", description: "冻结通过质量检测的版本，并基于冻结知识生成研报。" },
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
    ["当前步骤", payload.current_step || payload.task?.current_step],
    ["当前动作", payload.current_action || payload.task?.current_action],
    ["生成进度", summarizeGenerationProgress(payload)],
    ["队列进度", summarizeQueueProgress(payload)],
    ["轮次验证", summarizeValidationRounds(payload)],
    ["队列状态", queueSummary.final_status],
    ["队列统计", summarizeQueueCounts(queueSummary.counts)],
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
  return payload.current_step || payload.task?.current_step || events.at(-1)?.step_id || "blueprint_ready";
}

function renderWorkflowMap(payload) {
  const events = normalizeWorkflowEvents(payload);
  const byStep = new Map(events.map((event) => [event.step_id, event]));
  const current = getCurrentWorkflowStep(payload, events);
  renderWorkflowFallback(byStep, current);
  renderWorkflowX6(byStep, current);
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
    step.classList.toggle("active", status === "active");
    step.classList.toggle("focused", status === "active");
    step.classList.toggle("done", status === "completed");
    step.classList.toggle("blocked", event?.status === "blocked");
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
  graph.centerContent({ padding: 16 });
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
  const compact = width < 920;
  const nodeWidth = compact ? Math.max(180, width - 48) : 204;
  const nodeHeight = compact ? 122 : 118;
  const gapX = compact ? 0 : Math.max(22, Math.floor((width - 48 - nodeWidth * 4) / 3));
  const startX = 24;
  const startY = 24;
  const rowGap = compact ? 18 : 42;
  const columnGap = compact ? 0 : nodeWidth + gapX;
  const nodes = workflowSteps.map((step, index) => {
    const position = getWorkflowPosition(index, compact, startX, startY, nodeWidth, nodeHeight, columnGap, rowGap);
    const status = getWorkflowStepStatus(step.id, byStep, current);
    return {
      id: step.id,
      shape: "rect",
      x: position.x,
      y: position.y,
      width: nodeWidth,
      height: nodeHeight,
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
      source: step.id,
      target: next.id,
      router: compact ? { name: "manhattan" } : { name: "orth" },
      connector: { name: "rounded" },
      attrs: getWorkflowEdgeAttrs(edgeStatus),
    };
  });
  const rows = compact ? workflowSteps.length : Math.ceil(workflowSteps.length / 4);
  const height = startY * 2 + rows * nodeHeight + Math.max(0, rows - 1) * rowGap;
  return { nodes, edges, meta: { height } };
}

function getWorkflowPosition(index, compact, startX, startY, nodeWidth, nodeHeight, columnGap, rowGap) {
  if (compact) return { x: startX, y: startY + index * (nodeHeight + rowGap) };
  const row = Math.floor(index / 4);
  const column = index % 4;
  return { x: startX + column * columnGap, y: startY + row * (nodeHeight + rowGap) };
}

function getWorkflowStepStatus(stepId, byStep, current) {
  const event = byStep.get(stepId);
  if (event?.status === "blocked") return "blocked";
  if (stepId === current) return "active";
  if (event?.status === "completed") return "completed";
  return "pending";
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

function renderQueuePanel(payload) {
  if (!queueOutput) return;
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const generation = payload.generation_progress || payload.task?.generation_progress || queue.generation_status || {};
  const tasks = Array.isArray(queue.tasks) ? queue.tasks : [];
  const rounds = Array.isArray(queue.round_summaries) ? queue.round_summaries : [];
  const counts = summarizeQueueCounts(tasks);
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

function summarizeQueueProgress(payload) {
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const tasks = Array.isArray(queue.tasks) ? queue.tasks : [];
  if (!tasks.length) return "";
  return buildQueueCountLabel(summarizeQueueCounts(tasks));
}

function summarizeValidationRounds(payload) {
  const queue = payload.task_queue_snapshot || payload.task?.task_queue_snapshot || {};
  const rounds = Array.isArray(queue.round_summaries) ? queue.round_summaries : [];
  if (!rounds.length) return "";
  return formatRoundSummary(rounds.at(-1));
}

function summarizeQueueCounts(tasks) {
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

function summarizeQueueCounts(counts = {}) {
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

function stopTaskPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
  state.pollTaskId = null;
  state.pollCount = 0;
}

async function refreshRunningTask(taskId) {
  const logsPayload = await requestJson(`/tasks/${encodeURIComponent(taskId)}/logs`);
  let merged = mergeTaskPayload(logsPayload);
  state.pollCount += 1;
  if (state.pollCount % 3 === 0) {
    const taskPayload = await requestJson(`/tasks/${encodeURIComponent(taskId)}`);
    merged = mergeTaskPayload({ ...taskPayload, logs: logsPayload.logs });
    if (isTerminalStatus(taskPayload.task_status)) stopTaskPolling();
  }
  showPayload(merged);
}

function startTaskPolling(taskId) {
  stopTaskPolling();
  state.pollTaskId = taskId;
  state.pollTimer = setInterval(async () => {
    try {
      await refreshRunningTask(taskId);
    } catch (error) {
      stopTaskPolling();
      showError(error);
    }
  }, 900);
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
    if (taskId) startTaskPolling(taskId);
    else stopTaskPolling();
  } catch (error) {
    showError(error);
    stopTaskPolling();
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
    if (createdTaskId) startTaskPolling(createdTaskId);
    else stopTaskPolling();
  } catch (error) {
    showError(error);
    stopTaskPolling();
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
      if (["get", "queue", "logs", "resume"].includes(action) && activeTaskId && !isTerminalStatus(payload.task_status || payload.task?.task_status)) {
        startTaskPolling(activeTaskId);
      }
    } catch (error) {
      showError(error);
    } finally {
      setBusy(button, false);
    }
  });
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
    stopTaskPolling();
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

window.addEventListener("resize", () => {
  if (state.workflowGraphReady) renderWorkflowMap(state.lastPayload || {});
});
