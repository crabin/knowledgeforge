const state = {
  lastPayload: null,
};

const output = document.querySelector("#response-output");
const summaryStrip = document.querySelector("#summary-strip");
const configGrid = document.querySelector("#config-grid");
const healthDot = document.querySelector("#health-dot");
const healthLabel = document.querySelector("#health-label");
const intakeSessionInput = document.querySelector("#intake-session-id");
const taskIdInput = document.querySelector("#task-id");
const queryPlanOutput = document.querySelector("#query-plan-output");
const executionLogOutput = document.querySelector("#execution-log-output");

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
  const items = [
    ["Task ID", payload.task_id || payload.task?.task_id || payload.intake_session?.task_id],
    ["Session ID", payload.session_id || payload.intake_session?.session_id],
    ["状态", payload.task_status || payload.status || payload.task?.task_status || payload.intake_session?.status],
    ["文档路径", getNested(payload, "document_artifact.path")],
    ["质量检查", getNested(payload, "post_storage_result.quality_check.status")],
    ["冻结版本", getNested(payload, "post_storage_result.version_record.version") || payload.version],
    ["研报资格", getNested(payload, "post_storage_result.version_record.report_eligible")],
    ["错误", payload.error],
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
  const rawMaterial = queryOutput?.raw_material || [];
  const planStart = rawMaterial.indexOf("查询计划：");
  const planItems = planStart >= 0
    ? rawMaterial.slice(planStart + 1).filter((item) => String(item).startsWith("- Q") || String(item).startsWith("  "))
    : [];

  if (!planItems.length) {
    queryPlanOutput.innerHTML = '<div class="empty-state">暂无结构化查询计划。</div>';
    return;
  }

  queryPlanOutput.innerHTML = planItems
    .map((item) => `<div class="trace-item">${escapeHtml(item)}</div>`)
    .join("");
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
    showPayload(await requestJson("/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    }));
  } catch (error) {
    showError(error);
  } finally {
    setBusy(form, false);
  }
});

document.querySelectorAll("[data-task-action]").forEach((button) => {
  button.addEventListener("click", async () => {
    const taskId = taskIdInput.value.trim();
    const action = button.dataset.taskAction;
    const route = {
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

refreshStatus();
