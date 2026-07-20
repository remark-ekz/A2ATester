const state = {
  profiles: [],
  profile: null,
  conversations: [],
  conversation: null,
  selectedProfileId: null,
  selectedConversationId: null,
  theme: "studio",
  palettes: [],
  chatListLimit: 20,
  busy: false,
  busyLabel: "",
  busyStartedAt: 0,
  busyTimer: null,
  currentAbortController: null,
};

const $ = (id) => document.getElementById(id);

const els = {
  status: $("statusText"),
  profileSelect: $("profileSelect"),
  paletteSelect: $("paletteSelect"),
  chatListLimit: $("chatListLimit"),
  chatList: $("chatList"),
  deleteProfile: $("deleteProfileBtn"),
  profileName: $("profileName"),
  endpoint: $("endpoint"),
  agentCardRoute: $("agentCardRoute"),
  messageSendRoute: $("messageSendRoute"),
  messageStreamRoute: $("messageStreamRoute"),
  tasksGetRoute: $("tasksGetRoute"),
  tasksCancelRoute: $("tasksCancelRoute"),
  protocolVersion: $("protocolVersion"),
  tenant: $("tenant"),
  tenantField: $("tenantField"),
  protocolHint: $("protocolHint"),
  routesSummaryText: $("routesSummaryText"),
  routesHint: $("routesHint"),
  protocolTransport: $("protocolTransport"),
  protocolRole: $("protocolRole"),
  protocolPart: $("protocolPart"),
  protocolTenant: $("protocolTenant"),
  agentCardRouteLabel: $("agentCardRouteLabel"),
  messageSendRouteLabel: $("messageSendRouteLabel"),
  messageStreamRouteLabel: $("messageStreamRouteLabel"),
  tasksGetRouteLabel: $("tasksGetRouteLabel"),
  tasksCancelRouteLabel: $("tasksCancelRouteLabel"),
  timeoutSeconds: $("timeoutSeconds"),
  tlsVerify: $("tlsVerify"),
  caBundlePath: $("caBundlePath"),
  caBundleFile: $("caBundleFile"),
  clientCertPath: $("clientCertPath"),
  clientCertFile: $("clientCertFile"),
  clientKeyPath: $("clientKeyPath"),
  clientKeyFile: $("clientKeyFile"),
  metadataJson: $("metadataJson"),
  taskId: $("taskId"),
  taskIdLabel: $("taskIdLabel"),
  getTask: $("getTaskBtn"),
  cancelTask: $("cancelTaskBtn"),
  taskResult: $("taskResult"),
  agentCard: $("agentCard"),
  headerRows: $("headerRows"),
  conversationMeta: $("conversationMeta"),
  chatPane: $("chatPane"),
  messageInput: $("messageInput"),
  diagnostics: $("diagnostics"),
  stopRequest: $("stopRequestBtn"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  return response.json();
}

function setStatus(text) {
  els.status.textContent = localizeStatus(text);
}

function localizeStatus(text) {
  const value = String(text || "");
  if (!value) return "Готово";
  if (value.includes(" · ")) {
    const [base, ...tail] = value.split(" · ");
    return `${localizeStatus(base)} · ${tail.join(" · ")}`;
  }
  const exact = {
    Ready: "Готово",
    "Request completed": "Запрос выполнен",
    "Stream completed": "Stream завершен",
    "Streaming...": "Stream идет...",
    "Agent Card loaded": "Agent Card загружена",
    "Chat deleted": "Чат удален",
    "message/send completed": "message/send выполнен",
    "message/stream completed": "message/stream выполнен",
    "tasks/get completed": "tasks/get выполнен",
    "tasks/cancel completed": "tasks/cancel выполнен",
  };
  if (exact[value]) return exact[value];
  if (value.startsWith("Input required for task")) {
    return value.replace("Input required for task", "Требуется ввод для задачи");
  }
  if (value.startsWith("Stream error:")) {
    return value.replace("Stream error:", "Ошибка stream:");
  }
  return value;
}

function setBusy(busy, label = "Ждем ответ") {
  state.busy = busy;
  document.body.dataset.busy = busy ? "true" : "false";
  for (const id of ["sendBtn", "streamBtn", "saveProfileBtn", "deleteProfileBtn", "agentCardBtn", "getTaskBtn", "cancelTaskBtn", "chatListLimit", "addHeaderBtn"]) {
    $(id).disabled = busy;
  }
  els.stopRequest.hidden = !busy;
  els.stopRequest.disabled = !busy;
  for (const button of document.querySelectorAll(".chat-delete, .header-save, .header-delete")) {
    button.disabled = busy;
  }
  if (busy) {
    startBusyTimer(label);
  } else {
    stopBusyTimer();
  }
}

function beginCancelableRequest(label) {
  const controller = new AbortController();
  state.currentAbortController = controller;
  setBusy(true, label);
  return controller;
}

function finishCancelableRequest(controller) {
  if (state.currentAbortController === controller) {
    state.currentAbortController = null;
  }
  setBusy(false);
}

function stopCurrentRequest() {
  if (!state.currentAbortController) return;
  els.stopRequest.disabled = true;
  state.currentAbortController.abort();
  setStatus("Вызов остановлен пользователем");
}

function isAbortError(error) {
  return error?.name === "AbortError" || String(error?.message || "").toLowerCase().includes("abort");
}

function startBusyTimer(label) {
  stopBusyTimer(false);
  state.busyLabel = label;
  state.busyStartedAt = performance.now();
  updateBusyStatus();
  state.busyTimer = window.setInterval(updateBusyStatus, 250);
}

function stopBusyTimer(resetStatus = true) {
  if (state.busyTimer) {
    window.clearInterval(state.busyTimer);
    state.busyTimer = null;
  }
  if (resetStatus && state.busyLabel) {
    state.busyLabel = "";
    state.busyStartedAt = 0;
  }
}

function updateBusyStatus() {
  if (!state.busyStartedAt) return;
  const elapsed = Math.max(0, (performance.now() - state.busyStartedAt) / 1000);
  setStatus(`${state.busyLabel} · ${elapsed.toFixed(1)}s`);
}

function statusWithLatency(status, conversation = state.conversation) {
  const latest = conversation?.diagnostics?.at(-1);
  if (!latest?.latencyMs || /streaming/i.test(status || "")) {
    return status || "Готово";
  }
  return `${status || "Готово"} · ${(latest.latencyMs / 1000).toFixed(1)}s`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortId(value) {
  const text = String(value || "");
  return text.length <= 12 ? text : `${text.slice(0, 8)}...${text.slice(-4)}`;
}

function profileFormPayload() {
  return {
    name: els.profileName.value.trim(),
    endpoint: els.endpoint.value.trim(),
    routes: {
      agentCard: els.agentCardRoute.value.trim(),
      messageSend: els.messageSendRoute.value.trim(),
      messageStream: els.messageStreamRoute.value.trim(),
      tasksGet: els.tasksGetRoute.value.trim(),
      tasksCancel: els.tasksCancelRoute.value.trim(),
    },
    protocolVersion: els.protocolVersion.value,
    tenant: els.tenant.value.trim(),
    timeoutSeconds: Number(els.timeoutSeconds.value || 60),
    tlsVerify: els.tlsVerify.checked,
    caBundlePath: els.caBundlePath.value.trim(),
    clientCertPath: els.clientCertPath.value.trim(),
    clientKeyPath: els.clientKeyPath.value.trim(),
    metadataJson: els.metadataJson.value.trim() || "{}",
    headers: state.profile?.headers || [],
  };
}

function syncProfileDraftFromForm() {
  if (!state.profile) return;
  Object.assign(state.profile, profileFormPayload());
}

async function saveProfile(showStatus = true) {
  if (!state.selectedProfileId) return;
  syncProfileDraftFromForm();
  const payload = profileFormPayload();
  JSON.parse(payload.metadataJson || "{}");
  const data = await api(`/api/profiles/${state.selectedProfileId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  state.profile = data.profile;
  state.profiles = data.profiles;
  renderProfileSelect();
  renderHeaderRows();
  if (showStatus) setStatus("Соединение сохранено");
}

function applyState(data) {
  Object.assign(state, data);
  document.body.dataset.theme = state.theme || "studio";
  renderAll();
}

function renderAll() {
  renderProfileSelect();
  renderPaletteSelect();
  renderChatListLimit();
  renderProfileForm();
  renderHeaderRows();
  renderConversations();
  renderConversation();
}

function renderProfileSelect() {
  els.profileSelect.innerHTML = state.profiles
    .map((profile) => `<option value="${profile.id}">${escapeHtml(profile.name)} - ${escapeHtml(profile.endpoint || "без endpoint")}</option>`)
    .join("");
  if (state.selectedProfileId) els.profileSelect.value = String(state.selectedProfileId);
}

function renderPaletteSelect() {
  els.paletteSelect.innerHTML = state.palettes
    .map((palette) => `<option value="${palette.key}">${escapeHtml(palette.name)}</option>`)
    .join("");
  els.paletteSelect.value = state.theme || "studio";
}

function renderChatListLimit() {
  els.chatListLimit.value = String(state.chatListLimit || 20);
}

function renderProfileForm() {
  const profile = state.profile;
  if (!profile) return;
  els.profileName.value = profile.name || "";
  els.endpoint.value = profile.endpoint || "";
  els.agentCardRoute.value = profile.routes?.agentCard || "";
  els.messageSendRoute.value = profile.routes?.messageSend || "";
  els.messageStreamRoute.value = profile.routes?.messageStream || "";
  els.tasksGetRoute.value = profile.routes?.tasksGet || "";
  els.tasksCancelRoute.value = profile.routes?.tasksCancel || "";
  els.protocolVersion.value = profile.protocolVersion || "1.0";
  els.tenant.value = profile.tenant || "";
  els.timeoutSeconds.value = profile.timeoutSeconds || 60;
  els.tlsVerify.checked = Boolean(profile.tlsVerify);
  els.caBundlePath.value = profile.caBundlePath || "";
  els.clientCertPath.value = profile.clientCertPath || "";
  els.clientKeyPath.value = profile.clientKeyPath || "";
  els.metadataJson.value = profile.metadataJson || "{}";
  renderProtocolControls();
}

function renderProtocolControls() {
  const version = els.protocolVersion.value || "1.0";
  const isV1 = version === "1.0";
  const methods = isV1
    ? {
        send: "SendMessage",
        stream: "SendStreamingMessage",
        get: "GetTask",
        cancel: "CancelTask",
      }
    : {
        send: "message/send",
        stream: "message/stream",
        get: "tasks/get",
        cancel: "tasks/cancel",
      };

  els.tenantField.hidden = !isV1;
  els.protocolHint.textContent = isV1
    ? "A2A 1.0: используется роль ROLE_USER, текстовая часть с mediaType и, при необходимости, контур tenant. Заголовок A2A-Version добавляется автоматически."
    : `A2A ${version}: используется роль user и текстовая часть kind: text. Контур tenant не передается; заголовок A2A-Version добавляется автоматически.`;
  els.routesSummaryText.textContent = `Ручки запросов A2A ${version}`;
  els.routesHint.textContent = "Все операции используют JSON-RPC по адресу агента. Оставьте поле пустым, чтобы использовать этот адрес; укажите путь или полный URL только для переопределения конкретной операции.";
  els.protocolTransport.textContent = "JSON-RPC 2.0";
  els.protocolRole.textContent = isV1 ? "ROLE_USER" : "user";
  els.protocolPart.textContent = isV1 ? "text + mediaType" : "kind: text + text";
  els.protocolTenant.textContent = isV1 ? "params.tenant" : "не передается";
  els.agentCardRouteLabel.textContent = "Карточка агента (Agent Card)";
  els.messageSendRouteLabel.textContent = `Отправить сообщение (${methods.send})`;
  els.messageStreamRouteLabel.textContent = `Поток сообщений (${methods.stream})`;
  els.tasksGetRouteLabel.textContent = `Получить задачу (${methods.get})`;
  els.tasksCancelRouteLabel.textContent = `Отменить задачу (${methods.cancel})`;
  els.messageSendRoute.placeholder = "пусто = адрес агента";
  els.messageStreamRoute.placeholder = "пусто = адрес агента";
  els.tasksGetRoute.placeholder = "пусто = адрес агента";
  els.tasksCancelRoute.placeholder = "пусто = адрес агента";
  els.taskIdLabel.textContent = `Идентификатор задачи (Task ID) для ${methods.get} / ${methods.cancel}`;
  els.getTask.textContent = `Получить (${methods.get})`;
  els.cancelTask.textContent = `Отменить (${methods.cancel})`;
}

function renderConversations() {
  els.chatList.innerHTML = "";
  for (const conversation of state.conversations) {
    const item = document.createElement("div");
    item.className = `chat-item ${conversation.id === state.selectedConversationId ? "active" : ""}`;

    const selectButton = document.createElement("button");
    selectButton.className = "chat-select";
    selectButton.innerHTML = `
      <strong>${escapeHtml(conversation.title)}</strong>
      <span class="chat-preview">${escapeHtml(conversation.preview || "Сообщений пока нет")}</span>
      <span class="chat-context">${escapeHtml(shortId(conversation.contextId))}</span>
    `;
    selectButton.addEventListener("click", () => selectConversation(conversation.id));

    const deleteButton = document.createElement("button");
    deleteButton.className = "chat-delete";
    deleteButton.type = "button";
    deleteButton.title = "Удалить чат";
    deleteButton.textContent = "Удалить";
    deleteButton.disabled = state.busy;
    deleteButton.addEventListener("click", () => deleteConversation(conversation.id));

    item.append(selectButton, deleteButton);
    els.chatList.appendChild(item);
  }
}

function clearTaskResult() {
  if (els.taskResult) {
    els.taskResult.textContent = "";
  }
}

function renderConversation() {
  const conversation = state.conversation;
  if (!conversation) {
    els.conversationMeta.innerHTML = "";
    els.chatPane.innerHTML = '<div class="empty-chat">Чат не выбран.</div>';
    els.diagnostics.textContent = "[]";
    return;
  }

  els.taskId.value = conversation.taskId || "";
  const chips = [
    `Context: ${conversation.contextId || "не задан"}`,
    conversation.taskId ? `Task: ${conversation.taskId}` : "",
    conversation.taskState ? `State: ${conversation.taskState}` : "",
    conversation.inputRequired ? "Требуется ввод" : "",
  ].filter(Boolean);
  els.conversationMeta.innerHTML = chips.map((chip) => `<span class="meta-chip">${escapeHtml(chip)}</span>`).join("");

  if (!conversation.messages?.length) {
    els.chatPane.innerHTML = '<div class="empty-chat">Сообщений пока нет.</div>';
  } else {
    els.chatPane.innerHTML = conversation.messages.map(renderMessage).join("");
    els.chatPane.scrollTop = els.chatPane.scrollHeight;
  }
  els.diagnostics.textContent = JSON.stringify(conversation.diagnostics || [], null, 2);
}

function renderMessage(message) {
  const side = message.role === "user" ? "right" : "left";
  const kind = bubbleKind(message);
  const label = messageLabel(message);
  return `
    <div class="message-row ${side}">
      <div class="bubble ${kind}">
        <div class="bubble-label">${escapeHtml(label)}</div>
        <div class="markdown-body">${renderMarkdown(message.text || "")}</div>
      </div>
    </div>
  `;
}

function renderMarkdown(value) {
  const text = String(value ?? "").replace(/\r\n?/g, "\n");
  return splitMarkdownFences(text)
    .map((segment) => {
      if (segment.type === "code") {
        const language = segment.language ? ` data-language="${escapeAttribute(segment.language)}"` : "";
        return `<pre class="md-code"${language}><code>${escapeHtml(segment.text)}</code></pre>`;
      }
      return renderMarkdownBlocks(segment.text);
    })
    .join("");
}

function splitMarkdownFences(text) {
  const segments = [];
  const lines = text.split("\n");
  let textBuffer = [];
  let codeBuffer = [];
  let fenceChar = "";
  let fenceLength = 0;
  let language = "";

  const flushText = () => {
    if (textBuffer.length) {
      segments.push({ type: "text", text: textBuffer.join("\n") });
      textBuffer = [];
    }
  };

  for (const line of lines) {
    const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})\s*([^`]*)$/);
    if (!fenceChar && fenceMatch) {
      flushText();
      fenceChar = fenceMatch[1][0];
      fenceLength = fenceMatch[1].length;
      language = String(fenceMatch[2] || "").trim().split(/\s+/)[0] || "";
      codeBuffer = [];
      continue;
    }

    if (fenceChar) {
      const closeMatch = line.match(/^ {0,3}(`{3,}|~{3,})\s*$/);
      if (closeMatch && closeMatch[1][0] === fenceChar && closeMatch[1].length >= fenceLength) {
        segments.push({ type: "code", text: codeBuffer.join("\n"), language });
        fenceChar = "";
        fenceLength = 0;
        language = "";
        codeBuffer = [];
      } else {
        codeBuffer.push(line);
      }
      continue;
    }

    textBuffer.push(line);
  }

  if (fenceChar) {
    segments.push({ type: "code", text: codeBuffer.join("\n"), language });
  }
  flushText();
  return segments;
}

function renderMarkdownBlocks(text) {
  const lines = text.split("\n");
  const html = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const heading = line.match(/^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      const level = heading[1].length;
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^ {0,3}([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
      html.push("<hr>");
      index += 1;
      continue;
    }

    if (/^ {0,3}>\s?/.test(line)) {
      const quoteLines = [];
      while (index < lines.length && /^ {0,3}>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^ {0,3}>\s?/, ""));
        index += 1;
      }
      html.push(`<blockquote>${renderMarkdownBlocks(quoteLines.join("\n"))}</blockquote>`);
      continue;
    }

    if (isMarkdownTableStart(lines, index)) {
      const { markup, nextIndex } = renderMarkdownTable(lines, index);
      html.push(markup);
      index = nextIndex;
      continue;
    }

    const unordered = line.match(/^ {0,3}[-*+]\s+(.+)$/);
    if (unordered) {
      const items = [];
      while (index < lines.length) {
        const item = lines[index].match(/^ {0,3}[-*+]\s+(.+)$/);
        if (!item) break;
        items.push(`<li>${renderInlineMarkdown(item[1])}</li>`);
        index += 1;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    const ordered = line.match(/^ {0,3}\d+[.)]\s+(.+)$/);
    if (ordered) {
      const items = [];
      while (index < lines.length) {
        const item = lines[index].match(/^ {0,3}\d+[.)]\s+(.+)$/);
        if (!item) break;
        items.push(`<li>${renderInlineMarkdown(item[1])}</li>`);
        index += 1;
      }
      html.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    const paragraphLines = [];
    while (index < lines.length && lines[index].trim() && !isMarkdownBlockStart(lines, index)) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    if (paragraphLines.length) {
      html.push(`<p>${paragraphLines.map(renderInlineMarkdown).join("<br>")}</p>`);
    } else {
      index += 1;
    }
  }

  return html.join("");
}

function isMarkdownBlockStart(lines, index) {
  const line = lines[index] || "";
  return (
    /^ {0,3}(#{1,6})\s+/.test(line) ||
    /^ {0,3}([-*_])(?:\s*\1){2,}\s*$/.test(line) ||
    /^ {0,3}>\s?/.test(line) ||
    /^ {0,3}[-*+]\s+/.test(line) ||
    /^ {0,3}\d+[.)]\s+/.test(line) ||
    isMarkdownTableStart(lines, index)
  );
}

function isMarkdownTableStart(lines, index) {
  const header = lines[index] || "";
  const separator = lines[index + 1] || "";
  return header.includes("|") && /^ {0,3}\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(separator);
}

function renderMarkdownTable(lines, index) {
  const rows = [];
  rows.push(splitMarkdownTableRow(lines[index]));
  index += 2;
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    rows.push(splitMarkdownTableRow(lines[index]));
    index += 1;
  }

  const header = rows.shift() || [];
  const head = header.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`)
    .join("");
  return {
    markup: `<div class="md-table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`,
    nextIndex: index,
  };
}

function splitMarkdownTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderInlineMarkdown(value) {
  let text = String(value ?? "");
  const tokens = [];
  const remember = (html) => {
    tokens.push(html);
    return `\u0000${tokens.length - 1}\u0000`;
  };

  text = text.replace(/`([^`\n]+)`/g, (_, code) => remember(`<code>${escapeHtml(code)}</code>`));
  text = text.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (match, label, url) => {
    const safeUrl = safeMarkdownUrl(url);
    if (!safeUrl) return match;
    return remember(
      `<a href="${escapeAttribute(safeUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
    );
  });

  let html = escapeHtml(text);
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
  html = html.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
  html = html.replace(/(^|[^\*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  html = html.replace(/\u0000(\d+)\u0000/g, (_, tokenIndex) => tokens[Number(tokenIndex)] || "");
  return html;
}

function safeMarkdownUrl(value) {
  try {
    const url = new URL(String(value), window.location.origin);
    if (!["http:", "https:", "mailto:"].includes(url.protocol)) return "";
    return url.href;
  } catch {
    return "";
  }
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function bubbleKind(message) {
  if (message.kind === "artifact") return "artifact";
  if (message.kind === "status") return "status";
  if (message.kind === "error") return "error";
  if (message.role === "user") return "user";
  if (message.role === "agent") return "agent";
  return "status";
}

function messageLabel(message) {
  if (message.kind === "artifact") return message.taskId ? `artifact - ${shortId(message.taskId)}` : "artifact";
  if (message.kind === "status") return message.taskId ? `статус задачи - ${shortId(message.taskId)}` : "статус задачи";
  if (message.kind === "error") return "ошибка";
  if (message.role === "user") return "вы";
  if (message.role === "agent") return "agent";
  return `${message.role} / ${message.kind}`;
}

function headerRecords() {
  if (!state.profile) return [];
  if (!Array.isArray(state.profile.headers)) {
    state.profile.headers = [];
  }
  return state.profile.headers;
}

function renderHeaderRows() {
  const headers = headerRecords();
  if (!headers.length) {
    els.headerRows.innerHTML = '<div class="empty-chat">Заголовков пока нет.</div>';
    return;
  }

  els.headerRows.innerHTML = headers
    .map((header, index) => {
      const enabled = header.enabled !== false;
      return `
        <div class="header-row" data-index="${index}">
          <label class="header-enabled-toggle" title="Включен">
            <input class="header-enabled-input" type="checkbox" ${enabled ? "checked" : ""} />
          </label>
          <input class="header-key-input" type="text" value="${escapeHtml(header.name || "")}" placeholder="Authorization" autocomplete="off" />
          <input class="header-value-input" type="text" value="${escapeHtml(header.value || "")}" placeholder="Bearer ..." autocomplete="off" />
          <div class="header-row-actions">
            <button class="header-save" type="button" title="Сохранить заголовок">✓</button>
            <button class="header-delete" type="button" title="Удалить заголовок">×</button>
          </div>
        </div>
      `;
    })
    .join("");

  for (const row of els.headerRows.querySelectorAll(".header-row")) {
    const index = Number(row.dataset.index);
    row.querySelector(".header-enabled-input").addEventListener("change", () => syncHeaderRow(index));
    row.querySelector(".header-key-input").addEventListener("input", () => syncHeaderRow(index));
    row.querySelector(".header-value-input").addEventListener("input", () => syncHeaderRow(index));
    row.querySelector(".header-save").addEventListener("click", () => saveHeaderRow(index));
    row.querySelector(".header-delete").addEventListener("click", () => deleteHeaderRow(index));
  }
}

function normalizeHeader(header) {
  return {
    name: String(header?.name || "").trim(),
    value: String(header?.value || ""),
    enabled: header?.enabled !== false,
    secret: false,
  };
}

function syncHeaderRow(index) {
  const row = els.headerRows.querySelector(`.header-row[data-index="${index}"]`);
  const headers = headerRecords();
  if (!row || !headers[index]) return;
  headers[index] = {
    name: row.querySelector(".header-key-input").value,
    value: row.querySelector(".header-value-input").value,
    enabled: row.querySelector(".header-enabled-input").checked,
    secret: false,
  };
}

function syncAllHeaderRows() {
  for (const row of els.headerRows.querySelectorAll(".header-row")) {
    syncHeaderRow(Number(row.dataset.index));
  }
}

function addHeaderRow() {
  const headers = headerRecords();
  headers.push({ name: "", value: "", enabled: true, secret: false });
  renderHeaderRows();
  const lastInput = els.headerRows.querySelector(`.header-row[data-index="${headers.length - 1}"] .header-key-input`);
  lastInput?.focus();
  setStatus("Добавлена строка заголовка");
}

async function saveHeaderRow(index) {
  try {
    syncAllHeaderRows();
    const headers = headerRecords();
    const current = normalizeHeader(headers[index]);
    if (!current.name) {
      setStatus("Укажите ключ заголовка");
      els.headerRows.querySelector(`.header-row[data-index="${index}"] .header-key-input`)?.focus();
      return;
    }

    const currentName = current.name.toLowerCase();
    state.profile.headers = headers
      .map(normalizeHeader)
      .filter((header, itemIndex) => header.name && (itemIndex === index || header.name.toLowerCase() !== currentName));
    await saveProfile(false);
    setStatus(`Заголовок ${current.name} сохранен`);
  } catch (error) {
    setStatus(error.message);
  }
}

async function deleteHeaderRow(index) {
  try {
    const headers = headerRecords();
    headers.splice(index, 1);
    await saveProfile(false);
    setStatus("Заголовок удален");
  } catch (error) {
    setStatus(error.message);
  }
}

async function selectProfile(profileId) {
  const data = await api(`/api/profiles/${profileId}`);
  state.selectedProfileId = Number(profileId);
  state.profile = data.profile;
  state.conversations = data.conversations;
  state.selectedConversationId = data.selectedConversationId;
  state.conversation = data.conversation;
  state.chatListLimit = data.chatListLimit || state.chatListLimit;
  clearTaskResult();
  renderAll();
  setStatus("Соединение загружено");
}

async function selectConversation(conversationId) {
  const data = await api(`/api/conversations/${conversationId}`);
  state.selectedConversationId = Number(conversationId);
  state.conversation = data.conversation;
  clearTaskResult();
  renderConversations();
  renderConversation();
  setStatus(state.conversation.inputRequired ? "Требуется ввод" : "Чат загружен");
}

async function newProfile() {
  const data = await api("/api/profiles", {
    method: "POST",
    body: JSON.stringify({}),
  });
  applyState({ ...state, ...data });
  setStatus("Соединение создано");
}

async function deleteProfile() {
  if (state.busy || !state.selectedProfileId) return;
  setBusy(true, "Удаляем соединение");
  try {
    const data = await api(`/api/profiles/${state.selectedProfileId}`, {
      method: "DELETE",
    });
    clearTaskResult();
    applyState({ ...state, ...data });
    setStatus(data.status || "Соединение удалено");
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function newChat() {
  const data = await api("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ profileId: state.selectedProfileId }),
  });
  state.conversations = data.conversations;
  state.selectedConversationId = data.selectedConversationId;
  state.conversation = data.conversation;
  clearTaskResult();
  renderConversations();
  renderConversation();
  setStatus("Новый чат создан");
}

async function deleteConversation(conversationId) {
  if (state.busy) return;
  setBusy(true, "Удаляем чат");
  try {
    const activeId = state.selectedConversationId || 0;
    const data = await api(`/api/conversations/${conversationId}?activeConversationId=${activeId}`, {
      method: "DELETE",
    });
    state.conversations = data.conversations;
    state.selectedConversationId = data.selectedConversationId;
    state.conversation = data.conversation;
    clearTaskResult();
    renderConversations();
    renderConversation();
    setStatus(data.status || "Чат удален");
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function updateChatListLimit() {
  if (!state.selectedProfileId) return;
  const limit = Number(els.chatListLimit.value || 20);
  try {
    const data = await api("/api/settings/chat-list-limit", {
      method: "POST",
      body: JSON.stringify({
        profileId: state.selectedProfileId,
        limit,
      }),
    });
    state.chatListLimit = data.chatListLimit;
    state.conversations = data.conversations;
    renderChatListLimit();
    renderConversations();
    setStatus("Лимит чатов сохранен");
  } catch (error) {
    setStatus(error.message);
  }
}

async function sendMessage(stream = false) {
  const text = els.messageInput.value.trim();
  if (!text) return;
  const controller = beginCancelableRequest(stream ? "Ждем stream-ответ" : "Ждем ответ");
  try {
    await saveProfile(false);
    if (stream) {
      await streamRequest(text, controller.signal);
    } else {
      const data = await api("/api/messages/send", {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({
          profileId: state.selectedProfileId,
          conversationId: state.selectedConversationId,
          text,
        }),
      });
      applyConversationUpdate(data);
    }
    els.messageInput.value = "";
  } catch (error) {
    setStatus(isAbortError(error) ? "Вызов остановлен пользователем" : error.message);
  } finally {
    finishCancelableRequest(controller);
  }
}

async function streamRequest(text, signal) {
  const response = await fetch("/api/messages/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      profileId: state.selectedProfileId,
      conversationId: state.selectedConversationId,
      text,
    }),
  });
  if (!response.ok || !response.body) {
    throw new Error(await response.text());
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      const data = JSON.parse(line.slice(6));
      applyConversationUpdate(data);
    }
  }
}

function applyConversationUpdate(data) {
  state.conversations = data.conversations || state.conversations;
  state.conversation = data.conversation || state.conversation;
  state.selectedConversationId = state.conversation?.id || state.selectedConversationId;
  renderConversations();
  renderConversation();
  setStatus(statusWithLatency(data.status || "Готово", state.conversation));
}

async function taskRequest(method) {
  const controller = beginCancelableRequest(method === "get" ? "Получаем задачу" : "Отменяем задачу");
  try {
    await saveProfile(false);
    const data = await api(`/api/tasks/${method}`, {
      method: "POST",
      signal: controller.signal,
      body: JSON.stringify({
        profileId: state.selectedProfileId,
        conversationId: state.selectedConversationId,
        taskId: els.taskId.value.trim(),
      }),
    });
    state.conversations = data.conversations || state.conversations;
    state.conversation = data.conversation || state.conversation;
    renderConversations();
    renderConversation();
    els.taskResult.textContent = JSON.stringify(data.taskResult || {}, null, 2);
    setStatus(statusWithLatency(data.status || "Готово", state.conversation));
  } catch (error) {
    setStatus(isAbortError(error) ? "Вызов остановлен пользователем" : error.message);
  } finally {
    finishCancelableRequest(controller);
  }
}

async function loadAgentCard() {
  const controller = beginCancelableRequest("Загружаем Agent Card");
  try {
    await saveProfile(false);
    const data = await api("/api/agent-card", {
      method: "POST",
      signal: controller.signal,
      body: JSON.stringify({
        profileId: state.selectedProfileId,
        conversationId: state.selectedConversationId,
      }),
    });
    els.agentCard.textContent = JSON.stringify(data.agentCard || {}, null, 2);
    if (data.conversation) {
      state.conversation = data.conversation;
      renderConversation();
    }
    setStatus(statusWithLatency(data.status, data.conversation));
  } catch (error) {
    setStatus(isAbortError(error) ? "Вызов остановлен пользователем" : error.message);
  } finally {
    finishCancelableRequest(controller);
  }
}

async function uploadCert(input, fieldName, targetInput) {
  if (!input.files?.length || !state.selectedProfileId) return;
  syncProfileDraftFromForm();
  const form = new FormData();
  form.append("file", input.files[0]);
  try {
    const data = await api(`/api/profiles/${state.selectedProfileId}/certificates/${fieldName}`, {
      method: "POST",
      body: form,
    });
    targetInput.value = data.path;
    state.profile = { ...state.profile, ...data.profile };
    syncProfileDraftFromForm();
    renderProfileSelect();
    setStatus("Копия сертификата импортирована");
  } catch (error) {
    setStatus(error.message);
  } finally {
    input.value = "";
  }
}

async function pickCertificatePath(fieldName, targetInput) {
  if (window.pywebview?.api?.choose_certificate_path) {
    try {
      const path = await window.pywebview.api.choose_certificate_path(fieldName);
      if (!path) return;
      targetInput.value = path;
      syncProfileDraftFromForm();
      await saveProfile(false);
      setStatus("Путь к сертификату выбран и сохранен");
      return;
    } catch (error) {
      setStatus(error.message);
    }
  }
  setStatus("Desktop-диалог недоступен. Вставьте абсолютный путь или используйте импорт копии.");
}

function wireEvents() {
  $("newProfileBtn").addEventListener("click", newProfile);
  $("saveProfileBtn").addEventListener("click", () => saveProfile(true).catch((error) => setStatus(error.message)));
  $("deleteProfileBtn").addEventListener("click", deleteProfile);
  $("newChatBtn").addEventListener("click", newChat);
  $("sendBtn").addEventListener("click", () => sendMessage(false));
  $("streamBtn").addEventListener("click", () => sendMessage(true));
  $("stopRequestBtn").addEventListener("click", stopCurrentRequest);
  $("agentCardBtn").addEventListener("click", loadAgentCard);
  $("getTaskBtn").addEventListener("click", () => taskRequest("get"));
  $("cancelTaskBtn").addEventListener("click", () => taskRequest("cancel"));
  $("addHeaderBtn").addEventListener("click", addHeaderRow);
  $("formatMetadataBtn").addEventListener("click", () => {
    try {
      els.metadataJson.value = JSON.stringify(JSON.parse(els.metadataJson.value || "{}"), null, 2);
      setStatus("Метаданные отформатированы");
    } catch (error) {
      setStatus(error.message);
    }
  });
  els.profileSelect.addEventListener("change", () => selectProfile(els.profileSelect.value));
  els.chatListLimit.addEventListener("change", updateChatListLimit);
  els.chatListLimit.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      els.chatListLimit.blur();
    }
  });
  els.paletteSelect.addEventListener("change", async () => {
    state.theme = els.paletteSelect.value;
    document.body.dataset.theme = state.theme;
    await api("/api/settings/theme", { method: "POST", body: JSON.stringify({ theme: state.theme }) });
  });
  $("caBundlePickPath").addEventListener("click", () => pickCertificatePath("ca_bundle_path", els.caBundlePath));
  $("clientCertPickPath").addEventListener("click", () => pickCertificatePath("client_cert_path", els.clientCertPath));
  $("clientKeyPickPath").addEventListener("click", () => pickCertificatePath("client_key_path", els.clientKeyPath));
  $("caBundleImportBtn").addEventListener("click", () => els.caBundleFile.click());
  $("clientCertImportBtn").addEventListener("click", () => els.clientCertFile.click());
  $("clientKeyImportBtn").addEventListener("click", () => els.clientKeyFile.click());
  els.caBundleFile.addEventListener("change", () => uploadCert(els.caBundleFile, "ca_bundle_path", els.caBundlePath));
  els.clientCertFile.addEventListener("change", () => uploadCert(els.clientCertFile, "client_cert_path", els.clientCertPath));
  els.clientKeyFile.addEventListener("change", () => uploadCert(els.clientKeyFile, "client_key_path", els.clientKeyPath));
  wireProfileDraftEvents();
  els.messageInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
      return;
    }
    event.preventDefault();
    if (!state.busy) {
      sendMessage(false);
    }
  });
}

function wireProfileDraftEvents() {
  for (const element of [
    els.profileName,
    els.endpoint,
    els.agentCardRoute,
    els.messageSendRoute,
    els.messageStreamRoute,
    els.tasksGetRoute,
    els.tasksCancelRoute,
    els.tenant,
    els.timeoutSeconds,
    els.caBundlePath,
    els.clientCertPath,
    els.clientKeyPath,
    els.metadataJson,
  ]) {
    element.addEventListener("input", syncProfileDraftFromForm);
  }
  els.protocolVersion.addEventListener("change", () => {
    syncProfileDraftFromForm();
    renderProtocolControls();
  });
  els.tlsVerify.addEventListener("change", syncProfileDraftFromForm);
}

async function init() {
  wireEvents();
  try {
    const data = await api("/api/state");
    applyState(data);
    setStatus("Готово");
  } catch (error) {
    setStatus(error.message);
  }
}

init();
