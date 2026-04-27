const state = {
  profiles: [],
  profile: null,
  conversations: [],
  conversation: null,
  selectedProfileId: null,
  selectedConversationId: null,
  selectedHeaderName: null,
  theme: "studio",
  palettes: [],
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
  headerCards: $("headerCards"),
  headerName: $("headerName"),
  headerValue: $("headerValue"),
  headerEnabled: $("headerEnabled"),
  headerSecret: $("headerSecret"),
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
  els.status.textContent = text || "Ready";
}

function setBusy(busy, label = "Waiting for response") {
  state.busy = busy;
  document.body.dataset.busy = busy ? "true" : "false";
  for (const id of ["sendBtn", "streamBtn", "saveProfileBtn", "agentCardBtn", "getTaskBtn", "cancelTaskBtn"]) {
    $(id).disabled = busy;
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
    return status || "Ready";
  }
  return `${status || "Ready"} · ${(latest.latencyMs / 1000).toFixed(1)}s`;
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

function maskValue(value, secret) {
  const text = String(value || "");
  if (!secret) return text;
  if (!text) return "";
  if (text.length <= 8) return "....";
  return `${text.slice(0, 4)} ....... ${text.slice(-4)}`;
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
  renderHeaderCards();
  if (showStatus) setStatus("Connection saved");
}

function applyState(data) {
  Object.assign(state, data);
  document.body.dataset.theme = state.theme || "studio";
  renderAll();
}

function renderAll() {
  renderProfileSelect();
  renderPaletteSelect();
  renderProfileForm();
  renderHeaderCards();
  renderConversations();
  renderConversation();
}

function renderProfileSelect() {
  els.profileSelect.innerHTML = state.profiles
    .map((profile) => `<option value="${profile.id}">${escapeHtml(profile.name)} - ${escapeHtml(profile.endpoint || "no endpoint")}</option>`)
    .join("");
  if (state.selectedProfileId) els.profileSelect.value = String(state.selectedProfileId);
}

function renderPaletteSelect() {
  els.paletteSelect.innerHTML = state.palettes
    .map((palette) => `<option value="${palette.key}">${escapeHtml(palette.name)}</option>`)
    .join("");
  els.paletteSelect.value = state.theme || "studio";
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
    const button = document.createElement("button");
    button.className = `chat-item ${conversation.id === state.selectedConversationId ? "active" : ""}`;
    button.innerHTML = `<strong>${escapeHtml(conversation.title)}</strong><span>${escapeHtml(shortId(conversation.contextId))}</span>`;
    button.addEventListener("click", () => selectConversation(conversation.id));
    els.chatList.appendChild(button);
  }
}

function renderConversation() {
  const conversation = state.conversation;
  if (!conversation) {
    els.conversationMeta.innerHTML = "";
    els.chatPane.innerHTML = '<div class="empty-chat">No chat selected.</div>';
    els.diagnostics.textContent = "[]";
    return;
  }

  els.taskId.value = conversation.taskId || "";
  const chips = [
    `Context: ${conversation.contextId || "not set"}`,
    conversation.taskId ? `Task: ${conversation.taskId}` : "",
    conversation.taskState ? `State: ${conversation.taskState}` : "",
    conversation.inputRequired ? "Input required" : "",
  ].filter(Boolean);
  els.conversationMeta.innerHTML = chips.map((chip) => `<span class="meta-chip">${escapeHtml(chip)}</span>`).join("");

  if (!conversation.messages?.length) {
    els.chatPane.innerHTML = '<div class="empty-chat">No messages yet.</div>';
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
  if (message.kind === "status") return message.taskId ? `task status - ${shortId(message.taskId)}` : "task status";
  if (message.kind === "error") return "error";
  if (message.role === "user") return "you";
  if (message.role === "agent") return "agent";
  return `${message.role} / ${message.kind}`;
}

function renderHeaderCards() {
  const headers = state.profile?.headers || [];
  if (!headers.length) {
    els.headerCards.innerHTML = '<div class="empty-chat">No headers configured.</div>';
    return;
  }
  els.headerCards.innerHTML = headers
    .map((header) => {
      const active = header.name === state.selectedHeaderName ? " active" : "";
      const disabled = header.enabled ? "" : " disabled";
      return `
        <button class="header-card${active}${disabled}" data-header="${escapeHtml(header.name)}">
          <div class="header-top">
            <span class="header-name">${escapeHtml(header.name)}</span>
            <span class="pill ${header.enabled ? "on" : ""}">${header.enabled ? "enabled" : "off"}</span>
            <span class="pill">${header.secret ? "masked" : "visible"}</span>
          </div>
          <code class="header-value">${escapeHtml(maskValue(header.value, header.secret)) || "&nbsp;"}</code>
        </button>
      `;
    })
    .join("");
  for (const card of els.headerCards.querySelectorAll(".header-card")) {
    card.addEventListener("click", () => editHeader(card.dataset.header));
  }
}

function clearHeaderForm() {
  state.selectedHeaderName = null;
  els.headerName.value = "";
  els.headerValue.value = "";
  els.headerEnabled.checked = true;
  els.headerSecret.checked = true;
  renderHeaderCards();
}

function editHeader(name) {
  const header = state.profile?.headers?.find((item) => item.name === name);
  if (!header) return;
  state.selectedHeaderName = header.name;
  els.headerName.value = header.name;
  els.headerValue.value = header.value || "";
  els.headerEnabled.checked = Boolean(header.enabled);
  els.headerSecret.checked = Boolean(header.secret);
  renderHeaderCards();
}

function saveHeader() {
  const name = els.headerName.value.trim();
  if (!name) {
    setStatus("Header name is empty");
    return;
  }
  const next = {
    name,
    value: els.headerValue.value,
    enabled: els.headerEnabled.checked,
    secret: els.headerSecret.checked,
  };
  const headers = (state.profile.headers || []).filter(
    (header) => header.name.toLowerCase() !== name.toLowerCase() && header.name !== state.selectedHeaderName,
  );
  headers.push(next);
  state.profile.headers = headers;
  state.selectedHeaderName = name;
  renderHeaderCards();
  setStatus(`Header ${name} saved locally`);
}

function deleteHeader() {
  if (!state.selectedHeaderName) {
    setStatus("Select a header first");
    return;
  }
  state.profile.headers = (state.profile.headers || []).filter((header) => header.name !== state.selectedHeaderName);
  clearHeaderForm();
  setStatus("Header deleted locally");
}

async function selectProfile(profileId) {
  const data = await api(`/api/profiles/${profileId}`);
  state.selectedProfileId = Number(profileId);
  state.profile = data.profile;
  state.conversations = data.conversations;
  state.selectedConversationId = data.selectedConversationId;
  state.conversation = data.conversation;
  state.selectedHeaderName = null;
  renderAll();
  setStatus("Connection loaded");
}

async function selectConversation(conversationId) {
  const data = await api(`/api/conversations/${conversationId}`);
  state.selectedConversationId = Number(conversationId);
  state.conversation = data.conversation;
  renderConversations();
  renderConversation();
  setStatus(state.conversation.inputRequired ? "Input required" : "Chat loaded");
}

async function newProfile() {
  const data = await api("/api/profiles", {
    method: "POST",
    body: JSON.stringify({}),
  });
  applyState({ ...state, ...data });
  setStatus("Connection created");
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
  setStatus("New chat created");
}

async function sendMessage(stream = false) {
  const text = els.messageInput.value.trim();
  if (!text) return;
  setBusy(true, stream ? "Streaming response" : "Waiting for response");
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
  setStatus(statusWithLatency(data.status || "Ready", state.conversation));
}

async function taskRequest(method) {
  setBusy(true, method === "get" ? "Getting task" : "Cancelling task");
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
  setBusy(true, "Loading Agent Card");
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
    setStatus("Certificate copy imported");
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
      setStatus("Certificate path selected and saved");
      return;
    } catch (error) {
      setStatus(error.message);
    }
  }
  setStatus("Desktop file dialog unavailable. Paste absolute path or use Import Copy.");
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
  $("newHeaderBtn").addEventListener("click", clearHeaderForm);
  $("saveHeaderBtn").addEventListener("click", saveHeader);
  $("deleteHeaderBtn").addEventListener("click", deleteHeader);
  $("formatMetadataBtn").addEventListener("click", () => {
    try {
      els.metadataJson.value = JSON.stringify(JSON.parse(els.metadataJson.value || "{}"), null, 2);
      setStatus("Metadata formatted");
    } catch (error) {
      setStatus(error.message);
    }
  });
  els.profileSelect.addEventListener("change", () => selectProfile(els.profileSelect.value));
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
    setStatus("Ready");
  } catch (error) {
    setStatus(error.message);
  }
}

init();
