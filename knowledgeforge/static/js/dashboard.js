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
const agentPlanOutput = document.querySelector("#agent-plan-output");
const planPanelHint = document.querySelector("#plan-panel-hint");
const tokenUsageOutput = document.querySelector("#token-usage-output");
const tokenFloat = document.querySelector("#token-float");
const tokenFloatToggle = document.querySelector("#token-float-toggle");
const tokenFloatTotal = document.querySelector("#token-float-total");
const executionLogOutput = document.querySelector("#execution-log-output");
const taskListOutput = document.querySelector("#task-list-output");
const workflowMap = document.querySelector("#workflow-map");
const workflowX6Container = document.querySelector("#workflow-x6");

const workflowSteps = [
  { id: "planning", order: "01", title: "计划生成", description: "三路 Agent 基于输入上下文先生成执行计划。" },
  { id: "awaiting_confirmation", order: "02", title: "用户确认", description: "展示 Insight、Query、Media 计划，确认后再执行。" },
  { id: "collecting", order: "03", title: "并行采集", description: "三路能力并行补充内部线索、权威事实与媒体视角。" },
  { id: "realtime_saving", order: "04", title: "实时沉淀", description: "Query / Media 每个合格计划项立即审查并保存 Markdown 草稿。" },
  { id: "evaluating", order: "05", title: "完整性评估", description: "检查核心子主题、可信来源、信息空洞、冲突与时效性。" },
  { id: "writing", order: "06", title: "Markdown 落盘", description: "生成最终综合文档并保留实时保存索引。" },
  { id: "governing", order: "07", title: "治理质检", description: "抽取、Neo4j 路径关联、质量检测和回流分类。" },
  { id: "versioning", order: "08", title: "版本与研报", description: "冻结通过质量检测的版本，并基于冻结知识生成研报。" },
];

async function requestJson(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

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
  renderAgentPlans(payload);
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

function showError(error) {
  const payload = {
    error: error.message,
    status: error.status || "client_error",
    details: error.payload || null,
  };
  output.textContent = JSON.stringify(payload, null, 2);
  renderSummary(payload);
  renderWorkflowMap(payload);
  renderAgentPlans(payload);
  renderTokenUsage(payload);
  renderExecutionLog(payload);
  renderTaskList(payload);
}

function syncKnownIds(payload) {
  const sessionId = payload.session_id || payload.intake_session?.session_id;
  const taskId = payload.task_id || payload.task?.task_id || payload.intake_session?.task_id;

  if (sessionId) {
    intakeSessionInput.value = sessionId;
  }
  if (taskId) {
    taskIdInput.value = taskId;
  }
}

function getNested(payload, path) {
  return path.split(".").reduce((value, key) => {
    if (value && Object.prototype.hasOwnProperty.call(value, key)) {
      return value[key];
    }
    return undefined;
  }, payload);
}

function renderSummary(payload) {
  if (!summaryStrip) return;
  const progress = summarizePlanProgress(payload);
  const realtime = summarizeRealtimeSaves(payload);
  const items = [
    ["Task ID", payload.task_id || payload.task?.task_id || payload.intake_session?.task_id],
    ["Session ID", payload.session_id || payload.intake_session?.session_id],
    ["状态", payload.task_status || payload.status || payload.task?.task_status || payload.intake_session?.status],
    ["当前动作", payload.current_action || payload.task?.current_action],
    ["当前步骤", payload.current_step || payload.task?.current_step],
    ["文档路径", getNested(payload, "document_artifact.path")],
    ["质量检查", getNested(payload, "post_storage_result.quality_check.status")],
    ["冻结版本", getNested(payload, "post_storage_result.version_record.version") || payload.version],
    ["研报资格", getNested(payload, "post_storage_result.version_record.report_eligible")],
    ["错误", payload.error],
    ["计划进度", progress],
    ["实时保存", realtime],
    ["Token", summarizeTokenUsageLabel(payload)],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");

  if (!items.length) {
    summaryStrip.innerHTML = '<div class="empty-state">暂无可提取的关键字段。</div>';
    return;
  }

  summaryStrip.innerHTML = items
    .map(([label, value]) => {
      const rendered = typeof value === "boolean" ? (value ? "是" : "否") : String(value);
      return `<div class="summary-item"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(rendered)}</span></div>`;
    })
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
    .map(([itemKey, itemValue]) => {
      return `<div class="config-row"><span>${escapeHtml(formatConfigLabel(itemKey))}</span>${renderConfigValue(itemValue)}</div>`;
    })
    .join("");
  return `<div class="config-item config-group"><strong>${escapeHtml(label)}</strong>${rows}</div>`;
}

function flattenConfig(value, prefix = "") {
  const rows = [];
  Object.entries(value).forEach(([key, item]) => {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (item && typeof item === "object" && !Array.isArray(item)) {
      rows.push(...flattenConfig(item, nextKey));
    } else {
      rows.push([nextKey, item]);
    }
  });
  return rows;
}

function renderConfigValue(value) {
  if (typeof value === "boolean") {
    return `<span class="${value ? "tone-ok" : "tone-bad"}">${value ? "是" : "否"}</span>`;
  }
  if (Array.isArray(value)) {
    return `<span>${escapeHtml(value.join(", "))}</span>`;
  }
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
  graph.resize(workflowX6Container.clientWidth || 960, workflowX6Container.clientHeight || 360);
  const data = buildWorkflowGraphData(byStep, current);
  graph.fromJSON(data);
  graph.centerContent();
}

function ensureWorkflowGraph() {
  if (!workflowX6Container || !window.X6?.Graph) return null;
  if (state.workflowGraph) return state.workflowGraph;

  const { Graph } = window.X6;
  state.workflowGraph = new Graph({
    container: workflowX6Container,
    width: workflowX6Container.clientWidth || 960,
    height: workflowX6Container.clientHeight || 360,
    panning: true,
    mousewheel: {
      enabled: true,
      modifiers: ["ctrl", "meta"],
    },
    interacting: {
      nodeMovable: false,
      edgeMovable: false,
      arrowheadMovable: false,
      vertexMovable: false,
    },
    background: {
      color: "#fffdf8",
    },
    grid: {
      size: 12,
      visible: true,
      type: "dot",
      args: {
        color: "rgba(23, 33, 31, 0.12)",
      },
    },
  });
  state.workflowGraphReady = true;
  document.body.classList.add("x6-flow-ready");
  return state.workflowGraph;
}

function buildWorkflowGraphData(byStep, current) {
  const width = workflowX6Container?.clientWidth || 960;
  const compact = width < 760;
  const nodeWidth = compact ? Math.min(220, width - 48) : 184;
  const nodeHeight = compact ? 78 : 92;
  const gapX = compact ? 0 : Math.max(32, Math.floor((width - 48 - nodeWidth * 4) / 3));
  const startX = 24;
  const startY = 24;
  const rowGap = compact ? 24 : 58;
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
  return { nodes, edges };
}

function getWorkflowPosition(index, compact, startX, startY, nodeWidth, nodeHeight, columnGap, rowGap) {
  if (compact) {
    return { x: startX, y: startY + index * (nodeHeight + rowGap) };
  }
  const row = Math.floor(index / 4);
  const column = index % 4;
  return {
    x: startX + column * columnGap,
    y: startY + row * (nodeHeight + rowGap),
  };
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
    label: {
      text: `${step.order}  ${step.title}\n${step.description}`,
      fill: palette.title,
      fontSize: 13,
      fontWeight: 800,
      lineHeight: 18,
      refX: 14,
      refY: 15,
      textAnchor: "start",
      textVerticalAnchor: "top",
    },
  };
}

function getWorkflowEdgeAttrs(status) {
  const color = {
    pending: "#d8d1c2",
    active: "#2f5f91",
    completed: "#1e7b64",
    blocked: "#a9483f",
  }[status] || "#d8d1c2";
  return {
    line: {
      stroke: color,
      strokeWidth: status === "active" ? 3 : 2,
      targetMarker: {
        name: "classic",
        size: 8,
      },
      strokeDasharray: status === "pending" ? "6 5" : "",
    },
  };
}

function normalizeWorkflowEvents(payload) {
  const taskEvents = payload.workflow_events || payload.task?.workflow_events || [];
  const logs = payload.logs || payload.execution_log || payload.task?.execution_log || [];
  const logEvents = logs
    .filter((entry) => entry.event === "workflow_step")
    .map((entry) => entry.details || {});
  const syntheticEvents = [];
  const realtimeLogs = logs.filter((entry) => isRealtimeFileEvent(entry.event));
  if (realtimeLogs.length) {
    syntheticEvents.push({
      step_id: "realtime_saving",
      label: "实时文件审查与 Markdown 草稿保存",
      status: realtimeLogs.some((entry) => entry.event.endsWith("_failed")) ? "blocked" : "completed",
      timestamp: realtimeLogs.at(-1)?.timestamp || realtimeLogs.at(-1)?.details?.event_timestamp || "",
    });
  }
  return [...taskEvents, ...logEvents, ...syntheticEvents].filter((event) => event.step_id);
}

function getCurrentWorkflowStep(payload, events) {
  const current = payload.current_step || payload.task?.current_step || events.at(-1)?.step_id || "planning";
  const logs = payload.logs || payload.execution_log || payload.task?.execution_log || [];
  const latestEvent = logs.at(-1)?.event || "";
  if (current === "collecting" && isRealtimeFileEvent(latestEvent)) {
    return "realtime_saving";
  }
  return current;
}

function isRealtimeFileEvent(event) {
  return [
    "query_realtime_file_reviewed",
    "query_realtime_file_failed",
    "media_realtime_file_reviewed",
    "media_realtime_file_failed",
    "realtime_file_reviewed",
  ].includes(event);
}

function renderAgentPlans(payload) {
  if (!agentPlanOutput) return;
  const plans = payload.agent_plans || payload.task?.agent_plans || {};
  const taskStatus = payload.task_status || payload.task?.task_status || "";
  const planItems = buildAgentPlanItems(plans, payload);
  const isEditable = taskStatus === "awaiting_plan_confirmation";

  if (planPanelHint) {
    planPanelHint.textContent = isEditable
      ? "等待确认 — 可修改或删除各项查询计划"
      : planItems.length ? "" : "";
  }

  if (!planItems.length) {
    agentPlanOutput.innerHTML = '<div class="empty-state">暂无结构化执行计划。</div>';
    return;
  }

  agentPlanOutput.innerHTML = planItems
    .map((item) => {
      const done = item.status === "completed";
      const active = item.status === "in_progress" || item.status === "approved";
      const statusLabel = done ? "已完成" : active ? "执行中" : item.status === "insufficient" ? "需补检索" : "待确认";
      const targets = (item.targets || item.search_targets || []).map((target) => `<li>${escapeHtml(target)}</li>`).join("");
      const criteria = (item.success_criteria || []).map((criterion) => `<li>${escapeHtml(criterion)}</li>`).join("");
      const attempts = (item.attempts || []).map((attempt) => `<li>${escapeHtml(attempt.query)}：${escapeHtml(attempt.hits)} 条命中</li>`).join("");
      const savedPaths = (item.saved_paths || []).map((path) => `<li>${escapeHtml(path)}</li>`).join("");
      const skippedCount = (item.skipped_sources || []).length;
      const realtimeStatus = item.realtime_status ? `<span class="realtime-status ${escapeHtml(item.realtime_status)}">${escapeHtml(formatRealtimeStatus(item.realtime_status, skippedCount))}</span>` : "";
      const itemData = escapeHtml(JSON.stringify({
        title: item.title || item.question || "",
        query_or_action: item.query_or_action || item.google_query || "",
      }));
      const actionButtons = isEditable ? `
        <div class="plan-card-actions">
          <button class="plan-action-btn edit-btn" type="button" data-action="edit">编辑</button>
          <button class="plan-action-btn delete-btn" type="button" data-action="delete">删除</button>
        </div>` : "";
      return `<article class="plan-card ${done ? "done" : active ? "active" : "pending"}"
          data-agent-name="${escapeHtml(item.agent_name)}"
          data-plan-item-id="${escapeHtml(item.plan_item_id || "")}"
          data-plan-item="${itemData}">
        <div class="plan-card-head">
          <span class="checkmark" aria-hidden="true">${done ? "✓" : ""}</span>
          <div>
            <strong>${escapeHtml(item.agent_name)} · ${escapeHtml(item.plan_item_id || "P")}. ${escapeHtml(item.title || item.question)}</strong>
            <span>${escapeHtml(statusLabel)}${realtimeStatus}</span>
          </div>
        </div>
        <div class="plan-query">${escapeHtml(item.query_or_action || item.google_query || "")}</div>
        <div class="plan-lists">
          <div><b>查询内容</b><ul>${targets || "<li>未提供</li>"}</ul></div>
          <div><b>满足标准</b><ul>${criteria || "<li>未提供</li>"}</ul></div>
        </div>
        ${attempts ? `<div class="plan-attempts"><b>执行记录</b><ul>${attempts}</ul></div>` : ""}
        ${savedPaths ? `<div class="plan-saves"><b>实时保存</b><ul>${savedPaths}</ul></div>` : ""}
        ${actionButtons}
      </article>`;
    })
    .join("");

  if (isEditable) {
    attachPlanCardHandlers();
  }
}

function attachPlanCardHandlers() {
  agentPlanOutput.querySelectorAll("[data-action='edit']").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest("[data-plan-item-id]");
      if (!card || card.querySelector(".plan-edit-form")) return;
      let item;
      try { item = JSON.parse(card.dataset.planItem); } catch { item = {}; }
      const form = document.createElement("div");
      form.className = "plan-edit-form";
      form.innerHTML = `
        <label>标题</label>
        <input type="text" name="title" value="${escapeHtml(item.title || "")}">
        <label>查询语句</label>
        <textarea name="query_or_action" rows="2">${escapeHtml(item.query_or_action || "")}</textarea>
        <div class="plan-edit-actions">
          <button type="button" data-edit-action="save">保存</button>
          <button type="button" class="ghost-button" data-edit-action="cancel">取消</button>
        </div>`;
      card.appendChild(form);
      btn.disabled = true;

      form.querySelector("[data-edit-action='cancel']").addEventListener("click", () => {
        form.remove();
        btn.disabled = false;
      });

      form.querySelector("[data-edit-action='save']").addEventListener("click", async () => {
        const taskId = taskIdInput.value.trim();
        const agentName = card.dataset.agentName;
        const planItemId = card.dataset.planItemId;
        const title = form.querySelector("[name='title']").value.trim();
        const queryOrAction = form.querySelector("[name='query_or_action']").value.trim();
        form.querySelectorAll("button").forEach((b) => { b.disabled = true; });
        try {
          const result = await requestJson(
            `/tasks/${encodeURIComponent(taskId)}/plan/items/${encodeURIComponent(agentName)}/${encodeURIComponent(planItemId)}`,
            { method: "PATCH", body: JSON.stringify({ title, query_or_action: queryOrAction }) },
          );
          showPayload({ ...state.lastPayload, ...result });
        } catch (error) {
          showError(error);
        }
      });
    });
  });

  agentPlanOutput.querySelectorAll("[data-action='delete']").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const card = btn.closest("[data-plan-item-id]");
      if (!card) return;
      const label = card.querySelector("strong")?.textContent || card.dataset.planItemId;
      if (!window.confirm(`确认删除计划项「${label}」？`)) return;
      const taskId = taskIdInput.value.trim();
      const agentName = card.dataset.agentName;
      const planItemId = card.dataset.planItemId;
      btn.disabled = true;
      try {
        const result = await requestJson(
          `/tasks/${encodeURIComponent(taskId)}/plan/items/${encodeURIComponent(agentName)}/${encodeURIComponent(planItemId)}`,
          { method: "DELETE" },
        );
        showPayload({ ...state.lastPayload, ...result });
      } catch (error) {
        showError(error);
        btn.disabled = false;
      }
    });
  });
}

function buildAgentPlanItems(plans, payload) {
  const items = [];
  const successful = isSuccessfulTerminalStatus(payload.task_status || payload.task?.task_status);
  Object.entries(plans || {}).forEach(([agentName, plan]) => {
    (plan.plan_items || []).forEach((item) => {
      items.push({
        ...item,
        status: successful ? "completed" : item.status,
        agent_name: agentName,
      });
    });
  });
  if (successful) {
    return dedupePlanItems(items);
  }
  const queryLogs = payload.logs || payload.execution_log || payload.task?.execution_log || [];
  const queryItems = buildQueryPlanItems(queryLogs).map((item) => ({ ...item, agent_name: "QueryEngine" }));
  const mediaItems = buildMediaPlanItems(queryLogs).map((item) => ({ ...item, agent_name: "MediaEngine" }));
  queryItems.forEach((queryItem) => {
    const index = items.findIndex((item) => item.agent_name === "QueryEngine" && item.plan_item_id === queryItem.plan_item_id);
    if (index >= 0) {
      items[index] = { ...items[index], ...queryItem, title: items[index].title || queryItem.question };
    } else {
      items.push(queryItem);
    }
  });
  mediaItems.forEach((mediaItem) => {
    const index = items.findIndex((item) => item.agent_name === "MediaEngine" && item.plan_item_id === mediaItem.plan_item_id);
    if (index >= 0) {
      items[index] = { ...items[index], ...mediaItem, title: items[index].title || mediaItem.title };
    } else {
      items.push(mediaItem);
    }
  });
  return dedupePlanItems(items);
}

function dedupePlanItems(items) {
  const deduped = new Map();
  items.forEach((item) => {
    const key = planItemDedupeKey(item);
    const existing = deduped.get(key);
    if (!existing) {
      deduped.set(key, item);
      return;
    }
    deduped.set(key, {
      ...existing,
      ...item,
      title: existing.title || item.title || item.question,
      query_or_action: existing.query_or_action || item.query_or_action || item.google_query,
      targets: mergeUnique(existing.targets, item.targets || item.search_targets || item.expected_info),
      success_criteria: mergeUnique(existing.success_criteria, item.success_criteria),
      attempts: mergeAttempts(existing.attempts, item.attempts),
      saved_paths: mergeUnique(existing.saved_paths, item.saved_paths),
      skipped_sources: mergeUnique(existing.skipped_sources, item.skipped_sources),
    });
  });
  return Array.from(deduped.values());
}

function planItemDedupeKey(item) {
  const agent = item.agent_name || "";
  if (item.plan_item_id) return `${agent}:${item.plan_item_id}`;
  const query = normalizePlanText(item.query_or_action || item.google_query || item.query || item.question || "");
  const targets = (item.targets || item.search_targets || item.expected_info || []).map(normalizePlanText).sort().join("|");
  return `${agent}:${query}:${targets}`;
}

function normalizePlanText(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function mergeUnique(a, b) {
  const values = [...(Array.isArray(a) ? a : []), ...(Array.isArray(b) ? b : [])];
  const seen = new Set();
  return values.filter((value) => {
    const key = normalizePlanText(value);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function mergeAttempts(a, b) {
  const attempts = [...(Array.isArray(a) ? a : []), ...(Array.isArray(b) ? b : [])];
  const seen = new Set();
  return attempts.filter((attempt) => {
    const key = `${normalizePlanText(attempt.query)}:${attempt.hits}:${attempt.status}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function buildQueryPlanItems(logs) {
  const items = new Map();
  logs.forEach((entry) => {
    const details = entry.details || {};
    if (entry.event === "query_plan_created" && Array.isArray(details.questions)) {
      details.questions.forEach((question, index) => {
        const key = question.plan_item_id || `Q${index + 1}`;
        items.set(key, {
          ...question,
          plan_item_id: key,
          status: question.status || "planned",
        });
      });
    }
    if (entry.event === "query_plan_item_started" || entry.event === "query_question_completed") {
      const key = details.plan_item_id || details.question;
      if (!key) return;
      const existing = items.get(key) || {};
      items.set(key, {
        ...existing,
        ...details,
        plan_item_id: details.plan_item_id || existing.plan_item_id || key,
      });
    }
    if (entry.event === "query_search_executed") {
      const key = details.plan_item_id || details.question;
      if (!key) return;
      const existing = items.get(key) || {};
      const attempts = existing.attempts || [];
      items.set(key, {
        ...existing,
        ...details,
        plan_item_id: details.plan_item_id || existing.plan_item_id || key,
        status: details.status === "completed" ? "in_progress" : existing.status || "in_progress",
        attempts: [...attempts, { query: details.query, hits: details.hits, status: details.status }],
      });
    }
    if (entry.event === "query_realtime_file_reviewed" || entry.event === "query_realtime_file_failed") {
      const key = details.plan_item_id || details.question;
      if (!key) return;
      const existing = items.get(key) || {};
      items.set(key, {
        ...existing,
        ...details,
        plan_item_id: details.plan_item_id || existing.plan_item_id || key,
        realtime_status: entry.event.endsWith("_failed") ? "failed" : details.status || "saved",
        saved_paths: details.saved_paths || existing.saved_paths || [],
        skipped_sources: details.skipped_sources || existing.skipped_sources || [],
      });
    }
  });
  return Array.from(items.values());
}

function buildMediaPlanItems(logs) {
  const items = new Map();
  logs.forEach((entry) => {
    const details = entry.details || {};
    if (entry.event === "media_plan_item_started" || entry.event === "media_search_executed") {
      const key = details.plan_item_id || mediaPlanItemId(details.platform_type, details.query, items);
      if (!key) return;
      const existing = items.get(key) || {};
      const attempts = existing.attempts || [];
      items.set(key, {
        ...existing,
        plan_item_id: key,
        title: mediaPlanTitle(details.platform_type),
        query_or_action: details.query || existing.query_or_action,
        targets: mediaTargets(details.platform_type),
        success_criteria: ["命中相关来源", "结果能补充观点或趋势语境"],
        status: entry.event === "media_search_executed" ? "in_progress" : "in_progress",
        attempts: entry.event === "media_search_executed"
          ? [...attempts, { query: details.query, hits: details.hits, status: "completed" }]
          : attempts,
      });
    }
    if (entry.event === "media_realtime_file_reviewed" || entry.event === "media_realtime_file_failed") {
      const key = details.plan_item_id || mediaPlanItemId(details.platform_type, details.query, items);
      if (!key) return;
      const existing = items.get(key) || {};
      items.set(key, {
        ...existing,
        ...details,
        plan_item_id: key,
        title: existing.title || mediaPlanTitle(details.platform_type),
        query_or_action: existing.query_or_action || details.query,
        targets: existing.targets || mediaTargets(details.platform_type),
        success_criteria: existing.success_criteria || ["命中相关来源", "结果能补充观点或趋势语境"],
        status: details.status === "saved" ? "completed" : existing.status || "in_progress",
        realtime_status: entry.event.endsWith("_failed") ? "failed" : details.status || "saved",
        saved_paths: details.saved_paths || existing.saved_paths || [],
        skipped_sources: details.skipped_sources || existing.skipped_sources || [],
      });
    }
  });
  return Array.from(items.values());
}

function mediaPlanItemId(platformType, query, items) {
  const prefix = { social: "M-S", community: "M-C", blog: "M-B" }[platformType];
  if (!prefix || !query) return "";
  const existing = Array.from(items.values()).find((item) => item.query_or_action === query && item.plan_item_id?.startsWith(prefix));
  if (existing) return existing.plan_item_id;
  const count = Array.from(items.keys()).filter((key) => key.startsWith(prefix)).length + 1;
  return `${prefix}${count}`;
}

function mediaPlanTitle(platformType) {
  return {
    social: "社交媒体观点检索",
    community: "技术社区讨论检索",
    blog: "博客与长文趋势检索",
  }[platformType] || "媒体观点检索";
}

function mediaTargets(platformType) {
  return {
    social: ["社交讨论", "实时观点", "采用信号"],
    community: ["社区共识", "争议点", "实践反馈"],
    blog: ["趋势分析", "落地案例", "未来方向"],
  }[platformType] || ["观点与趋势"];
}

function formatRealtimeStatus(status, skippedCount) {
  if (status === "saved") return "已实时保存";
  if (status === "skipped") return skippedCount ? `已审查，跳过 ${skippedCount} 个来源` : "已审查";
  if (status === "failed") return "保存失败";
  return status;
}

function summarizePlanProgress(payload) {
  const items = buildAgentPlanItems(payload.agent_plans || payload.task?.agent_plans || {}, payload);
  if (!items.length) return "";
  const completed = items.filter((item) => item.status === "completed").length;
  const insufficient = items.filter((item) => item.status === "insufficient").length;
  return `${completed}/${items.length} 完成${insufficient ? `，${insufficient} 个需补检索` : ""}`;
}

function summarizeRealtimeSaves(payload) {
  const logs = payload.logs || payload.execution_log || payload.task?.execution_log || [];
  const reviewed = logs.filter((entry) => entry.event === "query_realtime_file_reviewed" || entry.event === "media_realtime_file_reviewed");
  if (!reviewed.length) return "";
  const savedCount = reviewed.reduce((count, entry) => count + ((entry.details?.saved_paths || []).length), 0);
  const skippedCount = reviewed.reduce((count, entry) => count + ((entry.details?.skipped_sources || []).length), 0);
  return `${savedCount} 个文件${skippedCount ? `，${skippedCount} 个来源跳过` : ""}`;
}

function summarizeTokenUsageLabel(payload) {
  const usage = payload.token_usage || payload.task?.token_usage;
  if (!usage || !usage.request_count) return "";
  return `${formatNumber(usage.total_tokens)} total / ${formatNumber(usage.request_count)} 次调用`;
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

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number.toLocaleString("en-US") : "0";
}

function renderExecutionLog(payload) {
  if (!executionLogOutput) return;
  const logs = payload.logs || payload.execution_log || payload.task?.execution_log || [];
  if (!logs.length) {
    executionLogOutput.innerHTML = '<div class="empty-state">暂无调用或执行日志。</div>';
    return;
  }

  executionLogOutput.innerHTML = logs
    .slice(-24)
    .map((entry) => {
      const event = entry.event || "event";
      const timestamp = entry.timestamp || "";
      const agent = entry.agent || entry.details?.agent || "";
      const details = entry.details ? JSON.stringify(entry.details) : "";
      return `<div class="trace-item"><strong>${escapeHtml(event)}</strong><span>${escapeHtml([timestamp, agent].filter(Boolean).join(" · "))}</span><code>${escapeHtml(details)}</code></div>`;
    })
    .join("");
}

function isTerminalStatus(status) {
  return ["verified", "research_required", "repair_required", "supplement_required", "max_rounds_reached", "failed", "plan_failed"].includes(status);
}

function isSuccessfulTerminalStatus(status) {
  return status === "verified";
}

function stopTaskPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
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
    if (isTerminalStatus(taskPayload.task_status)) {
      stopTaskPolling();
    }
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
      const meta = [
        task.task_status,
        task.version,
        task.updated_at,
      ].filter(Boolean).join(" · ");
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
  } catch (error) {
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
    showPayload(await requestJson("/intake/sessions", {
      method: "POST",
      body: JSON.stringify({ message }),
    }));
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
    showPayload(await requestJson(`/intake/sessions/${encodeURIComponent(sessionId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }));
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
    const payload = await requestJson(`/intake/sessions/${encodeURIComponent(sessionId)}/confirm`, {
      method: "POST",
    });
    showPayload(payload);
    const taskId = payload.task?.task_id || payload.task_id || payload.intake_session?.task_id;
    if (taskId) {
      stopTaskPolling();
    }
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
    const task = await requestJson("/tasks/async", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showPayload(task);
    const createdTaskId = task.task_id || task.task?.task_id;
    if (createdTaskId) {
      startTaskPolling(createdTaskId);
    } else {
      stopTaskPolling();
    }
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
    const route = {
      list: ["/tasks", "GET"],
      get: [`/tasks/${encodeURIComponent(taskId)}`, "GET"],
      plan: [`/tasks/${encodeURIComponent(taskId)}/plan`, "GET"],
      confirmPlan: [`/tasks/${encodeURIComponent(taskId)}/plan/confirm`, "POST"],
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
      if ((action === "resume" || action === "confirmPlan") && activeTaskId && !isTerminalStatus(payload.task_status || payload.task?.task_status)) {
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
    showPayload(await requestJson(`/tasks/${encodeURIComponent(taskId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }));
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
  if (!window.confirm(`确认删除任务 ${taskId}？`)) {
    return;
  }
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
  if (state.workflowGraphReady) {
    renderWorkflowMap(state.lastPayload || {});
  }
});
