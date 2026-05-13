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
};

const $ = (id) => document.getElementById(id);

const els = {
  status: $("statusText"),
  profileSelect: $("profileSelect"),
  paletteSelect: $("paletteSelect"),
  chatListLimit: $("chatListLimit"),
  chatList: $("chatList"),
  profileName: $("profileName"),
  endpoint: $("endpoint"),
  protocolVersion: $("protocolVersion"),
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
  agentCard: $("agentCard"),
  headerRows: $("headerRows"),
  conversationMeta: $("conversationMeta"),
  chatPane: $("chatPane"),
  messageInput: $("messageInput"),
  diagnostics: $("diagnostics"),
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
  for (const id of ["sendBtn", "streamBtn", "saveProfileBtn", "agentCardBtn", "getTaskBtn", "cancelTaskBtn", "chatListLimit", "addHeaderBtn"]) {
    $(id).disabled = busy;
  }
  for (const button of document.querySelectorAll(".chat-delete, .header-save, .header-delete")) {
    button.disabled = busy;
  }
  if (busy) {
    startBusyTimer(label);
  } else {
    stopBusyTimer();
  }
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
    protocolVersion: els.protocolVersion.value,
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
  els.protocolVersion.value = profile.protocolVersion || "1.0";
  els.timeoutSeconds.value = profile.timeoutSeconds || 60;
  els.tlsVerify.checked = Boolean(profile.tlsVerify);
  els.caBundlePath.value = profile.caBundlePath || "";
  els.clientCertPath.value = profile.clientCertPath || "";
  els.clientKeyPath.value = profile.clientKeyPath || "";
  els.metadataJson.value = profile.metadataJson || "{}";
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
        <pre>${escapeHtml(message.text || "")}</pre>
      </div>
    </div>
  `;
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
  renderAll();
  setStatus("Соединение загружено");
}

async function selectConversation(conversationId) {
  const data = await api(`/api/conversations/${conversationId}`);
  state.selectedConversationId = Number(conversationId);
  state.conversation = data.conversation;
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

async function newChat() {
  const data = await api("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ profileId: state.selectedProfileId }),
  });
  state.conversations = data.conversations;
  state.selectedConversationId = data.selectedConversationId;
  state.conversation = data.conversation;
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
  setBusy(true, stream ? "Ждем stream-ответ" : "Ждем ответ");
  try {
    await saveProfile(false);
    if (stream) {
      await streamRequest(text);
    } else {
      const data = await api("/api/messages/send", {
        method: "POST",
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
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function streamRequest(text) {
  const response = await fetch("/api/messages/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  setBusy(true, method === "get" ? "Получаем задачу" : "Отменяем задачу");
  try {
    await saveProfile(false);
    const data = await api(`/api/tasks/${method}`, {
      method: "POST",
      body: JSON.stringify({
        profileId: state.selectedProfileId,
        conversationId: state.selectedConversationId,
        taskId: els.taskId.value.trim(),
      }),
    });
    applyConversationUpdate(data);
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function loadAgentCard() {
  setBusy(true, "Загружаем Agent Card");
  try {
    await saveProfile(false);
    const data = await api("/api/agent-card", {
      method: "POST",
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
    setStatus(error.message);
  } finally {
    setBusy(false);
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
  $("newChatBtn").addEventListener("click", newChat);
  $("sendBtn").addEventListener("click", () => sendMessage(false));
  $("streamBtn").addEventListener("click", () => sendMessage(true));
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
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      sendMessage(false);
    }
  });
}

function wireProfileDraftEvents() {
  for (const element of [
    els.profileName,
    els.endpoint,
    els.timeoutSeconds,
    els.caBundlePath,
    els.clientCertPath,
    els.clientKeyPath,
    els.metadataJson,
  ]) {
    element.addEventListener("input", syncProfileDraftFromForm);
  }
  els.protocolVersion.addEventListener("change", syncProfileDraftFromForm);
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
