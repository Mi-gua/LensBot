(() => {
  const defaults = window.LENSBOT_DEFAULTS || {};
  const defaultParams = defaults.params || {};

  const zh = {
    idle: "\u7a7a\u95f2",
    running: "\u8fd0\u884c\u4e2d",
    done: "\u5b8c\u6210",
    error: "\u9519\u8bef",
    waitTask: "\u7b49\u5f85\u65b0\u7684\u8bbe\u8ba1\u4efb\u52a1\u3002",
    ready: "LensBot \u5df2\u5c31\u7eea\u3002",
    pendingTitle: "\u7b49\u5f85\u8fd0\u884c",
    runningTitle: "\u6b63\u5728\u751f\u6210",
    imagePendingTitle: "\u7b49\u5f85\u56fe\u50cf",
    refsEmpty: "\u8fd0\u884c\u540e\u663e\u793a\u6700\u591a 3 \u4e2a\u6838\u5fc3\u53c2\u8003\u6848\u4f8b\u3002",
    filesEmpty: "\u8fd0\u884c\u540e\u663e\u793a\u7ed3\u679c\u6587\u4ef6\u3002",
    metricsEmpty: "\u8fd0\u884c\u540e\u663e\u793a\u6027\u80fd\u6307\u6807\u3002",
    artifactsEmpty: "\u8fd0\u884c\u540e\u663e\u793a\u5206\u6790\u4ea7\u7269\u3002",
    processEmpty: "\u8fd0\u884c\u540e\u663e\u793a\u6700\u7ec8\u7ed3\u679c\u3002",
    runningText: "\u8fd0\u884c\u4e2d...",
    creatingRun: "\u6b63\u5728\u521b\u5efa\u8bbe\u8ba1\u4efb\u52a1\u5e76\u8fde\u63a5\u5b9e\u65f6\u8f93\u51fa\u3002",
    createFailed: "\u521b\u5efa\u4efb\u52a1\u5931\u8d25\u3002",
    designDone: "\u8bbe\u8ba1\u5b8c\u6210\uff0c\u7ed3\u679c\u5df2\u66f4\u65b0\u3002",
    doneWithIssues: "\u4efb\u52a1\u5b8c\u6210\u4f46\u5b58\u5728\u95ee\u9898\u3002",
    runFailed: "\u8fd0\u884c\u5931\u8d25\u3002",
    reconnecting: "\u5b9e\u65f6\u8fde\u63a5\u4e2d\u65ad\uff0c\u6b63\u5728\u91cd\u8fde\u3002",
    modelMissing: "\u6a21\u578b\u672a\u914d\u7f6e",
    imageWaiting: "\u7b49\u5f85\u56fe\u50cf...",
    zemaxPending: "Zemax \u5206\u6790\u672a\u5b8c\u6210\uff1a",
    currentSnapshot: "\u5f53\u524d\u955c\u5934\u4f18\u5316\u5feb\u7167",
    snapshotPending: "\u8fd0\u884c\u540e\u6d41\u5f0f\u663e\u793a\u5f53\u524d\u4f18\u5316\u5feb\u7167\u3002",
    defaultPrompt: "设计一个全画幅标准摄影镜头： 焦距 50 mm，F/3.0，全视场 43 度，后焦距 18 mm，总厚度约 75 mm。 优先保持 EFL、FOV 和 F 数等规格接近目标；其次优化中心、0.5 视场和边缘 RMS spot 。",
    reportEmpty: "运行完成后，这里会显示光学镜头设计总结报告。",
  };
  const providers = defaults.llm?.providers || [];
  const providerMap = Object.fromEntries(providers.map((provider) => [provider.id, provider]));

  let confirmedApiConfig;
  let confirmedEngineConfig;
  let currentMode = "";
  let currentSource = null;
  let streamCompleted = false;
  let seenEventIds = new Set();
  let lastTimelineText = "";
  let runStartTime = null;
  let elapsedTimer = null;
  let previewPollTimer = null;
  let activeResultDir = "";
  let initialProvider = "custom";
  let initialModel = "";
  let customBaseUrl = "";
  let customModel = "";
  let selectedOptimizationTurn = null;

  const modeButtons = [...document.querySelectorAll("#mode-toggle button")];
  const nlBlock = document.getElementById("nl-block");
  const paramBlock = document.getElementById("param-block");
  const runBtn = document.getElementById("run-btn");
  const resetBtn = document.getElementById("reset-btn");
  const statusCopy = document.getElementById("status-copy");
  const statusState = document.getElementById("status-state");
  const elapsedPill = document.getElementById("elapsed-pill");
  const timeline = document.getElementById("timeline");
  const metrics = document.getElementById("metrics");
  const artifacts = document.getElementById("artifacts");
  const optimizationStages = document.getElementById("optimization-stages");
  const optimizationProgressPanel = document.getElementById("optimization-progress-panel");
  const initialStructure = document.getElementById("initial-structure");
  const currentSnapshot = document.getElementById("current-snapshot");
  const lensStageGallery = document.getElementById("lens-stage-gallery");
  const references = document.getElementById("references");
  const fileMeta = document.getElementById("file-meta");
  const reportStage = document.getElementById("report-stage");
  const reportOpen = document.getElementById("report-open");
  const reportDownload = document.getElementById("report-download");
  const modelPill = document.getElementById("model-pill");
  const viewButtons = [...document.querySelectorAll("[data-view]")];
  const pageViews = [...document.querySelectorAll(".page-view")];
  const providerButtons = [...document.querySelectorAll("#llm-provider-tabs button")];

  providerButtons.forEach((button) => {
    const provider = providerMap[button.dataset.provider];
    if (!provider) return;
    if (provider.base_url) button.dataset.url = provider.base_url;
    if (provider.label) button.textContent = provider.label;
  });

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function renderEmptyState(message, { title = zh.pendingTitle, tone = "pending", fill = true } = {}) {
    const classes = ["empty-state", `empty-state--${tone}`];
    if (fill) classes.push("empty-state--fill");
    return `
      <div class="${classes.join(" ")}">
        <span class="empty-state-mark" aria-hidden="true"></span>
        <span class="empty-state-title">${escapeHtml(title)}</span>
        <p>${escapeHtml(message)}</p>
      </div>
    `;
  }

  function renderRunningState(message = zh.runningText) {
    return renderEmptyState(message, { title: zh.runningTitle, tone: "running" });
  }

  function setView(viewId) {
    const aliases = {
      monitor: "run",
      sources: "run",
      gallery: "results",
      files: "results",
      "metrics-view": "results",
    };
    const target = aliases[viewId] || viewId || "run";
    pageViews.forEach((view) => {
      view.classList.toggle("active", view.id === `view-${target}`);
    });
    viewButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.view === target);
    });
    if (window.location.hash !== `#${target}`) {
      history.replaceState(null, "", `#${target}`);
    }
  }

  function setMode(mode) {
    currentMode = mode || (modeButtons[0] && modeButtons[0].dataset.mode) || "natural";
    modeButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.mode === currentMode);
    });
    const isNatural = modeButtons[0] && currentMode === modeButtons[0].dataset.mode;
    if (nlBlock) nlBlock.style.display = isNatural ? "block" : "none";
    if (paramBlock) paramBlock.style.display = isNatural ? "none" : "block";
  }

  function normalizeUrl(value) {
    return String(value || "").trim().replace(/\/+$/, "").toLowerCase();
  }

  function urlHost(value) {
    try {
      return new URL(String(value || "").trim()).hostname.toLowerCase();
    } catch (_error) {
      return "";
    }
  }

  function providerUrlMatches(providerId, baseUrl) {
    const providerUrl = normalizeUrl(providerMap[providerId]?.base_url);
    if (!providerUrl || !baseUrl) return false;
    return providerUrl === baseUrl || urlHost(providerUrl) === urlHost(baseUrl);
  }

  function syncProviderTabs(preferredProvider = "") {
    const baseUrl = normalizeUrl(textValue("llm_base_url"));
    let active = "custom";
    if (preferredProvider && providerUrlMatches(preferredProvider, baseUrl)) {
      active = preferredProvider;
    } else {
      for (const button of providerButtons) {
        if (providerUrlMatches(button.dataset.provider, baseUrl)) {
          active = button.dataset.provider;
          break;
        }
      }
    }
    providerButtons.forEach((button) => {
      const selected = button.dataset.provider === active;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-selected", String(selected));
    });
    const modelInput = document.getElementById("llm_model");
    if (modelInput) {
      modelInput.placeholder = providerMap[active]?.model_placeholder || providerMap.custom?.model_placeholder || "";
    }
    return active;
  }

  function selectProvider(button) {
    const provider = button.dataset.provider || "custom";
    const activeProvider = document.querySelector("#llm-provider-tabs button.active")?.dataset.provider;
    if (activeProvider === "custom") {
      customBaseUrl = textValue("llm_base_url");
      customModel = textValue("llm_model");
    }
    if (button.dataset.provider !== "custom" && button.dataset.url) {
      setInputValue("llm_base_url", button.dataset.url);
      const active = syncProviderTabs(provider);
      setInputValue("llm_model", active === initialProvider ? initialModel : (providerMap[active]?.default_model || ""));
    } else {
      setInputValue("llm_base_url", customBaseUrl);
      setInputValue("llm_model", customModel);
      providerButtons.forEach((item) => {
        item.classList.toggle("active", item.dataset.provider === provider);
      });
      const modelInput = document.getElementById("llm_model");
      if (modelInput) modelInput.placeholder = providerMap.custom?.model_placeholder || "";
      document.getElementById("llm_base_url")?.focus();
    }
  }

  function setStatus(label, detail) {
    const key = String(label || "idle").toLowerCase();
    const labels = {
      idle: zh.idle,
      running: zh.running,
      done: zh.done,
      error: zh.error,
    };
    statusState.textContent = labels[key] || label || zh.idle;
    statusCopy.textContent = detail || "";
    statusCopy.title = detail || "";
    statusState.classList.remove("is-idle", "is-running", "is-error");
    if (key.includes("run")) {
      statusState.classList.add("is-running");
    } else if (key.includes("fail") || key.includes("error")) {
      statusState.classList.add("is-error");
    } else {
      statusState.classList.add("is-idle");
    }
  }

  function formatElapsed(ms) {
    const totalSeconds = Math.max(0, Math.floor(ms / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) {
      return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function refreshElapsed() {
    if (!runStartTime || !elapsedPill) return;
    elapsedPill.textContent = formatElapsed(Date.now() - runStartTime);
  }

  function startElapsedTimer() {
    runStartTime = Date.now();
    refreshElapsed();
    stopElapsedTimer();
    elapsedTimer = window.setInterval(refreshElapsed, 1000);
  }

  function stopElapsedTimer() {
    if (elapsedTimer) {
      window.clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  function resultDirFromPayload(payload) {
    return String(payload?.result_dir || payload?.result_dir_url || "").trim();
  }

  function startPreviewPolling(resultDir) {
    const nextResultDir = String(resultDir || "").trim();
    if (!nextResultDir) return;
    if (activeResultDir === nextResultDir && previewPollTimer) return;
    stopPreviewPolling();
    activeResultDir = nextResultDir;
    pollActivePreview();
    previewPollTimer = window.setInterval(pollActivePreview, 2500);
  }

  function stopPreviewPolling() {
    if (previewPollTimer) {
      window.clearInterval(previewPollTimer);
      previewPollTimer = null;
    }
    activeResultDir = "";
  }

  async function pollActivePreview() {
    const resultDir = activeResultDir;
    if (!resultDir) return;
    try {
      const rsp = await fetch(`/api/preview?result_dir=${encodeURIComponent(resultDir)}`, { cache: "no-store" });
      if (!rsp.ok || resultDir !== activeResultDir) return;
      const payload = await rsp.json();
      if (resultDir !== activeResultDir || !payload.preview) return;
      renderArtifacts(payload, { renderFinalDesign: false });
    } catch (_error) {
      // The SSE stream remains authoritative; preview polling is opportunistic.
    }
  }

  function handleArtifactPayload(payload) {
    const resultDir = resultDirFromPayload(payload);
    if (resultDir) startPreviewPolling(resultDir);
    if (payload?.preview) {
      renderArtifacts(payload, { renderFinalDesign: false });
      renderMetricCards(payload.metrics || {});
    }
  }

  function shouldHandleEvent(event) {
    const id = event.lastEventId || "";
    if (!id) return true;
    if (seenEventIds.has(id)) return false;
    seenEventIds.add(id);
    return true;
  }

  function appendTimeline(event) {
    const payload = event && typeof event === "object" ? event : { message: event };
    const text = String(payload.message || "").trim();
    if (!text || text === lastTimelineText) return;
    lastTimelineText = text;
    const item = document.createElement("li");
    item.className = "timeline-item timeline-item--" + escapeHtml(payload.level || "info");
    const title = String(payload.title || "").trim();
    const isOptimizationStart = payload.key === "workflow.node.start" && payload.fields?.node === "Optimization";
    item.innerHTML = (title ? "<strong>" + escapeHtml(title) + "</strong>" : "")
      + "<span>" + escapeHtml(isOptimizationStart ? "镜头优化智能体正在运行" : text) + "</span>";
    if (isOptimizationStart) {
      const action = document.createElement("button");
      action.className = "timeline-action";
      action.type = "button";
      action.textContent = "查看优化过程";
      action.addEventListener("click", () => setView("process"));
      item.appendChild(action);
    }
    timeline.appendChild(item);
    timeline.scrollTop = timeline.scrollHeight;
  }

  function resetTimeline() {
    timeline.innerHTML = "";
    lastTimelineText = "";
    appendTimeline({
      key: "run.ready",
      title: "任务接收",
      source: "system",
      level: "info",
      message: zh.ready,
    });
  }

  function formatValue(value, suffix = "", digits = 2) {
    if (value === null || value === undefined || value === "") return "-";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return `${number.toFixed(digits).replace(/\.?0+$/, "")}${suffix}`;
  }

  function firstValue(map, keys) {
    for (const key of keys) {
      if (map && map[key] !== undefined && map[key] !== null && map[key] !== "") {
        return map[key];
      }
    }
    return null;
  }

  function setInputValue(id, value) {
    const input = document.getElementById(id);
    if (input) input.value = value ?? "";
  }

  function numberValue(id) {
    const input = document.getElementById(id);
    if (!input || input.value === "") return undefined;
    const value = Number(input.value);
    return Number.isFinite(value) ? value : undefined;
  }

  function textValue(id) {
    const input = document.getElementById(id);
    return input ? input.value.trim() : "";
  }

  function renderMetricCards(metricMap) {
    const groups = [
      {
        title: "DeepLens",
        items: [
          [["deeplens_efl_mm"], "\u6709\u6548\u7126\u8ddd", " mm", 2],
          [["deeplens_fnum"], "\u5de5\u4f5c F \u6570", "", 2],
          [["deeplens_fov_deg"], "\u89c6\u573a", " deg", 2],
          [["deeplens_distortion_pct_edge"], "\u8fb9\u7f18\u7578\u53d8", " %", 2],
          [["deeplens_spot_valid_pct_edge"], "\u8fb9\u7f18\u6709\u6548\u5149\u7ebf", " %", 1],
          [["deeplens_mtf50_edge_tan_cy_mm"], "\u8fb9\u7f18\u51e0\u4f55 MTF50", " cy/mm", 2],
          [["deeplens_rms_spot_um_edge"], "\u8fb9\u7f18 RMS \u5149\u6591", " um", 2],
          [["deeplens_rms_spot_um_max"], "\u6700\u5927 RMS \u5149\u6591", " um", 2],
        ],
      },
      {
        title: "Zemax",
        items: [
          [["zemax_efl_mm"], "\u6709\u6548\u7126\u8ddd", " mm", 2],
          [["zemax_fnum"], "\u8fd1\u8f74\u5de5\u4f5c F \u6570", "", 2],
          [["zemax_fov_deg"], "\u89c6\u573a", " deg", 2],
          [["zemax_distortion_pct_edge"], "\u8fb9\u7f18\u7578\u53d8", " %", 2],
          [["zemax_geometric_mtf50_edge_tan_cy_mm"], "\u8fb9\u7f18\u51e0\u4f55 MTF50", " cy/mm", 2],
          [["zemax_mtf50_edge_tan_cy_mm"], "\u8fb9\u7f18\u884d\u5c04 FFT MTF50", " cy/mm", 2],
          [["zemax_spot_rms_edge_um"], "\u8fb9\u7f18 RMS \u5149\u6591", " um", 2],
          [["zemax_spot_rms_max_um"], "\u6700\u5927 RMS \u5149\u6591", " um", 2],
        ],
      },
    ];

    const hasAnyMetric = groups.some((group) =>
      group.items.some(([keys]) => firstValue(metricMap, keys) !== null)
    );
    if (!hasAnyMetric) {
      metrics.innerHTML = renderEmptyState(zh.metricsEmpty);
      return;
    }

    const html = groups.map((group) => {
      const rows = group.items.map(([keys, label, suffix, digits]) => {
        const value = firstValue(metricMap, keys);
        return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(formatValue(value, suffix, digits))}</strong></div>`;
      }).join("");
      return `<div class="metric-column"><h3 class="metric-source">${escapeHtml(group.title)}</h3><div class="metric-grid">${rows}</div></div>`;
    }).join("");

    metrics.innerHTML = html || renderEmptyState(zh.metricsEmpty);
  }

  function renderFileMeta(result) {
    const preview = result.preview || {};
    const rows = [
      ["\u6700\u7ec8\u6570\u636e", result.final_json, result.final_json_url],
      ["Zemax \u955c\u5934\u6587\u4ef6", result.final_zmx, result.final_zmx_url],
      ["\u7ed3\u679c\u8bc1\u636e", preview.evidence_path, preview.evidence_url],
      ["\u6458\u8981\u62a5\u544a", result.summary_report_file, result.summary_report_file_url],
      ["\u6307\u6807\u6587\u4ef6", result.metrics_file, result.metrics_file_url],
      ["\u8fd0\u884c\u65e5\u5fd7", result.log_file, result.log_file_url],
    ];
    fileMeta.innerHTML = rows
      .filter(([, path]) => path)
      .map(([label, path, url]) => `
        <div class="list-item">
          <h4>${escapeHtml(label)}</h4>
          <p class="file-path">${url ? `<a class="file-link mono" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(path)}</a>` : escapeHtml(path)}</p>
        </div>
      `).join("") || renderEmptyState(zh.filesEmpty);
  }

  function renderReport(result) {
    const report = (result?.preview?.artifacts || []).find((item) => item.role === "html_review_report");
    const url = report?.url || "";
    if (!reportStage || !reportOpen || !reportDownload) return;
    for (const link of [reportOpen, reportDownload]) {
      link.classList.toggle("disabled", !url);
      link.setAttribute("aria-disabled", String(!url));
      link.href = url || "#";
    }
    reportStage.innerHTML = url
      ? `<iframe class="report-frame" src="${escapeHtml(url)}" title="光学镜头设计总结报告"></iframe>`
      : result?.ok === false
        ? renderEmptyState(result.summary || zh.runFailed, { title: "运行未完成，未生成设计报告", tone: "error" })
        : renderEmptyState(zh.reportEmpty);
  }

  function renderImagePanel({ title, subtitle, url, kind, showHead = true }) {
    return `
      <div class="result-panel ${escapeHtml(kind || "")}${showHead ? "" : " no-head"}">
        ${showHead ? `
          <div class="result-head">
            <div>
              <h4>${escapeHtml(title)}</h4>
              <p>${escapeHtml(subtitle || "")}</p>
            </div>
          </div>
        ` : ""}
        <div class="result-image-wrap">
          ${url ? `<img class="result-image" src="${escapeHtml(url)}" alt="${escapeHtml(title)}">` : renderEmptyState(zh.imageWaiting, { title: zh.imagePendingTitle, tone: "image" })}
        </div>
      </div>
    `;
  }

  function isPlainObject(value) {
    return Boolean(value && typeof value === "object" && !Array.isArray(value));
  }

  function hasDetailValue(value) {
    if (value === null || value === undefined || value === "") return false;
    if (Array.isArray(value)) return value.length > 0;
    if (isPlainObject(value)) return Object.keys(value).length > 0;
    return true;
  }

  function compactJson(value) {
    if (!hasDetailValue(value)) return "";
    try {
      return JSON.stringify(value, null, 2);
    } catch (_error) {
      return String(value);
    }
  }

  function traceDetailKey(...parts) {
    return parts.map((part) => String(part ?? "").replace(/\s+/g, " ").trim()).join(":");
  }

  function renderDetails(label, value, detailKey) {
    if (!hasDetailValue(value)) return "";
    return "<details class=\"trace-details\" data-detail-key=\"" + escapeHtml(detailKey || label) + "\"><summary>" + escapeHtml(label)
      + "</summary><pre>" + escapeHtml(compactJson(value)) + "</pre></details>";
  }

  function formatTraceDuration(value) {
    if (value === null || value === undefined || value === "") return "-";
    const ms = Number(value);
    if (!Number.isFinite(ms)) return "-";
    if (ms < 1000) return Math.round(ms) + " ms";
    const seconds = ms / 1000;
    return seconds.toFixed(seconds < 10 ? 1 : 0).replace(/\.0$/, "") + " s";
  }

  function traceStatusLabel(status, context = "") {
    const text = String(status || "").trim().toLowerCase();
    if (text === "ok" && context === "tool-call") return "完成";
    if (text === "ok" && context === "tool-result") return "通过";
    const labels = {
      running: "运行中",
      ok: "通过",
      error: "异常",
      trace: "记录",
      done: "完成",
      completed: "完成",
      pending: "等待中",
    };
    return labels[text] || status || "记录";
  }

  function resultDetailPayload(event, toolResult) {
    const payload = {};
    const metricsPayload = toolResult.metrics || event.metrics;
    const artifactsPayload = toolResult.artifacts || event.artifacts;
    if (hasDetailValue(metricsPayload)) payload.metrics = metricsPayload;
    if (hasDetailValue(artifactsPayload)) payload.artifacts = artifactsPayload;
    for (const key of ["state_patch", "metadata", "error", "data"]) {
      if (hasDetailValue(toolResult[key])) payload[key] = toolResult[key];
    }
    return payload;
  }

  function renderTraceChips(event, toolResult) {
    const chips = [];
    const metricsPayload = toolResult.metrics || event.metrics;
    const artifactsPayload = toolResult.artifacts || event.artifacts;
    if (isPlainObject(metricsPayload) && Object.keys(metricsPayload).length) {
      chips.push(Object.keys(metricsPayload).length + " 项指标");
    }
    if (Array.isArray(artifactsPayload) && artifactsPayload.length) {
      chips.push(artifactsPayload.length + " 个产物");
    }
    if (!chips.length) return "";
    return "<div class=\"trace-chips\">" + chips.map((chip) => "<span>" + escapeHtml(chip) + "</span>").join("") + "</div>";
  }

  function eventTurn(event) {
    const value = Number(event?.turn);
    return Number.isFinite(value) ? value : 0;
  }

  function isOptimizationCompletionEvent(event) {
    const kind = String(event?.kind || "");
    return kind === "agent_end" || kind === "agent_error" || event?.done === true;
  }

  function optimizationReasoningEvents(events) {
    return (events || []).filter((event) => !isOptimizationCompletionEvent(event));
  }

  function optimizationProgressTurnCount(events, turnCount = 0) {
    const numericTurnCount = Math.max(0, Number(turnCount) || 0);
    const reasoningTurns = optimizationReasoningEvents(events).map(eventTurn);
    if (!reasoningTurns.length) return numericTurnCount;
    const lastReasoningTurn = Math.max(...reasoningTurns);
    const completionTurns = (events || []).filter(isOptimizationCompletionEvent).map(eventTurn);
    const lastCompletionTurn = completionTurns.length ? Math.max(...completionTurns) : -1;
    if (lastCompletionTurn > lastReasoningTurn && numericTurnCount === lastCompletionTurn + 1) {
      return lastReasoningTurn + 1;
    }
    return Math.max(numericTurnCount, lastReasoningTurn + 1);
  }

  function turnDisplay(turn) {
    return String(Number(turn) + 1);
  }

  function turnAnchorId(turn) {
    return "optimization-turn-" + String(turn).replace(/[^0-9a-z_-]/gi, "-");
  }

  function turnAnchorAttrs(turn, anchorTurns) {
    const anchor = anchorTurns.has(turn) ? "" : " id=\"" + escapeHtml(turnAnchorId(turn)) + "\"";
    anchorTurns.add(turn);
    return " data-turn=\"" + escapeHtml(turn) + "\"" + anchor;
  }

  function toolEventKey(event, payload, fallback) {
    return String(event?.tool_call_id || payload?.id || event?.result_id || event?.tool || payload?.tool || payload?.name || fallback);
  }

  function toolCallResultStatuses(events) {
    const statuses = new Map();
    (events || []).forEach((event) => {
      const kind = String(event?.kind || "");
      if (kind === "tool_result") {
        const toolResult = isPlainObject(event.tool_result) ? event.tool_result : {};
        const ok = event.ok ?? toolResult.ok;
        const status = ok === false ? "error" : (event.status && event.status !== "running" ? event.status : "ok");
        statuses.set(toolEventKey(event, toolResult, "tool-result"), status);
      }
    });
    return statuses;
  }

  function legacyEventsToTranscript(events) {
    const transcript = [];
    (events || []).forEach((event) => {
      const turn = eventTurn(event);
      const toolCall = isPlainObject(event.tool_call)
        ? event.tool_call
        : { name: event.tool || event.action || "agent", arguments: event.arguments || event.action_input || {} };
      const toolResult = isPlainObject(event.tool_result) ? event.tool_result : {};
      if (event.thought) {
        transcript.push({
          kind: "assistant_message",
          turn,
          text: event.thought,
          message_id: "legacy-message-" + turn,
        });
      }
      if (toolCall.name) {
        transcript.push({
          kind: "tool_call",
          turn,
          tool: toolCall.name,
          arguments: toolCall.arguments || {},
          tool_call: toolCall,
          tool_call_id: "legacy-tool-" + turn,
          status: event.status || "running",
        });
      }
      transcript.push({
        kind: event.done ? "agent_end" : "tool_result",
        turn,
        tool: toolCall.name,
        tool_result: toolResult,
        observation: event.observation || toolResult.observation || (event.done ? "Optimization agent finished." : ""),
        ok: event.ok ?? toolResult.ok,
        done: event.done,
        metrics: toolResult.metrics || event.metrics,
        artifacts: toolResult.artifacts || event.artifacts,
        duration_ms: event.duration_ms,
        data: event.data,
        status: event.status,
      });
    });
    return transcript;
  }

  function transcriptEventsFromStage(stage) {
    const data = stage?.data || {};
    const nativeEvents = Array.isArray(data.transcript_events) ? data.transcript_events : [];
    if (nativeEvents.length) return nativeEvents.filter((event) => String(event?.kind || "") !== "agent_end");
    const agentEvents = Array.isArray(data.agent_events) ? data.agent_events : data.react_events;
    return legacyEventsToTranscript(Array.isArray(agentEvents) ? agentEvents : [])
      .filter((event) => String(event?.kind || "") !== "agent_end");
  }

  function renderTurnDots(events, turnCount = 0) {
    const reasoningEvents = optimizationReasoningEvents(events);
    const turns = new Set(reasoningEvents.map(eventTurn));
    const lastEventTurn = turns.size ? Math.max(...turns) : -1;
    const count = optimizationProgressTurnCount(events, turnCount);
    if (!count) return "";
    const selectedTurn = Number.isInteger(selectedOptimizationTurn) && selectedOptimizationTurn >= 0 && selectedOptimizationTurn < count
      ? selectedOptimizationTurn
      : null;
    const activeTurn = selectedTurn ?? (lastEventTurn >= 0 ? lastEventTurn : count - 1);
    const buttons = [];
    for (let index = 0; index < count; index += 1) {
      const hasEvent = turns.has(index);
      const isActive = index === activeTurn;
      buttons.push(
        "<button type=\"button\" class=\"turn-jump" + (hasEvent ? " is-ready" : "") + (isActive ? " is-active" : "") + "\" data-turn-anchor=\""
          + escapeHtml(index) + "\" data-turn-target=\"" + escapeHtml(turnAnchorId(index)) + "\">" + escapeHtml(turnDisplay(index)) + "</button>"
      );
    }
    return "<div class=\"turn-jump-strip\" aria-label=\"优化轮次\">" + buttons.join("") + "</div>";
  }

  function toolProgressMatches(toolName, progress) {
    const name = String(toolName || "").trim();
    if (!["deeplens_curriculum", "deeplens_finetune"].includes(name)) return false;
    if (!progress || progress.tool !== name) return false;
    return progress.running !== false;
  }

  function renderToolProgress(toolName, status, progress) {
    const name = String(toolName || "").trim();
    if (!["deeplens_curriculum", "deeplens_finetune"].includes(name)) return "";
    if (String(status || "").toLowerCase() !== "running") return "";
    const matched = toolProgressMatches(name, progress);
    const label = matched ? progress.label : (name === "deeplens_curriculum" ? "课程学习" : "微调");
    const current = matched && Number.isFinite(Number(progress.current)) ? Number(progress.current) : null;
    const total = matched && Number.isFinite(Number(progress.total)) ? Number(progress.total) : null;
    const percent = matched && Number.isFinite(Number(progress.percent)) ? Math.max(0, Math.min(100, Number(progress.percent))) : null;
    const percentText = percent === null ? "同步中" : `${percent.toFixed(percent < 10 ? 1 : 0).replace(/\.0$/, "")}%`;
    const countText = current !== null && total ? `${current} / ${total}` : "读取运行状态";
    const loss = matched && progress.last_losses && Number.isFinite(Number(progress.last_losses.total_loss))
      ? " · loss " + Number(progress.last_losses.total_loss).toPrecision(4)
      : "";
    const barStyle = percent === null ? "" : " style=\"width: " + escapeHtml(percent) + "%\"";
    return "<div class=\"tool-progress" + (percent === null ? " is-indeterminate" : "") + "\">"
      + "<div class=\"tool-progress-head\"><span>" + escapeHtml(label) + "</span><strong>" + escapeHtml(percentText) + "</strong></div>"
      + "<div class=\"tool-progress-bar\"><span" + barStyle + "></span></div>"
      + "<div class=\"tool-progress-meta\">" + escapeHtml(countText + loss) + "</div>"
      + "</div>";
  }

  function renderTranscriptEvent(event, anchorTurns, completedToolStatuses, liveProgress) {
    const kind = String(event?.kind || "");
    const turn = eventTurn(event);
    if (kind === "assistant_message") {
      const text = String(event.text || event.delta || "").trim();
      if (!text) return "";
      const messageId = String(event.message_id || "").trim();
      const messageAttr = messageId ? " data-message-id=\"" + escapeHtml(messageId) + "\"" : "";
      return "<article class=\"transcript-entry transcript-entry--assistant\"" + turnAnchorAttrs(turn, anchorTurns) + messageAttr + ">"
        + "<div class=\"transcript-avatar\">A</div>"
        + "<div class=\"transcript-bubble\"><div class=\"transcript-meta\">第 " + escapeHtml(turnDisplay(turn)) + " 轮 · 智能体</div>"
        + "<p>" + escapeHtml(text) + "</p></div>"
        + "</article>";
    }
    if (kind === "tool_call") {
      const toolCall = isPlainObject(event.tool_call)
        ? event.tool_call
        : { name: event.tool || event.action || "tool", arguments: event.arguments || event.action_input || {} };
      const eventKey = toolEventKey(event, toolCall, "tool-call");
      const status = completedToolStatuses?.get(eventKey) || event.status || "running";
      return "<article class=\"transcript-entry transcript-entry--tool transcript-entry--tool-call\"" + turnAnchorAttrs(turn, anchorTurns) + ">"
        + "<div class=\"transcript-avatar\">T</div>"
        + "<div class=\"transcript-bubble\"><div class=\"transcript-meta\">第 " + escapeHtml(turnDisplay(turn)) + " 轮 · 工具调用</div>"
        + "<div class=\"tool-call-line\"><strong>" + escapeHtml(toolCall.name || event.tool || "tool") + "</strong><span>" + escapeHtml(traceStatusLabel(status, "tool-call")) + "</span></div>"
        + renderToolProgress(toolCall.name || event.tool || "tool", status, liveProgress)
        + renderDetails("参数", toolCall.arguments || event.arguments, traceDetailKey("tool-call", turn, eventKey, "arguments"))
        + renderDetails("中间结果", event.partial_result, traceDetailKey("tool-call", turn, eventKey, "partial-result"))
        + "</div></article>";
    }
    if (kind === "tool_result") {
      const toolResult = isPlainObject(event.tool_result) ? event.tool_result : {};
      const ok = event.ok ?? toolResult.ok;
      const status = ok === false ? "error" : "ok";
      const details = resultDetailPayload(event, toolResult);
      const eventKey = toolEventKey(event, toolResult, "tool-result");
      return "<article class=\"transcript-entry transcript-entry--tool transcript-entry--tool-result transcript-entry--" + escapeHtml(status) + "\"" + turnAnchorAttrs(turn, anchorTurns) + ">"
        + "<div class=\"transcript-avatar\">R</div>"
        + "<div class=\"transcript-bubble\"><div class=\"transcript-meta\">第 " + escapeHtml(turnDisplay(turn)) + " 轮 · 工具结果"
        + (event.duration_ms !== undefined ? " · " + escapeHtml(formatTraceDuration(event.duration_ms)) : "")
        + "</div>"
        + "<div class=\"tool-call-line\"><strong>" + escapeHtml(event.tool || toolResult.tool || "result") + "</strong><span>" + escapeHtml(traceStatusLabel(status, "tool-result")) + "</span></div>"
        + "<p>" + escapeHtml(event.observation || toolResult.observation || "-") + "</p>"
        + renderTraceChips(event, toolResult)
        + renderDetails("结果数据", details, traceDetailKey("tool-result", turn, eventKey, "result-data"))
        + "</div></article>";
    }
    return "";
  }

  function renderTranscriptEvents(events, liveProgress = null) {
    if (!events || !events.length) return "";
    const anchorTurns = new Set();
    const completedToolStatuses = toolCallResultStatuses(events);
    return "<div class=\"transcript-stream\">" + events.map((event) => renderTranscriptEvent(event, anchorTurns, completedToolStatuses, liveProgress)).join("") + "</div>";
  }

  function renderCaseCandidateCards(rows) {
    const candidates = (rows || []).slice(0, 3);
    if (!candidates.length) return "";
    return `
      <div class="case-candidate-grid">
        ${candidates.map((row, index) => {
          const detail = row.selection_rationale || row.design_rationale || row.description || row.snippet || "";
          return `
            <div class="case-candidate-card">
              <div class="case-candidate-head">
                <strong>${escapeHtml(row.case_id || row.candidate_id || `案例 ${index + 1}`)}</strong>
                <span>${escapeHtml(row.applied ? "已应用" : (row.selected ? "已选中" : "已检索"))}</span>
              </div>
              <p>${escapeHtml(row.title || row.category || "参考案例")}</p>
              ${detail ? `<p>${escapeHtml(detail)}</p>` : ""}
              <div class="case-candidate-meta">
                <span>${escapeHtml(row.applied ? "生成初始结构" : (row.selected ? "正在初始化与优化" : "作为参考保留"))}</span>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  function renderOptimizationStage(stage, liveProgress = null) {
    const transcriptEvents = transcriptEventsFromStage(stage);
    if (transcriptEvents.length) {
      return "<div class=\"strategy-card transcript-card\">"
        + renderTranscriptEvents(transcriptEvents, liveProgress)
        + "</div>";
    }
    return "";
  }

  function renderOptimizationProgress(events, turnCount = 0) {
    const reasoningEvents = optimizationReasoningEvents(events);
    const turns = [...new Set(reasoningEvents.map(eventTurn))].sort((a, b) => a - b);
    const count = optimizationProgressTurnCount(events, turnCount);
    if (!turns.length && !count) return "";
    const currentTurn = turns.length ? turnDisplay(turns[turns.length - 1]) : String(count);
    return "<div class=\"optimization-progress-label\">镜头优化智能体当前自主推理轮次："
      + "<strong class=\"optimization-progress-number\">" + escapeHtml(currentTurn) + "</strong>"
      + "</div>"
      + renderTurnDots(events, count);
  }

  function renderOptimizationStages(stages, liveProgress = null) {
    if (!optimizationStages) return;
    const transcriptState = captureTranscriptViewState();
    const agentStages = (stages || []).filter((stage) =>
      (Array.isArray(stage?.data?.transcript_events) && stage.data.transcript_events.length)
      || (Array.isArray(stage?.data?.agent_events) && stage.data.agent_events.length)
      || (Array.isArray(stage?.data?.react_events) && stage.data.react_events.length)
    );
    if (!agentStages.length) {
      if (optimizationProgressPanel) optimizationProgressPanel.innerHTML = "";
      optimizationStages.innerHTML = renderEmptyState("运行后显示优化智能体的原生消息、工具调用和工具结果。");
      return;
    }
    const progressEvents = agentStages.flatMap((stage) => transcriptEventsFromStage(stage));
    const turnCount = Math.max(0, ...agentStages.map((stage) => Number(stage?.data?.turn_count) || 0));
    if (optimizationProgressPanel) {
      optimizationProgressPanel.innerHTML = renderOptimizationProgress(progressEvents, turnCount);
    }
    optimizationStages.innerHTML = agentStages.map((stage) => renderOptimizationStage(stage, liveProgress)).join("");
    restoreTranscriptViewState(transcriptState);
  }

  function ensureTranscriptStream() {
    if (!optimizationStages) return null;
    const existing = optimizationStages.querySelector(".transcript-stream");
    if (existing) return existing;
    optimizationStages.innerHTML = "<div class=\"strategy-card transcript-card\" data-live-transcript=\"true\"><div class=\"transcript-stream\"></div></div>";
    return optimizationStages.querySelector(".transcript-stream");
  }

  function findAssistantMessageArticle(messageId) {
    if (!optimizationStages || !messageId) return null;
    return Array.from(optimizationStages.querySelectorAll(".transcript-entry--assistant[data-message-id]"))
      .find((entry) => entry.dataset.messageId === messageId) || null;
  }

  function handleTranscriptPayload(payload) {
    const event = payload?.transcript || payload;
    if (!event || event.kind !== "assistant_message") return;
    const text = String(event.text || event.delta || "");
    if (!text.trim()) return;
    const messageId = String(event.message_id || "").trim();
    const stream = ensureTranscriptStream();
    if (!stream) return;
    const wasAtBottom = optimizationStages.scrollTop + optimizationStages.clientHeight >= optimizationStages.scrollHeight - 32;
    let article = findAssistantMessageArticle(messageId);
    if (!article) {
      stream.insertAdjacentHTML("beforeend", renderTranscriptEvent(event, new Set(), new Map(), null));
      article = findAssistantMessageArticle(messageId) || stream.lastElementChild;
    }
    const paragraph = article?.querySelector("p");
    if (paragraph) paragraph.textContent = text.trim();
    if (wasAtBottom) optimizationStages.scrollTop = optimizationStages.scrollHeight;
  }

  function captureTranscriptViewState() {
    if (!optimizationStages) {
      return { openDetailKeys: [], detailScrollTops: {}, scrollTop: 0, turnJumpScrollLeft: 0, windowX: 0, windowY: 0 };
    }
    const detailScrollTops = {};
    const turnJumpStrip = optimizationProgressPanel?.querySelector(".turn-jump-strip");
    optimizationStages.querySelectorAll(".trace-details[data-detail-key]").forEach((details) => {
      const pre = details.querySelector("pre");
      if (pre && pre.scrollTop > 0) {
        detailScrollTops[details.dataset.detailKey] = pre.scrollTop;
      }
    });
    return {
      openDetailKeys: [...optimizationStages.querySelectorAll(".trace-details[open][data-detail-key]")]
        .map((details) => details.dataset.detailKey)
        .filter(Boolean),
      detailScrollTops,
      scrollTop: optimizationStages.scrollTop,
      turnJumpScrollLeft: turnJumpStrip?.scrollLeft || 0,
      windowX: window.scrollX,
      windowY: window.scrollY,
    };
  }

  function restoreTranscriptViewState(state) {
    if (!optimizationStages || !state) return;
    const openDetailKeys = new Set(state.openDetailKeys || []);
    if (openDetailKeys.size) {
      optimizationStages.querySelectorAll(".trace-details[data-detail-key]").forEach((details) => {
        if (openDetailKeys.has(details.dataset.detailKey)) details.open = true;
        const pre = details.querySelector("pre");
        const scrollTop = state.detailScrollTops?.[details.dataset.detailKey];
        if (pre && Number.isFinite(scrollTop)) pre.scrollTop = scrollTop;
      });
    }
    optimizationStages.scrollTop = Number(state.scrollTop) || 0;
    const turnJumpStrip = optimizationProgressPanel?.querySelector(".turn-jump-strip");
    const turnJumpScrollLeft = Number(state.turnJumpScrollLeft);
    if (turnJumpStrip && Number.isFinite(turnJumpScrollLeft)) {
      turnJumpStrip.scrollLeft = turnJumpScrollLeft;
    }
    if (Number.isFinite(state.windowX) && Number.isFinite(state.windowY)) {
      window.scrollTo(state.windowX, state.windowY);
    }
  }

  function setActiveOptimizationTurn(turn) {
    const value = Number(turn);
    if (!Number.isInteger(value) || value < 0) return;
    selectedOptimizationTurn = value;
    optimizationProgressPanel?.querySelectorAll(".turn-jump.is-active").forEach((button) => button.classList.remove("is-active"));
    Array.from(optimizationProgressPanel?.querySelectorAll(".turn-jump") || [])
      .find((button) => String(button.dataset.turnAnchor || "") === String(value))
      ?.classList.add("is-active");
  }

  function scrollTranscriptTurnIntoView(turnJump) {
    if (!optimizationStages || !turnJump) return;
    const turn = String(turnJump.dataset.turnAnchor || "");
    setActiveOptimizationTurn(turn);
    const anchorId = turnJump.dataset.turnTarget || turnAnchorId(turn);
    const target = Array.from(optimizationStages.querySelectorAll("[id], [data-turn]")).find((element) =>
      element.id === anchorId || String(element.dataset.turn || "") === turn
    );
    if (!target) return;

    const viewportRect = optimizationStages.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const scrollMarginTop = Number.parseFloat(window.getComputedStyle(target).scrollMarginTop) || 0;
    const top = optimizationStages.scrollTop + targetRect.top - viewportRect.top - scrollMarginTop;
    optimizationStages.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }

  function renderParamRail(params) {
    return `
      <div class="final-param-rail">
        ${params.map(([label, value]) => `
          <div class="param-chip">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value || "-")}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderCompletionNarrative(result, preview) {
    const stageLabel = preview.final_image_url
      ? "最终优化结果"
      : (preview.candidate_image_url ? "当前最佳候选" : (preview.curriculum_image_url ? "课程学习候选" : "初始结构"));
    const summary = String(result.summary || "").replace(/\s+/g, " ").trim();
    const fallback = preview.final_image_url
      ? "优化已完成，最终总结将在结果产物写入后显示。"
      : "候选结果已导出，智能体仍可继续分析、微调或调整策略。";
    return `
      <div class="completion-narrative">
        <span>${escapeHtml(stageLabel)}</span>
        <p>${escapeHtml(summary || fallback)}</p>
      </div>
    `;
  }

  function renderCompletionSummary(result, preview) {
    if (!preview?.final_image_url && !preview?.candidate_image_url && !preview?.curriculum_image_url && !preview?.starting_image_url) {
      return renderEmptyState("运行后显示关键结果摘要。");
    }
    const metricMap = result.metrics || {};
    const snapshotUrl = preview.final_image_url || preview.candidate_image_url || preview.curriculum_image_url || preview.starting_image_url;
    const evidenceItems = (preview.evidence?.sections || []).flatMap((section) => section.items || []);
    const rows = evidenceItems.length
      ? evidenceItems.slice(0, 6).map((item) => [
          item.label || item.key,
          formatValue(item.primary?.value, item.unit ? ` ${item.unit}` : "", 2),
        ])
      : [
          ["焦距", preview.foclen_display],
          ["F 数", preview.fnum_display],
          ["视场", preview.fov_display],
          ["边缘 RMS", formatValue(firstValue(metricMap, ["deeplens_rms_spot_um_edge", "spot_rms_um_edge"]), " um", 2)],
        ].filter(([, value]) => value && value !== "-");
    return `
      <div class="completion-summary">
        <div class="completion-thumb">
          ${snapshotUrl ? `<img class="result-image" src="${escapeHtml(snapshotUrl)}" alt="优化结果摘要">` : renderEmptyState(zh.imageWaiting, { title: zh.imagePendingTitle, tone: "image" })}
        </div>
        ${renderCompletionNarrative(result, preview)}
        <div class="completion-chip-grid">
          ${(rows.length ? rows : [["指标", "等待写入"]]).slice(0, 6).map(([label, value]) => `
            <div class="completion-chip">
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(value || "-")}</strong>
            </div>
          `).join("")}
        </div>
        <button type="button" class="result-link-action" data-view-jump="results">查看完整结果</button>
      </div>
    `;
  }

  function renderArtifacts(result, { renderFinalDesign = true } = {}) {
    const preview = result.preview || null;
    const zemaxFigures = preview && preview.zemax_figures ? preview.zemax_figures : [];
    if (!preview || (!preview.starting_image_url && !preview.curriculum_image_url && !preview.candidate_image_url && !preview.final_image_url && !zemaxFigures.length)) {
      artifacts.innerHTML = renderEmptyState(zh.artifactsEmpty);
      renderOptimizationStages(preview?.optimization_stages || [], preview?.deeplens_progress);
      if (renderFinalDesign) {
        if (initialStructure) {
          initialStructure.innerHTML = renderEmptyState("\u8fd0\u884c\u540e\u663e\u793a\u521d\u59cb\u7ed3\u6784\u3002");
        }
        if (currentSnapshot) {
          currentSnapshot.innerHTML = renderEmptyState(zh.snapshotPending);
        }
        if (lensStageGallery) {
          lensStageGallery.innerHTML = renderEmptyState("运行后显示关键结果摘要。");
        }
      }
      renderFileMeta(result);
      return;
    }
    renderOptimizationStages(preview.optimization_stages || [], preview.deeplens_progress);

    if (initialStructure) {
      initialStructure.innerHTML = renderImagePanel({
        title: "\u521d\u59cb\u7ed3\u6784",
        url: preview.starting_image_url,
        kind: "small",
        showHead: false,
      });
    }
    if (currentSnapshot) {
      const snapshotUrl = preview.current_image_url || preview.curriculum_image_url || preview.starting_image_url;
      const snapshotLabel = preview.current_image_url
        ? "\u5f53\u524d\u4f18\u5316\u5feb\u7167"
        : (preview.curriculum_image_url ? "\u8bfe\u7a0b\u5b66\u4e60\u5019\u9009" : "\u521d\u59cb\u7ed3\u6784");
      currentSnapshot.innerHTML = renderImagePanel({
        title: zh.currentSnapshot,
        subtitle: snapshotLabel,
        url: snapshotUrl,
        kind: "small",
        showHead: false,
      });
    }
    if (lensStageGallery && renderFinalDesign) {
      lensStageGallery.innerHTML = renderCompletionSummary(result, preview);
    }

    const zemaxSection = zemaxFigures.length
      ? `<div class="zemax-strip">${zemaxFigures.map((figure) => renderImagePanel({
          title: figure.title || "Zemax \u56fe\u8868",
          subtitle: figure.subtitle || "\u7531 final.zmx \u751f\u6210",
          url: figure.url,
          kind: figure.role === "zemax_spot_diagram" ? "zemax zemax-wide" : "zemax",
        })).join("")}</div>`
      : (preview.zemax_error ? renderEmptyState(`${zh.zemaxPending}${preview.zemax_error}`, { title: zh.imagePendingTitle, tone: "image" }) : "");

    artifacts.innerHTML = `
      <div class="result-gallery">
        ${zemaxSection || renderEmptyState(zh.artifactsEmpty)}
      </div>
    `;
    renderFileMeta(result);
  }

  function renderReferences(rows) {
    const coreRows = (rows || [])
      .filter((row) => row.inspected || row.selected || row.applied)
      .slice(0, 3);
    if (!coreRows.length) {
      references.innerHTML = renderEmptyState(zh.refsEmpty);
      return;
    }
    references.innerHTML = renderCaseCandidateCards(coreRows);
  }

  function resetView() {
    if (currentSource) {
      currentSource.close();
      currentSource = null;
    }
    stopPreviewPolling();
    streamCompleted = false;
    seenEventIds = new Set();
    lastTimelineText = "";
    selectedOptimizationTurn = null;
    stopElapsedTimer();
    runStartTime = null;
    elapsedPill.textContent = "00:00";
    resetTimeline();
    metrics.innerHTML = renderEmptyState(zh.metricsEmpty);
    artifacts.innerHTML = renderEmptyState(zh.artifactsEmpty);
    if (initialStructure) {
      initialStructure.innerHTML = renderEmptyState("\u8fd0\u884c\u540e\u663e\u793a\u521d\u59cb\u7ed3\u6784\u3002");
    }
    if (currentSnapshot) {
      currentSnapshot.innerHTML = renderEmptyState(zh.snapshotPending);
    }
    if (lensStageGallery) {
      lensStageGallery.innerHTML = renderEmptyState("运行后显示关键结果摘要。");
    }
    renderOptimizationStages([], null);
    references.innerHTML = renderEmptyState(zh.refsEmpty);
    fileMeta.innerHTML = renderEmptyState(zh.filesEmpty);
    renderReport(null);
    runBtn.disabled = false;
    setStatus("idle", zh.waitTask);
  }

  function fillDefaults() {
    const params = defaultParams;
    const llm = defaults.llm || {};
    setInputValue("nl_prompt", zh.defaultPrompt);
    setInputValue("foclen", params.foclen ?? 50);
    setInputValue("fov", params.fov ?? 43);
    setInputValue("fnum", params.fnum ?? 3.0);
    setInputValue("bfl", params.bfl ?? 18);
    setInputValue("thickness", params.thickness ?? 75);
    setInputValue("llm_base_url", llm.base_url || "");
    setInputValue("llm_model", llm.model || "");
    setInputValue("llm_temperature", llm.temperature ?? 0.3);
    setInputValue("optimization_max_turns", defaults.optimization?.max_turns ?? 50);
    setInputValue("engine_seed", params.seed);
    setInputValue("engine_lr_scale", params.lr_scale ?? 1.0);
    initialModel = llm.model || "";
    customBaseUrl = llm.provider === "custom" ? (llm.base_url || "") : "";
    customModel = llm.provider === "custom" ? (llm.model || "") : "";
    initialProvider = syncProviderTabs(llm.provider || "");
    setInputValue("iterations", params.curriculum?.iterations ?? 2000);
    setInputValue("spp", params.curriculum?.spp ?? "");
    setInputValue("test_per_iter", params.curriculum?.test_per_iter ?? "");
    setInputValue("curriculum_num_ring", params.curriculum?.num_ring ?? "");
    setInputValue("curriculum_num_arm", params.curriculum?.num_arm ?? "");
    setInputValue("fine_tune_iterations", params.fine_tune?.iterations ?? 5000);
    setInputValue("fine_tune_spp", params.fine_tune?.spp ?? "");
    setInputValue("fine_tune_test_per_iter", params.fine_tune?.test_per_iter ?? "");
    setInputValue("fine_tune_num_ring", params.fine_tune?.num_ring ?? "");
    setInputValue("fine_tune_num_arm", params.fine_tune?.num_arm ?? "");
  }

  function readApiConfig() {
    return {
      max_turns: numberValue("optimization_max_turns"),
      llm: {
        base_url: textValue("llm_base_url"),
        api_key: textValue("llm_api_key"),
        model: textValue("llm_model"),
        temperature: numberValue("llm_temperature"),
      },
    };
  }

  function readEngineConfig() {
    return {
      seed: numberValue("engine_seed"),
      lr_scale: numberValue("engine_lr_scale"),
      curriculum: {
        iterations: numberValue("iterations"),
        spp: numberValue("spp"),
        test_per_iter: numberValue("test_per_iter"),
        num_ring: numberValue("curriculum_num_ring"),
        num_arm: numberValue("curriculum_num_arm"),
      },
      fine_tune: {
        iterations: numberValue("fine_tune_iterations"),
        spp: numberValue("fine_tune_spp"),
        test_per_iter: numberValue("fine_tune_test_per_iter"),
        num_ring: numberValue("fine_tune_num_ring"),
        num_arm: numberValue("fine_tune_num_arm"),
      },
    };
  }

  function confirmConfig(kind) {
    const panel = document.getElementById(`${kind}-config-panel`);
    for (const input of panel.querySelectorAll("input")) {
      if (!input.reportValidity()) return;
    }
    if (kind === "api") {
      confirmedApiConfig = readApiConfig();
      confirmedApiConfig.max_turns_is_limit = confirmedApiConfig.max_turns !== null;
    } else {
      confirmedEngineConfig = readEngineConfig();
    }
    document.getElementById(`${kind}-config-status`).textContent = "已确认，下次运行生效（当前页面）";
  }

  async function startRun() {
    if (currentSource) {
      currentSource.close();
      currentSource = null;
    }
    stopPreviewPolling();
    streamCompleted = false;
    seenEventIds = new Set();
    lastTimelineText = "";
    selectedOptimizationTurn = null;
    runBtn.disabled = true;
    setView("run");
    startElapsedTimer();
    timeline.innerHTML = "";
    lastTimelineText = "";
    metrics.innerHTML = renderRunningState();
    artifacts.innerHTML = renderRunningState();
    if (initialStructure) initialStructure.innerHTML = renderRunningState();
    if (currentSnapshot) currentSnapshot.innerHTML = renderRunningState();
    if (lensStageGallery) lensStageGallery.innerHTML = renderRunningState();
    renderOptimizationStages([], null);
    references.innerHTML = renderRunningState();
    fileMeta.innerHTML = renderRunningState();
    renderReport(null);
    if (reportStage) reportStage.innerHTML = renderRunningState("正在整理光学镜头设计总结报告...");

    const payload = {
      mode: currentMode,
      nl_prompt: document.getElementById("nl_prompt").value,
      foclen: Number(document.getElementById("foclen").value),
      fov: Number(document.getElementById("fov").value),
      fnum: Number(document.getElementById("fnum").value),
      bfl: Number(document.getElementById("bfl").value),
      thickness: Number(document.getElementById("thickness").value),
      ...confirmedApiConfig,
      ...confirmedEngineConfig,
    };

    setStatus("running", zh.creatingRun);
    const rsp = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await rsp.json();
    if (!rsp.ok) {
      stopElapsedTimer();
      runStartTime = null;
      elapsedPill.textContent = "00:00";
      runBtn.disabled = false;
      setStatus("error", data.error || zh.createFailed);
      return;
    }

    currentSource = new EventSource(`/api/stream?run_id=${encodeURIComponent(data.run_id)}`);
    currentSource.addEventListener("progress", (event) => {
      if (!shouldHandleEvent(event)) return;
      const payload = JSON.parse(event.data);
      appendTimeline(payload);
      setStatus("running", payload.message);
    });
    currentSource.addEventListener("artifact", (event) => {
      if (!shouldHandleEvent(event)) return;
      handleArtifactPayload(JSON.parse(event.data));
    });
    currentSource.addEventListener("transcript", (event) => {
      if (!shouldHandleEvent(event)) return;
      handleTranscriptPayload(JSON.parse(event.data));
    });
    currentSource.addEventListener("references", (event) => {
      if (!shouldHandleEvent(event)) return;
      const payload = JSON.parse(event.data);
      renderReferences(payload.references || []);
    });
    currentSource.addEventListener("result", (event) => {
      if (!shouldHandleEvent(event)) return;
      const payload = JSON.parse(event.data);
      streamCompleted = true;
      stopPreviewPolling();
      stopElapsedTimer();
      refreshElapsed();
      renderMetricCards(payload.metrics || {});
      renderArtifacts(payload, { renderFinalDesign: true });
      renderReport(payload);
      renderReferences(payload.references || []);
      const summary = payload.summary || zh.runFailed;
      setStatus(payload.ok ? "done" : "error", payload.ok ? zh.designDone : summary);
    });
    currentSource.addEventListener("run_error", (event) => {
      if (!shouldHandleEvent(event)) return;
      const payload = JSON.parse(event.data);
      streamCompleted = true;
      stopPreviewPolling();
      stopElapsedTimer();
      refreshElapsed();
      runBtn.disabled = false;
      appendTimeline(payload.message ? payload : { message: zh.runFailed, title: zh.error, level: "error" });
      setStatus("error", payload.message || zh.runFailed);
    });
    currentSource.addEventListener("done", () => {
      streamCompleted = true;
      stopPreviewPolling();
      runBtn.disabled = false;
      if (currentSource) {
        currentSource.close();
        currentSource = null;
      }
    });
    currentSource.onerror = () => {
      if (streamCompleted) {
        stopPreviewPolling();
        stopElapsedTimer();
        refreshElapsed();
        runBtn.disabled = false;
        if (currentSource) {
          currentSource.close();
          currentSource = null;
        }
        return;
      }
      setStatus("running", zh.reconnecting);
    };
  }

  modeButtons.forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
  providerButtons.forEach((button) => button.addEventListener("click", () => selectProvider(button)));
  document.getElementById("llm_base_url")?.addEventListener("input", () => {
    const active = syncProviderTabs();
    if (active === "custom") {
      customBaseUrl = textValue("llm_base_url");
    }
  });
  document.getElementById("llm_model")?.addEventListener("input", () => {
    const activeProvider = document.querySelector("#llm-provider-tabs button.active")?.dataset.provider;
    if (activeProvider === "custom") {
      customModel = textValue("llm_model");
    }
  });
  viewButtons.forEach((button) => button.addEventListener("click", (event) => {
    event.preventDefault();
    setView(button.dataset.view);
  }));
  document.addEventListener("click", (event) => {
    const viewJump = event.target.closest("[data-view-jump]");
    if (viewJump) {
      event.preventDefault();
      setView(viewJump.dataset.viewJump);
      return;
    }
    const turnJump = event.target.closest("[data-turn-anchor]");
    if (turnJump && optimizationStages) {
      event.preventDefault();
      scrollTranscriptTurnIntoView(turnJump);
    }
  });
  window.addEventListener("hashchange", () => setView(window.location.hash.replace("#", "") || "run"));
  runBtn.addEventListener("click", startRun);
  resetBtn.addEventListener("click", resetView);

  fillDefaults();
  confirmedApiConfig = readApiConfig();
  confirmedEngineConfig = readEngineConfig();
  for (const kind of ["api", "engine"]) {
    document.getElementById(`confirm-${kind}-config`).addEventListener("click", () => confirmConfig(kind));
    const markDraft = () => {
      document.getElementById(`${kind}-config-status`).textContent = "有未确认修改，下次运行仍使用已确认配置";
    };
    const panel = document.getElementById(`${kind}-config-panel`);
    panel.addEventListener("input", markDraft);
    panel.querySelectorAll("[data-provider]").forEach((button) => button.addEventListener("click", markDraft));
  }
  if (modelPill) {
    modelPill.textContent = defaults.llm?.model || zh.modelMissing;
    modelPill.title = defaults.llm?.base_url || "";
  }
  setMode((modeButtons.find((button) => button.classList.contains("active")) || modeButtons[0])?.dataset.mode);
  setView(window.location.hash.replace("#", "") || "run");
  resetView();
  renderMetricCards({});
})();
