const state = {
  lastPayload: null,
  pollTimer: null,
  pollTaskId: null,
  pollCount: 0,
};

const output = document.querySelector("#response-output");
const summaryStrip = document.querySelector("#summary-strip");
const configGrid = document.querySelector("#config-grid");
const healthDot = document.querySelector("#health-dot");
const healthLabel = document.querySelector("#health-label");
const intakeSessionInput = document.querySelector("#intake-session-id");
const taskIdInput = document.querySelector("#task-id");
const taskUpdateInput = document.querySelector("#task-update-payload");
const queryPlanOutput = document.querySelector("#query-plan-output");
const executionLogOutput = document.querySelector("#execution-log-output");
const taskListOutput = document.querySelector("#task-list-output");

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
  renderQueryPlan(payload);
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
  renderQueryPlan(payload);
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
  const progress = summarizeQueryProgress(payload);
  const items = [
    ["Task ID", payload.task_id || payload.task?.task_id || payload.intake_session?.task_id],
    ["Session ID", payload.session_id || payload.intake_session?.session_id],
    ["状态", payload.task_status || payload.status || payload.task?.task_status || payload.intake_session?.status],
    ["文档路径", getNested(payload, "document_artifact.path")],
    ["质量检查", getNested(payload, "post_storage_result.quality_check.status")],
    ["冻结版本", getNested(payload, "post_storage_result.version_record.version") || payload.version],
    ["研报资格", getNested(payload, "post_storage_result.version_record.report_eligible")],
    ["错误", payload.error],
    ["查询进度", progress],
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
  const entries = Object.entries(payload);
  if (!entries.length) {
    configGrid.innerHTML = '<div class="empty-state">未返回配置状态。</div>';
    return;
  }

  configGrid.innerHTML = entries
    .map(([key, value]) => {
      const label = String(key).replaceAll("_", " ");
      const rendered = typeof value === "boolean" ? (value ? "已配置" : "未配置") : String(value);
      const tone = value === true ? "tone-ok" : value === false ? "tone-bad" : "";
      return `<div class="config-item"><strong>${escapeHtml(label)}</strong><span class="${tone}">${escapeHtml(rendered)}</span></div>`;
    })
    .join("");
}

function renderQueryPlan(payload) {
  const queryOutput = payload.agent_outputs?.QueryEngine || payload.task?.agent_outputs?.QueryEngine;
  const logs = queryOutput?.execution_log || payload.logs || payload.execution_log || payload.task?.execution_log || [];
  const planItems = buildQueryPlanItems(logs);

  if (!planItems.length) {
    queryPlanOutput.innerHTML = '<div class="empty-state">暂无结构化查询计划。</div>';
    return;
  }

  queryPlanOutput.innerHTML = planItems
    .map((item) => {
      const done = item.status === "completed";
      const active = item.status === "in_progress";
      const statusLabel = done ? "已完成" : active ? "查询中" : item.status === "insufficient" ? "需补检索" : "待查询";
      const targets = (item.search_targets || []).map((target) => `<li>${escapeHtml(target)}</li>`).join("");
      const criteria = (item.success_criteria || []).map((criterion) => `<li>${escapeHtml(criterion)}</li>`).join("");
      const attempts = (item.attempts || []).map((attempt) => `<li>${escapeHtml(attempt.query)}：${escapeHtml(attempt.hits)} 条命中</li>`).join("");
      return `<article class="plan-card ${done ? "done" : active ? "active" : "pending"}">
        <div class="plan-card-head">
          <span class="checkmark" aria-hidden="true">${done ? "✓" : ""}</span>
          <div>
            <strong>${escapeHtml(item.plan_item_id || "Q")}. ${escapeHtml(item.question)}</strong>
            <span>${escapeHtml(statusLabel)}</span>
          </div>
        </div>
        <div class="plan-query">${escapeHtml(item.google_query || "")}</div>
        <div class="plan-lists">
          <div><b>查询内容</b><ul>${targets || "<li>未提供</li>"}</ul></div>
          <div><b>满足标准</b><ul>${criteria || "<li>未提供</li>"}</ul></div>
        </div>
        ${attempts ? `<div class="plan-attempts"><b>执行记录</b><ul>${attempts}</ul></div>` : ""}
      </article>`;
    })
    .join("");
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
  });
  return Array.from(items.values());
}

function summarizeQueryProgress(payload) {
  const queryOutput = payload.agent_outputs?.QueryEngine || payload.task?.agent_outputs?.QueryEngine;
  const logs = queryOutput?.execution_log || payload.logs || payload.execution_log || payload.task?.execution_log || [];
  const items = buildQueryPlanItems(logs);
  if (!items.length) return "";
  const completed = items.filter((item) => item.status === "completed").length;
  const insufficient = items.filter((item) => item.status === "insufficient").length;
  return `${completed}/${items.length} 完成${insufficient ? `，${insufficient} 个需补检索` : ""}`;
}

function renderExecutionLog(payload) {
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
  return ["verified", "research_required", "repair_required", "supplement_required", "max_rounds_reached", "failed"].includes(status);
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
    configGrid.innerHTML = `<div class="empty-state">配置状态读取失败：${escapeHtml(error.message)}</div>`;
  }
}

document.querySelector("#refresh-status").addEventListener("click", refreshStatus);

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
    showPayload(await requestJson(`/intake/sessions/${encodeURIComponent(sessionId)}/confirm`, {
      method: "POST",
    }));
  } catch (error) {
    showError(error);
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
    startTaskPolling(task.task_id);
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
      resume: [`/tasks/${encodeURIComponent(taskId)}/resume`, "POST"],
      frozen: [`/tasks/${encodeURIComponent(taskId)}/frozen`, "GET"],
      report: [`/tasks/${encodeURIComponent(taskId)}/report`, "POST"],
      logs: [`/tasks/${encodeURIComponent(taskId)}/logs`, "GET"],
    }[action];

    setBusy(button, true);
    try {
      showPayload(await requestJson(route[0], { method: route[1] }));
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
