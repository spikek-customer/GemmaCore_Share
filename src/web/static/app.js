// Interactive Logic for Knowledge Portal (v3.2 Enterprise Strict Auth & Multi-format)

let currentProvider = "litert";
let allBlocks = [];
let authToken = sessionStorage.getItem("auth_token") || "";
let currentUser = null;
let currentThreadId = null;
let selectedFile = null;

document.addEventListener("DOMContentLoaded", async () => {
  // i18n initialization (restore saved language, apply to DOM)
  if (window.i18n) {
    document.documentElement.lang = i18n.currentLang;
    document.querySelectorAll(".lang-select").forEach((s) => (s.value = i18n.currentLang));
    i18n.updateDOM();
    window.addEventListener("languageChanged", () => {
      document.querySelectorAll(".lang-select").forEach((s) => (s.value = i18n.currentLang));
      if (currentUser) updateUIForRole(currentUser);
    });
  }
  setupDropzone();
  setupChatKeypress();
  setupTabs();

  // Strict Authentication Gate Check
  if (!authToken) {
    showAuthGate();
  } else {
    await verifyAndResumeSession();
  }
});

// Toast Helper
function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3500);
}

// Authenticated Fetch Wrapper with 401 & 403 Guards
async function authFetch(url, options = {}) {
  const headers = options.headers || {};
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  options.headers = headers;

  const res = await fetch(url, options);

  if (res.status === 401) {
    showToast(window.i18n ? i18n.t("toast_idle_timeout") : "🔒 セッション有効期限切れ、または30分無操作のため自動ログアウトしました。再度ログインしてください。", "warning");
    logout();
    throw new Error("Unauthorized");
  }

  if (res.status === 403) {
    const data = await res.json().catch(() => ({}));
    showToast(`⛔ 権限エラー: ${data.message || "この操作を行う権限がありません。"}`, "error");
    throw new Error(data.message || "Forbidden");
  }
  return res;
}

function escapeHtml(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// =============================================================
// 0. Strict Authentication Gate
// =============================================================
function showAuthGate() {
  document.getElementById("auth-gate").style.display = "flex";
  document.getElementById("app-root").style.display = "none";
}

function quickFillGate(u, p) {
  document.getElementById("gate-username").value = u;
  document.getElementById("gate-password").value = p;
  document.getElementById("btn-gate-login").focus();
}

async function handleGateLogin(event) {
  event.preventDefault();
  const username = document.getElementById("gate-username").value.trim();
  const password = document.getElementById("gate-password").value.trim();

  if (!username || !password) {
    showToast("ユーザーIDとパスワードを入力してください。", "error");
    return;
  }

  const btn = document.getElementById("btn-gate-login");
  btn.disabled = true;
  btn.innerText = "認証中... ⏳";

  try {
    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: username, password: password }),
    });
    const data = await res.json();

    if (!res.ok) {
      showToast(data.message || "認証に失敗しました。ユーザーIDまたはパスワードが違います。", "error");
      btn.disabled = false;
      btn.innerHTML = "<span data-i18n=\"btn_login\">" + (window.i18n ? i18n.t("btn_login") : "安全にログイン") + "</span> 🚀";
      return;
    }

    // Authentication Success
    authToken = data.session_id;
    currentUser = data;
    sessionStorage.setItem("auth_token", authToken);

    showToast(window.i18n ? i18n.t("toast_auth_success", { name: data.display_name }) : `認証成功！ ようこそ、${data.display_name}さん。`, "success");
    hideAuthGateAndStartApp(data);

  } catch (err) {
    showToast(`通信エラー: ${err.message}`, "error");
    btn.disabled = false;
    btn.innerHTML = "<span data-i18n=\"btn_login\">" + (window.i18n ? i18n.t("btn_login") : "安全にログイン") + "</span> 🚀";
  }
}

async function verifyAndResumeSession() {
  try {
    const res = await authFetch("/api/v1/auth/current");
    const data = await res.json();
    if (data && data.username) {
      currentUser = data;
      hideAuthGateAndStartApp(data);
    } else {
      logout();
    }
  } catch (err) {
    logout();
  }
}

function hideAuthGateAndStartApp(user) {
  document.getElementById("auth-gate").style.display = "none";
  document.getElementById("app-root").style.display = "block";

  // Update Header UI
  document.getElementById("header-user-name").innerText = `${user.display_name} (${user.department || "社内"})`;
  updateUIForRole(user);

  // Initialize clean chat state for this logged in user
  createNewThread();

  // Load initial app data
  loadThreads();
  loadBlocks();
  loadSettings();
}

async function logout() {
  if (authToken) {
    try {
      await fetch("/api/v1/auth/logout", {
        method: "POST",
        headers: { "Authorization": `Bearer ${authToken}` },
      });
    } catch (_) {}
  }
  authToken = "";
  currentUser = null;
  currentThreadId = null;
  sessionStorage.removeItem("auth_token");

  // Reset inputs
  document.getElementById("gate-username").value = "";
  document.getElementById("gate-password").value = "";
  document.getElementById("btn-gate-login").disabled = false;
  document.getElementById("btn-gate-login").innerHTML = "<span data-i18n=\"btn_login\">" + (window.i18n ? i18n.t("btn_login") : "安全にログイン") + "</span> 🚀";

  // Clear chat container and threads from DOM to prevent cross-user leakage
  const msgContainer = document.getElementById("chat-messages");
  if (msgContainer) {
    msgContainer.innerHTML = "";
  }
  const threadListContainer = document.getElementById("thread-list");
  if (threadListContainer) {
    threadListContainer.innerHTML = "";
  }

  showAuthGate();
  showToast("ログアウトしました。業務画面を完全に保護・ロックしました。", "info");
}

function updateUIForRole(user) {
  const badge = document.getElementById("user-role-badge");
  badge.className = `user-role-badge role-${user.role}`;
  badge.innerText = `${user.display_name.split(" ")[0]} (${user.role.toUpperCase()})`;

  const canWrite = user.permissions.includes("knowledge:write");
  const canUserManage = user.permissions.includes("user:manage");
  const canAdmin = user.permissions.includes("settings:manage") || user.permissions.includes("model:manage");

  // Lock tags
  const lockUpload = document.getElementById("lock-upload");
  const lockCms = document.getElementById("lock-cms");
  const lockUsers = document.getElementById("lock-users");
  const lockAudit = document.getElementById("lock-audit");
  const lockSettings = document.getElementById("lock-settings");

  const tabUpload = document.getElementById("nav-upload");
  const tabCms = document.getElementById("nav-cms");
  const tabUsers = document.getElementById("nav-users");
  const tabAudit = document.getElementById("nav-audit");
  const tabSettings = document.getElementById("nav-settings");

  if (canWrite) {
    tabUpload.classList.remove("tab-locked");
    tabCms.classList.remove("tab-locked");
    lockUpload.style.display = "none";
    lockCms.style.display = "none";
  } else {
    tabUpload.classList.add("tab-locked");
    tabCms.classList.add("tab-locked");
    lockUpload.style.display = "inline";
    lockCms.style.display = "inline";
  }

  // Users Tab: Accessible to Admin and Editor (Delegated User Management)
  if (canUserManage) {
    tabUsers.classList.remove("tab-locked");
    lockUsers.style.display = "none";
  } else {
    tabUsers.classList.add("tab-locked");
    lockUsers.style.display = "inline";
  }

  // Admin Only Tabs: Audit logs and System/Model Settings
  if (canAdmin) {
    tabAudit.classList.remove("tab-locked");
    tabSettings.classList.remove("tab-locked");
    lockAudit.style.display = "none";
    lockSettings.style.display = "none";
  } else {
    tabAudit.classList.add("tab-locked");
    tabSettings.classList.add("tab-locked");
    lockAudit.style.display = "inline";
    lockSettings.style.display = "inline";
  }

  // If user is currently on a locked tab, bounce to Chat
  const currentTab = document.querySelector(".nav-tab.active");
  if (currentTab && currentTab.classList.contains("tab-locked")) {
    document.getElementById("nav-chat").click();
  }
}

// =============================================================
// Tab Switching
// =============================================================
function setupTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      if (tab.classList.contains("tab-locked")) {
        showToast("🔒 この機能を利用するには上位の役職権限が必要です。", "error");
        return;
      }

      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      const targetId = tab.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");

      if (targetId === "tab-cms") {
        loadBlocks();
      } else if (targetId === "tab-settings") {
        loadSettings();
      } else if (targetId === "tab-users") {
        loadUsers();
      } else if (targetId === "tab-audit") {
        loadAuditLogs();
        loadDiagnosticsLogs();
      }
    });
  });
}

// =============================================================
// 1. ChatGPT-like Multi-Thread Chat
// =============================================================
function setupChatKeypress() {
  const input = document.getElementById("chat-input");
  input.addEventListener("keydown", (e) => {
    // Prevent premature send while composing Japanese text via IME
    if (e.isComposing || e.keyCode === 229) {
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });
}


function fillPrompt(text) {
  const input = document.getElementById("chat-input");
  input.value = text;
  input.focus();
}

async function loadThreads() {
  const threadListContainer = document.getElementById("thread-list");
  if (!threadListContainer) return;

  try {
    const res = await authFetch("/api/v1/chat/threads");
    if (!res.ok) return;
    const threads = await res.json();

    if (!threads || threads.length === 0) {
      threadListContainer.innerHTML = '<div class="thread-empty">会話履歴はありません。<br>「新しいチャット」から開始できます。</div>';
      return;
    }

    threadListContainer.innerHTML = "";
    threads.forEach(t => {
      const item = document.createElement("div");
      item.className = `thread-item ${t.thread_id === currentThreadId ? "active" : ""}`;
      item.onclick = (e) => {
        if (e.target.closest(".btn-thread-delete")) return;
        selectThread(t.thread_id);
      };

      const dateStr = t.updated_at ? new Date(t.updated_at * 1000).toISOString().split("T")[0] : "";

      item.innerHTML = `
        <div class="thread-info">
          <span class="thread-title" title="${escapeHtml(t.title)}">${escapeHtml(t.title)}</span>
          <span class="thread-date">${dateStr} (${t.message_count || 0}件)</span>
        </div>
        <button class="btn-thread-delete" onclick="deleteThread('${t.thread_id}', event)" title="削除">🗑️</button>
      `;
      threadListContainer.appendChild(item);
    });
  } catch (err) {
    console.error("Failed to load threads:", err);
  }
}

async function selectThread(threadId) {
  try {
    const res = await authFetch(`/api/v1/chat/threads/${threadId}`);
    if (!res.ok) {
      showToast("会話履歴の取得に失敗しました", "error");
      return;
    }
    const data = await res.json();
    currentThreadId = data.thread_id;

    document.getElementById("active-thread-title").innerText = data.title;

    // Render messages
    const msgContainer = document.getElementById("chat-messages");
    msgContainer.innerHTML = "";

    if (!data.messages || data.messages.length === 0) {
      msgContainer.innerHTML = `
        <div class="chat-bubble assistant-bubble">
          <div class="bubble-header">🤖 社内AIアシスタント</div>
          <div class="bubble-text">この会話は新しく開始されました。ご質問をどうぞ！</div>
        </div>
      `;
    } else {
      data.messages.forEach(m => {
        const bubble = document.createElement("div");
        if (m.role === "user") {
          bubble.className = "chat-bubble user-bubble";
          bubble.innerHTML = `<div class="bubble-header">あなた</div><div>${escapeHtml(m.content)}</div>`;
        } else {
          bubble.className = "chat-bubble assistant-bubble";
          let ansHtml = escapeHtml(m.content).replace(/\n/g, "<br>");
          if (m.citation_links && m.citation_links.length > 0) {
            const linksHtml = m.citation_links.map(l => `<span class="citation-card">📎 ${escapeHtml(l)}</span>`).join(" ");
            ansHtml += `<div style="margin-top:10px;"><strong>参照資料:</strong><br>${linksHtml}</div>`;
          }
          bubble.innerHTML = `<div class="bubble-header">🤖 社内AIアシスタント</div><div>${ansHtml}</div>`;
        }
        msgContainer.appendChild(bubble);
      });
    }

    msgContainer.scrollTop = msgContainer.scrollHeight;
    loadThreads();
    closeMobileSidebarIfOpen();
  } catch (err) {
    console.error("Select thread failed:", err);
  }
}

function createNewThread() {
  currentThreadId = null;
  document.getElementById("active-thread-title").innerText = "新しいチャット";
  const msgContainer = document.getElementById("chat-messages");
  msgContainer.innerHTML = `
    <div class="chat-bubble assistant-bubble">
      <div class="bubble-header">🤖 社内AIアシスタント</div>
      <div class="bubble-text">
        こんにちは！社内規程、就業規則、経費精算、ガイドラインなどについて、何でもお気軽にご質問ください。<br>
        登録された全社内ドキュメント（Office、PDF、マニュアル等）に基づいて正確にお答えします。（※厳選出典リンク付き）
      </div>
    </div>
  `;
  loadThreads();
  closeMobileSidebarIfOpen();
}

function toggleChatSidebar() {
  const sidebar = document.querySelector(".chat-sidebar");
  const backdrop = document.getElementById("chat-sidebar-backdrop");
  if (sidebar) {
    const isOpen = sidebar.classList.toggle("mobile-open");
    if (backdrop) {
      backdrop.classList.toggle("active", isOpen);
    }
  }
}

function closeMobileSidebarIfOpen() {
  const sidebar = document.querySelector(".chat-sidebar");
  const backdrop = document.getElementById("chat-sidebar-backdrop");
  if (sidebar && sidebar.classList.contains("mobile-open")) {
    sidebar.classList.remove("mobile-open");
  }
  if (backdrop && backdrop.classList.contains("active")) {
    backdrop.classList.remove("active");
  }
}

async function deleteThread(threadId, event) {
  if (event) event.stopPropagation();
  if (!confirm("このチャット履歴を削除しますか？")) return;

  try {
    const res = await authFetch(`/api/v1/chat/threads/${threadId}`, { method: "DELETE" });
    if (res.ok) {
      showToast("会話履歴を削除しました", "success");
      if (currentThreadId === threadId) {
        createNewThread();
      } else {
        loadThreads();
      }
    }
  } catch (err) {
    showToast("会話履歴の削除に失敗しました", "error");
  }
}

function deleteCurrentThread() {
  if (!currentThreadId) {
    showToast("現在開いている会話はありません", "info");
    return;
  }
  deleteThread(currentThreadId);
}

async function clearAllChatHistory() {
  if (!confirm("すべての会話履歴を完全に消去しますか？\n（※この操作は取り消せません）")) return;

  try {
    const res = await authFetch("/api/v1/chat/threads", { method: "DELETE" });
    if (res.ok) {
      const data = await res.json();
      showToast(`会話履歴をすべて消去しました（${data.deleted_count || 0}件削除）`, "success");
      createNewThread();
      loadThreads();
    }
  } catch (err) {
    showToast("会話履歴の全消去に失敗しました: " + err.message, "error");
  }
}

async function sendChat() {
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("btn-send");
  const text = input.value.trim();
  if (!text) return;

  // Immediately clear input field and reset textarea sizing
  input.value = "";
  input.style.height = "auto";
  if (sendBtn) {
    sendBtn.disabled = true;
  }

  // Defer an extra clear cycle to defeat browser/IME post-composition lingering
  setTimeout(() => {
    input.value = "";
  }, 10);

  const msgContainer = document.getElementById("chat-messages");

  // User bubble
  const userBubble = document.createElement("div");
  userBubble.className = "chat-bubble user-bubble";
  userBubble.innerHTML = `<div class="bubble-header">あなた (${currentUser ? currentUser.display_name.split(" ")[0] : "社員"})</div><div>${escapeHtml(text)}</div>`;
  msgContainer.appendChild(userBubble);
  msgContainer.scrollTop = msgContainer.scrollHeight;

  // Assistant bubble
  const assistantBubble = document.createElement("div");
  assistantBubble.className = "chat-bubble assistant-bubble";
  assistantBubble.innerHTML = `<div class="bubble-header">🤖 社内AIアシスタント</div><div class="loading-dots">ナレッジ照合＆回答生成中... ⏳</div>`;
  msgContainer.appendChild(assistantBubble);
  msgContainer.scrollTop = msgContainer.scrollHeight;

  try {
    const payload = { question: text };
    if (currentThreadId) {
      payload.thread_id = currentThreadId;
    }

    const res = await authFetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.thread_id) {
      currentThreadId = data.thread_id;
    }

    let answerHtml = escapeHtml(data.answer).replace(/\n/g, "<br>");
    
    // Query understanding tag
    if (data.query_understanding && data.query_understanding.formal_terms && data.query_understanding.formal_terms.length > 0 && data.citation_links && data.citation_links.length > 0) {
      const topTerms = data.query_understanding.formal_terms.slice(0, 3).join(", ");
      const tagHtml = `<div class="query-understanding-tag">💡 <strong>意図理解:</strong> ${escapeHtml(data.query_understanding.intent || "社内文書検索")} (照合語: ${escapeHtml(topTerms)})</div><br>`;
      answerHtml = tagHtml + answerHtml;
    }

    // Citation links
    if (data.citation_links && data.citation_links.length > 0) {
      const linksHtml = data.citation_links.map(l => `<span class="citation-card">📎 ${escapeHtml(l)}</span>`).join(" ");
      answerHtml += `<div style="margin-top:12px;"><strong>参照資料:</strong><br>${linksHtml}</div>`;
    }

    assistantBubble.querySelector(".bubble-header").innerText = `🤖 社内AIアシスタント (${currentProvider === "litert" ? "ローカルLiteRT" : "クラウドGemini"})`;
    assistantBubble.querySelector(".loading-dots, div:nth-child(2)").innerHTML = answerHtml;

    loadThreads();
  } catch (err) {
    assistantBubble.querySelector(".loading-dots, div:nth-child(2)").innerHTML = `<span style="color:var(--danger)">エラー: ${escapeHtml(err.message)}</span>`;
  } finally {
    if (sendBtn) {
      sendBtn.disabled = false;
    }
    input.value = "";
    input.focus();
  }
  msgContainer.scrollTop = msgContainer.scrollHeight;
}


// =============================================================
// 2. Universal File Upload & Transparency Report
// =============================================================
function setupDropzone() {
  const dropzone = document.getElementById("dropzone");
  if (!dropzone) return;

  ["dragenter", "dragover"].forEach(evt => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach(evt => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      setFile(files[0]);
    }
  });
}

function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) {
    setFile(file);
  }
}

function setFile(file) {
  selectedFile = file;
  const sizeKB = (file.size / 1024).toFixed(1);
  document.getElementById("selected-file-label").innerText = `📄 選択中: ${file.name} (${sizeKB} KB)`;
  document.getElementById("btn-upload-file").disabled = false;
  showToast(`ファイル「${file.name}」を選択しました。`, "info");
}

function clearSelectedFile() {
  selectedFile = null;
  document.getElementById("file-input").value = "";
  document.getElementById("selected-file-label").innerText = "未選択";
  document.getElementById("btn-upload-file").disabled = true;
  document.getElementById("upload-report-area").style.display = "none";
}

async function uploadSelectedFile() {
  if (!selectedFile) return;

  const btn = document.getElementById("btn-upload-file");
  btn.disabled = true;
  btn.innerText = "ファイルを解析＆インデックス中... ⏳";

  const reader = new FileReader();
  reader.onload = async (e) => {
    try {
      // Extract Base64 part from Data URL
      const dataUrl = e.target.result;
      const base64Data = dataUrl.split(",")[1];

      const res = await authFetch("/api/v1/upload/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: selectedFile.name,
          data_base64: base64Data,
        }),
      });

      const report = await res.json();
      showToast(`🎉 「${selectedFile.name}」の取込完了！ ${report.indexed_blocks}個の知識ブロックに分割・索引化しました。`, "success");

      renderUploadReport(report);
      loadBlocks();

    } catch (err) {
      showToast(`取込エラー: ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "<span>このファイルを解析して知識ベースへ登録</span> 🚀";
    }
  };

  reader.readAsDataURL(selectedFile);
}

function renderUploadReport(report) {
  const area = document.getElementById("upload-report-area");
  area.style.display = "block";

  const summary = document.getElementById("report-summary-box");
  summary.innerHTML = `
    <div style="font-weight:700;font-size:14.5px;color:var(--text-main);margin-bottom:8px;">
      ✅ ファイル『${escapeHtml(report.filename)}』の解析に成功しました
    </div>
    <div class="report-grid">
      <div class="report-metric-card">
        <div class="report-metric-value">${escapeHtml(report.file_type)}</div>
        <div class="report-metric-label">ファイル形式</div>
      </div>
      <div class="report-metric-card">
        <div class="report-metric-value">${report.total_characters ? report.total_characters.toLocaleString() : 0}</div>
        <div class="report-metric-label">抽出文字数</div>
      </div>
      <div class="report-metric-card">
        <div class="report-metric-value">${report.section_count || 1}</div>
        <div class="report-metric-label">抽出セクション/スライド/シート数</div>
      </div>
      <div class="report-metric-card">
        <div class="report-metric-value">${report.indexed_blocks}</div>
        <div class="report-metric-label">生成知識ブロック数</div>
      </div>
    </div>
  `;

  const blocksContainer = document.getElementById("report-blocks-list");
  blocksContainer.innerHTML = "";

  if (report.blocks && report.blocks.length > 0) {
    report.blocks.forEach(b => {
      const card = document.createElement("div");
      card.className = "block-card";
      card.innerHTML = `
        <div class="block-header">
          <div>
            <span class="block-title-tag">${escapeHtml(b.document_title)}</span>
            <span class="block-locator">${escapeHtml(b.locator || "")}</span>
          </div>
          <span style="font-size:11px;color:var(--text-muted);">${escapeHtml(b.block_id)}</span>
        </div>
        <div style="font-size:13px;line-height:1.5;color:var(--text-main);background:#fbfbfb;padding:8px 10px;border-radius:4px;">
          ${escapeHtml(b.text)}
        </div>
      `;
      blocksContainer.appendChild(card);
    });
  }
}

// =============================================================
// 3. Knowledge CMS (Editor / Admin)
// =============================================================
async function loadBlocks() {
  const container = document.getElementById("blocks-container");
  if (!container) return;

  try {
    const res = await authFetch("/api/v1/blocks");
    if (!res.ok) return;
    allBlocks = await res.json();
    renderBlocks(allBlocks);
  } catch (err) {
    console.error("Failed to load blocks:", err);
  }
}

function renderBlocks(blocks) {
  const container = document.getElementById("blocks-container");
  if (!blocks || blocks.length === 0) {
    container.innerHTML = '<p class="placeholder-text">登録されたナレッジ文面はありません。</p>';
    return;
  }

  container.innerHTML = "";
  blocks.forEach(b => {
    const isDrive = (b.metadata && b.metadata.source === "google_drive") || (b.source === "google_drive");
    const sourceBadge = isDrive
      ? '<span class="user-role-badge" style="background:#e8f0fe; color:#1a73e8; border:1px solid #cce0ff; margin-left:6px; font-size:10px;">☁️ Drive同期 (原本: Drive)</span>'
      : '<span class="user-role-badge" style="background:#f3f4f6; color:#4b5563; border:1px solid #e5e7eb; margin-left:6px; font-size:10px;">📁 手動登録 (原本: CMS)</span>';

    const syncNote = isDrive
      ? '<div style="font-size:11px; color:#6b7280; margin-top:4px; line-height:1.4;">💡 <strong>同期仕様:</strong> このブロックはGoogle Drive上の資料と自動同期されています。ここでの修正は即時検索に反映されますが、Drive側でファイルが更新されるとDrive原本の内容で自動再同期（上書き）されます。恒久的な修正はDrive原本の更新を推奨します。</div>'
      : '';

    const card = document.createElement("div");
    card.className = "block-card";
    card.innerHTML = `
      <div class="block-header">
        <div>
          <span class="block-title-tag">${escapeHtml(b.document_title)}</span>
          <span class="block-locator">${escapeHtml(b.locator || "一般条文")}</span>
          ${sourceBadge}
        </div>
        <span style="font-size:11.5px;color:var(--text-muted); font-family:monospace;">${escapeHtml(b.block_id)}</span>
      </div>
      <textarea class="block-textarea" id="block-text-${b.block_id}" rows="3">${escapeHtml(b.text)}</textarea>
      ${syncNote}
      <div class="block-actions" style="margin-top: 8px;">
        <button class="btn btn-secondary" onclick="deleteBlock('${b.block_id}')">削除 🗑️</button>
        <button class="btn btn-primary" onclick="saveBlock('${b.block_id}')">保存して即時再索引 💾</button>
      </div>
    `;
    container.appendChild(card);
  });
}

function filterBlocks() {
  const query = document.getElementById("cms-search-input").value.toLowerCase();
  if (!query) {
    renderBlocks(allBlocks);
    return;
  }
  const filtered = allBlocks.filter(b => 
    b.text.toLowerCase().includes(query) || 
    b.document_title.toLowerCase().includes(query) || 
    (b.locator && b.locator.toLowerCase().includes(query))
  );
  renderBlocks(filtered);
}

async function saveBlock(blockId) {
  const textarea = document.getElementById(`block-text-${blockId}`);
  const newText = textarea.value.trim();
  if (!newText) {
    showToast("文面が空です。削除する場合は「削除」ボタンを押してください。", "error");
    return;
  }

  try {
    const res = await authFetch(`/api/v1/blocks/${blockId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: newText }),
    });
    if (res.ok) {
      showToast("文面を更新し、即座に再ベクトル化しました！", "success");
      loadBlocks();
    }
  } catch (err) {
    showToast(`更新失敗: ${err.message}`, "error");
  }
}

async function deleteBlock(blockId) {
  if (!confirm("この知識ブロックを削除しますか？")) return;

  try {
    const res = await authFetch(`/api/v1/blocks/${blockId}`, { method: "DELETE" });
    if (res.ok) {
      showToast("知識ブロックを削除しました。", "success");
      loadBlocks();
    }
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, "error");
  }
}

function openNewBlockModal() {
  document.getElementById("modal-block").style.display = "flex";
}

function closeNewBlockModal() {
  document.getElementById("modal-block").style.display = "none";
}

async function saveNewBlock() {
  const title = document.getElementById("modal-doc-title").value.trim();
  const locator = document.getElementById("modal-locator").value.trim();
  const text = document.getElementById("modal-text").value.trim();

  if (!title || !text) {
    showToast("ドキュメント名と文面本文を入力してください。", "error");
    return;
  }

  try {
    const res = await authFetch("/api/v1/blocks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_title: title,
        locator: locator,
        text: text,
      }),
    });
    if (res.ok) {
      showToast("新しい知識ブロックを追加・索引化しました！", "success");
      closeNewBlockModal();
      document.getElementById("modal-doc-title").value = "";
      document.getElementById("modal-locator").value = "";
      document.getElementById("modal-text").value = "";
      loadBlocks();
    }
  } catch (err) {
    showToast(`追加失敗: ${err.message}`, "error");
  }
}

// =============================================================
// 4. Simulator (All Users)
// =============================================================
async function runSearchSimulator() {
  const query = document.getElementById("sim-query-input").value.trim();
  if (!query) {
    showToast("検索キーワードを入力してください", "error");
    return;
  }

  const container = document.getElementById("sim-results");
  container.innerHTML = '<p class="placeholder-text">検索中... ⚡</p>';

  try {
    const res = await authFetch("/api/v1/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query, limit: 5 }),
    });
    const results = await res.json();
    renderSimResults(results);
  } catch (err) {
    container.innerHTML = `<p style="color:var(--danger);padding:20px;">検索エラー: ${escapeHtml(err.message)}</p>`;
  }
}

function renderSimResults(results) {
  const container = document.getElementById("sim-results");
  if (!results || results.length === 0) {
    container.innerHTML = '<p class="placeholder-text">該当する文面は見つかりませんでした。</p>';
    return;
  }

  container.innerHTML = "";
  results.forEach((r, idx) => {
    const card = document.createElement("div");
    card.className = "sim-hit-card";
    const scorePct = Math.round(r.score * 100);

    card.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div>
          <span style="font-weight:700;font-size:13px;">#${idx + 1} ${escapeHtml(r.document_title)}</span>
          <span style="font-size:11.5px;color:var(--text-muted);margin-left:8px;">${escapeHtml(r.locator || "")}</span>
        </div>
        <span class="sim-score-badge">類似度: ${scorePct}%</span>
      </div>
      <div style="font-size:13px;line-height:1.5;color:var(--text-main);">${escapeHtml(r.text)}</div>
    `;
    container.appendChild(card);
  });
}

// =============================================================
// 5. Users & RBAC Lifecycle Management (Admin Only)
// =============================================================
let currentLoadedUsers = [];
let userSearchDebounceTimer = null;
let pendingSuspendAction = { username: "", is_active: false };
let pendingDeleteAction = { username: "", display_name: "" };

async function loadUsers() {
  const tbody = document.getElementById("users-table-body");
  if (!tbody) return;

  const query = document.getElementById("user-search-query") ? document.getElementById("user-search-query").value.trim() : "";
  const role = document.getElementById("user-filter-role") ? document.getElementById("user-filter-role").value : "";
  const status = document.getElementById("user-filter-status") ? document.getElementById("user-filter-status").value : "";

  let url = "/api/v1/users?";
  if (query) url += `q=${encodeURIComponent(query)}&`;
  if (role) url += `role=${encodeURIComponent(role)}&`;
  if (status) url += `status=${encodeURIComponent(status)}&`;

  try {
    // 1. Fetch users list
    const res = await authFetch(url);
    if (!res.ok) {
      if (res.status === 403) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:20px; color:var(--danger);">🔒 ユーザー管理権限がありません（管理者のみ閲覧可能）。</td></tr>`;
      }
      return;
    }
    const users = await res.json();
    currentLoadedUsers = users;

    // 2. Fetch user statistics
    loadUserStats();

    // 3. Render table
    tbody.innerHTML = "";
    if (users.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:var(--text-muted);">該当する社員アカウントが見つかりません。</td></tr>`;
      return;
    }

    const currentLoggedInUsername = currentUser ? currentUser.username : "";
    const activeAdminCount = users.filter(u => u.role === "admin" && u.is_active).length;

    users.forEach(u => {
      const tr = document.createElement("tr");

      // Role badge
      let roleBadge = `<span class="user-role-badge role-${u.role}">${escapeHtml(u.role.toUpperCase())}</span>`;
      if (u.role === "admin") roleBadge = `<span class="user-role-badge role-admin">👑 管理者</span>`;
      else if (u.role === "editor") roleBadge = `<span class="user-role-badge role-editor">✏️ 編集長</span>`;
      else if (u.role === "viewer") roleBadge = `<span class="user-role-badge role-viewer">👤 閲覧者</span>`;

      // Status badge (Handles active, suspended, and temporary lockout)
      let statusBadge = "";
      if (u.is_locked) {
        const remainingSec = Math.max(0, Math.round((u.locked_until || 0) - (Date.now() / 1000)));
        const remMin = Math.floor(remainingSec / 60);
        const remSec = remainingSec % 60;
        statusBadge = `<span class="status-badge" style="background:#fef2f2; color:#b91c1c; border:1px solid #fecaca; font-weight:700;" title="5回連続認証失敗による5分間一時ロック中">🔒 ロック中 (${remMin}分${remSec}秒)</span>`;
      } else if (u.is_active) {
        statusBadge = `<span class="status-badge status-active">🟢 有効</span>`;
      } else {
        statusBadge = `<span class="status-badge status-suspended">🔴 停止中</span>`;
      }

      // Delegated RBAC Guards: Check if operator is Admin
      const isOperatorAdmin = currentUser && currentUser.role === "admin";
      const isTargetAdmin = u.role === "admin";

      let actionButtonsHtml = "";
      if (!isOperatorAdmin && isTargetAdmin) {
        // Upper-tier immunity: Editor cannot modify, reset, suspend, or delete Admin
        actionButtonsHtml = `<span class="user-role-badge role-admin" style="background:#f1f5f9; color:#64748b; border:1px solid #cbd5e1; font-size:11px; padding:3px 8px;" title="最高管理者アカウントは編集長権限では操作できません">🔒 管理者保護</span>`;
      } else {
        // Unlock button for locked accounts
        let unlockBtn = "";
        if (u.is_locked) {
          unlockBtn = `<button class="btn btn-xs btn-primary btn-action-unlock" data-username="${escapeHtml(u.username)}" data-display-name="${escapeHtml(u.display_name)}" title="ロックを即時解除してログイン可能にする">🔓 ロック解除</button>`;
        }

        // Guards for Delete button
        const isSelf = (u.username === currentLoggedInUsername);
        const isLastAdmin = (u.role === "admin" && activeAdminCount <= 1);
        let deleteDisabledReason = "";
        if (isSelf) deleteDisabledReason = "現在ログイン中の自身のアカウントは削除できません";
        else if (isLastAdmin) deleteDisabledReason = "唯一の管理者のため削除できません";

        const deleteBtn = deleteDisabledReason
          ? `<button class="btn btn-xs btn-outline" disabled title="${deleteDisabledReason}">🗑️ 削除不可</button>`
          : `<button class="btn btn-xs btn-danger-outline btn-action-delete" data-username="${escapeHtml(u.username)}" data-display-name="${escapeHtml(u.display_name)}">🗑️ 削除</button>`;

        // Suspend/Reactivate Button
        let toggleStatusBtn = "";
        if (isSelf) {
          toggleStatusBtn = `<button class="btn btn-xs btn-outline" disabled title="自身のアカウントは停止できません">🛑 停止不可</button>`;
        } else if (u.is_active) {
          toggleStatusBtn = `<button class="btn btn-xs btn-warning-outline btn-action-suspend" data-action="suspend" data-username="${escapeHtml(u.username)}" data-display-name="${escapeHtml(u.display_name)}" title="即時アクセス遮断">🛑 停止</button>`;
        } else {
          toggleStatusBtn = `<button class="btn btn-xs btn-success-outline btn-action-suspend" data-action="reactivate" data-username="${escapeHtml(u.username)}" data-display-name="${escapeHtml(u.display_name)}" title="利用再開">🟢 再開</button>`;
        }

        actionButtonsHtml = `
          <div class="action-btn-group">
            ${unlockBtn}
            <button class="btn btn-xs btn-secondary btn-action-edit" data-username="${escapeHtml(u.username)}">✏️ 編集</button>
            <button class="btn btn-xs btn-secondary btn-action-pw" data-username="${escapeHtml(u.username)}" data-display-name="${escapeHtml(u.display_name)}">🔑 PW</button>
            ${toggleStatusBtn}
            ${deleteBtn}
          </div>
        `;
      }

      tr.innerHTML = `
        <td><strong>${escapeHtml(u.username)}</strong></td>
        <td>${escapeHtml(u.display_name)}</td>
        <td>${escapeHtml(u.department || "-")}</td>
        <td>${roleBadge}</td>
        <td>${statusBadge}</td>
        <td style="color:#64748b; font-size:12px;">${escapeHtml(u.notes || "-")}</td>
        <td>${actionButtonsHtml}</td>
      `;
      tbody.appendChild(tr);
    });

    // Delegated safe event handler to prevent attribute injection
    if (!tbody._securityDelegated) {
      tbody._securityDelegated = true;
      tbody.addEventListener("click", (e) => {
        const btn = e.target.closest("button");
        if (!btn) return;
        const uName = btn.dataset.username;
        const dName = btn.dataset.displayName;
        if (btn.classList.contains("btn-action-unlock")) {
          unlockUserAccount(uName, dName);
        } else if (btn.classList.contains("btn-action-delete")) {
          openDeleteUserModal(uName, dName);
        } else if (btn.classList.contains("btn-action-suspend")) {
          openSuspendModal(uName, dName, btn.dataset.action === "suspend");
        } else if (btn.classList.contains("btn-action-edit")) {
          openEditUserModal(uName);
        } else if (btn.classList.contains("btn-action-pw")) {
          openResetPwModal(uName, dName);
        }
      });
    }
  } catch (err) {
    console.error("Load users failed:", err);
    showToast(`ユーザー一覧取得エラー: ${err.message}`, "error");
  }
}

async function unlockUserAccount(username, displayName) {
  if (!confirm(`社員「${displayName} (${username})」の一時ロックを即時解除しますか？\n解除後は直ちにパスワード認証でログインできるようになります。`)) {
    return;
  }
  try {
    const res = await authFetch(`/api/v1/users/${encodeURIComponent(username)}/unlock`, {
      method: "POST"
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || "ロック解除に失敗しました");
    }
    const data = await res.json();
    showToast(data.message || `ユーザー ${username} のロックを解除しました。`, "success");
    loadUsers();
  } catch (err) {
    showToast(`ロック解除エラー: ${err.message}`, "error");
  }
}

async function loadUserStats() {
  try {
    const res = await authFetch("/api/v1/users/stats");
    if (!res.ok) return;
    const stats = await res.json();
    if (document.getElementById("stat-total-users")) {
      document.getElementById("stat-total-users").innerText = stats.total || 0;
      document.getElementById("stat-active-users").innerText = stats.active || 0;
      document.getElementById("stat-suspended-users").innerText = stats.suspended || 0;
      document.getElementById("stat-admin-users").innerText = stats.admins || 0;
    }
  } catch (err) {
    console.warn("Failed to load user stats:", err);
  }
}

function handleUserSearchInput() {
  if (userSearchDebounceTimer) clearTimeout(userSearchDebounceTimer);
  userSearchDebounceTimer = setTimeout(() => {
    loadUsers();
  }, 250);
}

function resetUserFilters() {
  if (document.getElementById("user-search-query")) document.getElementById("user-search-query").value = "";
  if (document.getElementById("user-filter-role")) document.getElementById("user-filter-role").value = "";
  if (document.getElementById("user-filter-status")) document.getElementById("user-filter-status").value = "";
  loadUsers();
}

function generateRandomPassword(targetElementId) {
  const chars = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*";
  let pwd = "";
  for (let i = 0; i < 10; i++) {
    pwd += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  const el = document.getElementById(targetElementId);
  if (el) el.value = pwd;
}

// -------------------------------------------------------------
// Modal 1: New User Registration (Join)
// -------------------------------------------------------------
function openNewUserModal() {
  document.getElementById("modal-user").style.display = "flex";
  generateRandomPassword("modal-user-pw");

  const isOperatorAdmin = currentUser && currentUser.role === "admin";

  // Pre-fill department from current operator (especially for Editor)
  const deptInput = document.getElementById("modal-user-dept");
  if (deptInput && currentUser && currentUser.department) {
    deptInput.value = currentUser.department;
  }

  // Restrict 'admin' role option if operator is not Admin (Privilege escalation prevention)
  const roleSelect = document.getElementById("modal-user-role");
  if (roleSelect) {
    for (let opt of roleSelect.options) {
      if (opt.value === "admin") {
        opt.style.display = isOperatorAdmin ? "" : "none";
        opt.disabled = !isOperatorAdmin;
      }
    }
    if (!isOperatorAdmin && roleSelect.value === "admin") {
      roleSelect.value = "viewer";
    }
  }
}

function closeNewUserModal() {
  document.getElementById("modal-user").style.display = "none";
}

async function saveNewUser() {
  const username = document.getElementById("modal-user-id").value.trim();
  const displayName = document.getElementById("modal-user-name").value.trim();
  const password = document.getElementById("modal-user-pw").value.trim();
  const department = document.getElementById("modal-user-dept").value.trim();
  const role = document.getElementById("modal-user-role").value;
  const notes = document.getElementById("modal-user-notes").value.trim();

  if (!username) {
    showToast("ユーザーIDは必須です。", "error");
    return;
  }
  if (!/^[A-Za-z0-9_.-]+$/.test(username)) {
    showToast("ユーザーIDは半角英数字、記号(_ - .)のみ使用できます。", "error");
    return;
  }
  if (!displayName) {
    showToast("社員名（表示名）は必須です。", "error");
    return;
  }
  if (!password || password.length < 6) {
    showToast("パスワードは6文字以上で設定してください。", "error");
    return;
  }

  try {
    const res = await authFetch("/api/v1/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: username,
        display_name: displayName,
        password: password,
        department: department,
        role: role,
        notes: notes,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || data.error || "ユーザー作成に失敗しました。", "error");
      return;
    }

    showToast(`社員「${displayName}」のアカウントを発行しました！🌸`, "success");
    closeNewUserModal();

    // Reset fields
    document.getElementById("modal-user-id").value = "";
    document.getElementById("modal-user-name").value = "";
    document.getElementById("modal-user-dept").value = "";
    document.getElementById("modal-user-notes").value = "";

    // Show Welcome Distribution Guide
    showWelcomeModal(data, password);
    loadUsers();
  } catch (err) {
    showToast(`ユーザー作成失敗: ${err.message}`, "error");
  }
}

// -------------------------------------------------------------
// Modal 2: Welcome Distribution Guide
// -------------------------------------------------------------
function showWelcomeModal(user, plainPassword) {
  const welcomeText = `【社内AIナレッジポータル 初期ログインのご案内】

${user.display_name} さん

社内AIナレッジポータルへのアカウントが発行されました。
以下の接続情報を用いて初回ログインを行ってください。

■ ログインURL: ${window.location.origin}/
■ ユーザーID: ${user.username}
■ 初期パスワード: ${plainPassword}
■ 付与役職: ${user.role} (${user.department || "社内"})

※ログイン後は「社内チャット」および「資料検索」が即座にご利用いただけます。
何かご不明点がある場合はシステム管理者までお問い合わせください。`;

  document.getElementById("modal-welcome-text").value = welcomeText;
  document.getElementById("modal-user-welcome").style.display = "flex";
}

function closeWelcomeModal() {
  document.getElementById("modal-user-welcome").style.display = "none";
}

function copyWelcomeText() {
  const text = document.getElementById("modal-welcome-text").value;
  navigator.clipboard.writeText(text).then(() => {
    showToast("📋 案内文をクリップボードにコピーしました！", "success");
  }).catch(() => {
    showToast("コピーに失敗しました。テキストを手動選択してください。", "error");
  });
}

// -------------------------------------------------------------
// Modal 3: Edit User Details & Role (Transfer / Promotion)
// -------------------------------------------------------------
function openEditUserModal(username) {
  const user = currentLoadedUsers.find(u => u.username === username);
  if (!user) return;

  const isOperatorAdmin = currentUser && currentUser.role === "admin";
  // Upper-tier immunity guard: Editor cannot edit Admin
  if (!isOperatorAdmin && user.role === "admin") {
    showToast("⚠️ 管理者アカウントは編集長権限では編集できません（管理者保護）。", "error");
    return;
  }

  document.getElementById("edit-user-id").value = user.username;
  document.getElementById("edit-user-id-display").value = user.username;
  document.getElementById("edit-user-name").value = user.display_name;
  document.getElementById("edit-user-dept").value = user.department || "";
  document.getElementById("edit-user-notes").value = user.notes || "";

  // Restrict 'admin' role option if operator is not Admin
  const roleSelect = document.getElementById("edit-user-role");
  if (roleSelect) {
    for (let opt of roleSelect.options) {
      if (opt.value === "admin") {
        opt.style.display = isOperatorAdmin ? "" : "none";
        opt.disabled = !isOperatorAdmin;
      }
    }
  }
  roleSelect.value = user.role;
  checkRoleChangeWarning();

  document.getElementById("modal-user-edit").style.display = "flex";
}

function closeEditUserModal() {
  document.getElementById("modal-user-edit").style.display = "none";
}

function checkRoleChangeWarning() {
  const role = document.getElementById("edit-user-role").value;
  const warning = document.getElementById("edit-role-warning");
  if (warning) {
    warning.style.display = (role === "admin") ? "block" : "none";
  }
}

async function submitEditUser() {
  const username = document.getElementById("edit-user-id").value;
  const displayName = document.getElementById("edit-user-name").value.trim();
  const department = document.getElementById("edit-user-dept").value.trim();
  const role = document.getElementById("edit-user-role").value;
  const notes = document.getElementById("edit-user-notes").value.trim();

  if (!displayName) {
    showToast("社員名は必須です。", "error");
    return;
  }

  try {
    const res = await authFetch(`/api/v1/users/${username}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_name: displayName,
        department: department,
        role: role,
        notes: notes,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || data.error || "変更保存に失敗しました。", "error");
      return;
    }

    showToast(`社員「${username}」の情報を更新しました。💾`, "success");
    closeEditUserModal();
    loadUsers();
  } catch (err) {
    showToast(`更新失敗: ${err.message}`, "error");
  }
}

// -------------------------------------------------------------
// Modal 4: Password Reset
// -------------------------------------------------------------
function openResetPwModal(username, displayName) {
  const user = currentLoadedUsers.find(u => u.username === username);
  if (currentUser && currentUser.role !== "admin" && user && user.role === "admin") {
    showToast("⚠️ 管理者アカウントのパスワードは編集長権限ではリセットできません（管理者保護）。", "error");
    return;
  }

  document.getElementById("reset-pw-user-name").innerText = displayName;
  document.getElementById("reset-pw-user-id").innerText = username;
  generateRandomPassword("reset-pw-input");
  document.getElementById("modal-user-reset-pw").style.display = "flex";
}

function closeResetPwModal() {
  document.getElementById("modal-user-reset-pw").style.display = "none";
}

async function submitResetPassword() {
  const username = document.getElementById("reset-pw-user-id").innerText;
  const newPassword = document.getElementById("reset-pw-input").value.trim();

  if (!newPassword || newPassword.length < 6) {
    showToast("パスワードは6文字以上で入力してください。", "error");
    return;
  }

  try {
    const res = await authFetch(`/api/v1/users/${username}/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: newPassword }),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || data.error || "パスワードリセットに失敗しました。", "error");
      return;
    }

    showToast(`社員「${username}」のパスワードを再発行しました！🔑 (新パスワード: ${newPassword})`, "success");
    closeResetPwModal();
  } catch (err) {
    showToast(`パスワードリセット失敗: ${err.message}`, "error");
  }
}

// -------------------------------------------------------------
// Modal 5: Suspend / Reactivate Confirmation
// -------------------------------------------------------------
function openSuspendModal(username, displayName, currentlyActive) {
  const user = currentLoadedUsers.find(u => u.username === username);
  if (currentUser && currentUser.role !== "admin" && user && user.role === "admin") {
    showToast("⚠️ 管理者アカウントは編集長権限では利用停止できません（管理者保護）。", "error");
    return;
  }

  pendingSuspendAction = { username: username, is_active: !currentlyActive };
  document.getElementById("suspend-user-name").innerText = displayName;
  document.getElementById("suspend-user-id").innerText = username;

  const title = document.getElementById("suspend-modal-title");
  const warnBox = document.getElementById("suspend-warning-box");
  const btn = document.getElementById("btn-confirm-suspend");

  if (currentlyActive) {
    title.innerText = "🛑 アカウントの利用停止確認";
    warnBox.innerHTML = "🛑 <strong>即時アクセス遮断:</strong> アカウントを利用停止にすると、本人によるログインが即座に拒絶され、現在接続中のセッションも強制切断されます（過去の監査ログは保持されます）。";
    warnBox.className = "alert-box alert-danger";
    btn.innerText = "利用停止を実行する 🛑";
    btn.className = "btn btn-danger";
  } else {
    title.innerText = "🟢 アカウントの利用再開確認";
    warnBox.innerHTML = "🟢 <strong>アクセス復帰:</strong> アカウントを有効化すると、本人が通常通りログインして機能を利用できるようになります。";
    warnBox.className = "alert-box alert-warning";
    btn.innerText = "利用を再開する 🟢";
    btn.className = "btn btn-primary";
  }

  document.getElementById("modal-user-suspend").style.display = "flex";
}

function closeSuspendModal() {
  document.getElementById("modal-user-suspend").style.display = "none";
}

async function submitToggleStatus() {
  const { username, is_active } = pendingSuspendAction;
  try {
    const res = await authFetch(`/api/v1/users/${username}/status`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: is_active }),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || data.error || "状態変更に失敗しました。", "error");
      return;
    }

    const desc = is_active ? "有効化（利用再開）" : "利用停止（即時アクセス遮断）";
    showToast(`社員「${username}」を${desc}しました。`, "success");
    closeSuspendModal();
    loadUsers();
  } catch (err) {
    showToast(`状態変更失敗: ${err.message}`, "error");
  }
}

// -------------------------------------------------------------
// Modal 6: Strict Safety Delete (Input Confirmation Safety Lock)
// -------------------------------------------------------------
function openDeleteUserModal(username, displayName) {
  const user = currentLoadedUsers.find(u => u.username === username);
  if (currentUser && currentUser.role !== "admin" && user && user.role === "admin") {
    showToast("⚠️ 管理者アカウントは編集長権限では削除できません（管理者保護）。", "error");
    return;
  }

  pendingDeleteAction = { username: username, display_name: displayName };
  document.getElementById("delete-user-name").innerText = displayName;
  document.getElementById("delete-user-id").innerText = username;
  document.getElementById("delete-target-id-label").innerText = username;

  const input = document.getElementById("delete-confirm-input");
  input.value = "";
  document.getElementById("btn-execute-delete").disabled = true;

  document.getElementById("modal-user-delete").style.display = "flex";
  setTimeout(() => input.focus(), 100);
}

function closeDeleteUserModal() {
  document.getElementById("modal-user-delete").style.display = "none";
}

function handleDeleteConfirmInput() {
  const input = document.getElementById("delete-confirm-input").value.trim();
  const target = pendingDeleteAction.username;
  const btn = document.getElementById("btn-execute-delete");
  btn.disabled = (input !== target);
}

async function submitDeleteUser() {
  const target = pendingDeleteAction.username;
  try {
    const res = await authFetch(`/api/v1/users/${target}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || data.error || "削除に失敗しました。", "error");
      return;
    }

    showToast(`社員アカウント「${target}」を完全に抹消しました。🗑️`, "success");
    closeDeleteUserModal();
    loadUsers();
  } catch (err) {
    showToast(`ユーザー削除失敗: ${err.message}`, "error");
  }
}

// =============================================================
// 6. Audit Trail & Diagnostics (Admin Only)
// =============================================================
async function loadAuditLogs() {
  const tbody = document.getElementById("audit-table-body");
  if (!tbody) return;

  const userFilter = document.getElementById("audit-filter-user").value.trim();
  const actionFilter = document.getElementById("audit-filter-action").value;

  let url = "/api/v1/audit/logs?limit=50";
  if (userFilter) url += `&username=${encodeURIComponent(userFilter)}`;
  if (actionFilter) url += `&action=${encodeURIComponent(actionFilter)}`;

  try {
    const res = await authFetch(url);
    if (!res.ok) return;
    const logs = await res.json();

    tbody.innerHTML = "";
    if (!logs || logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:20px;">該当する監査ログはありません。</td></tr>';
      return;
    }

    logs.forEach(l => {
      const tr = document.createElement("tr");
      let statusClass = "badge-status-success";
      if (l.status === "FAILED") statusClass = "badge-status-failed";
      if (l.status === "FORBIDDEN") statusClass = "badge-status-forbidden";

      const timeStr = l.timestamp ? new Date(l.timestamp * 1000).toISOString().replace("T", " ").substring(0, 19) : "";

      tr.innerHTML = `
        <td style="white-space:nowrap;font-size:11.5px;color:var(--text-muted);">${timeStr}</td>
        <td><strong>${escapeHtml(l.username)}</strong></td>
        <td><span class="user-role-badge role-${l.role}">${escapeHtml(l.role)}</span></td>
        <td><code>${escapeHtml(l.action)}</code></td>
        <td>${escapeHtml(l.resource || "-")}</td>
        <td><span class="badge-status ${statusClass}">${escapeHtml(l.status)}</span></td>
        <td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(l.details)}">${escapeHtml(l.details)}</td>
        <td><small>${escapeHtml(l.ip_address || "127.0.0.1")}</small></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Load audit logs failed:", err);
  }
}

async function loadDiagnosticsLogs() {
  const container = document.getElementById("diagnostics-container");
  if (!container) return;

  try {
    const res = await authFetch("/api/v1/diagnostics/logs?limit=10");
    if (!res.ok) return;
    const logs = await res.json();

    if (!logs || logs.length === 0) {
      container.innerHTML = '<p class="placeholder-text" style="color:#9aa0a6;margin:10px 0;">システムエラーは記録されていません（すべてのコンポーネントが正常稼働中）。</p>';
      return;
    }

    container.innerHTML = "";
    logs.forEach(l => {
      const box = document.createElement("div");
      box.className = "stacktrace-box";
      box.innerHTML = `
        <div style="font-weight:700;color:#f28b82;margin-bottom:4px;">
          [${l.iso_time || ""}] [${l.level}] [${escapeHtml(l.component)}] ${escapeHtml(l.message)}
        </div>
        ${l.stack_trace ? `<pre style="font-size:11px;overflow-x:auto;color:#d2e3fc;margin-top:4px;">${escapeHtml(l.stack_trace)}</pre>` : ""}
      `;
      container.appendChild(box);
    });
  } catch (err) {
    console.error("Load diagnostics failed:", err);
  }
}

// =============================================================
// 7. Settings & Retention Management (Admin Only)
// =============================================================
async function loadSettings() {
  try {
    const res = await authFetch("/api/v1/settings");
    if (!res.ok) return;
    const data = await res.json();

    currentProvider = data.active_provider;
    if (data.active_provider === "gemini") {
      document.getElementById("prov-gemini").checked = true;
    } else {
      document.getElementById("prov-litert").checked = true;
    }
    toggleProviderSettings();

    // Populate Gemini models dynamically
    const modelSelect = document.getElementById("gemini-model-select");
    if (modelSelect && data.available_models && data.available_models.length > 0) {
      modelSelect.innerHTML = "";
      data.available_models.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.innerText = m.name;
        if (m.id === data.gemini_model) {
          opt.selected = true;
        }
        modelSelect.appendChild(opt);
      });
    }

    // Retention Days
    if (data.retention_days) {
      const retentionSel = document.getElementById("retention-select");
      if (retentionSel) retentionSel.value = String(data.retention_days);
    }

    // Masked Key status
    const keyInput = document.getElementById("gemini-key");
    const keyHint = document.getElementById("api-key-status");
    if (data.has_gemini_key) {
      keyInput.placeholder = `設定済み (${data.masked_gemini_key}) - 変更時のみ入力`;
      keyHint.innerText = `🔒 APIキーセキュリティ: サーバー側で暗号保持中 (${data.masked_gemini_key})。平文漏洩ゼロ。`;
    }

    updateActiveBadge(data.active_provider, data.gemini_model);
  } catch (err) {
    console.error("Failed to load settings:", err);
  }
}

function toggleProviderSettings() {
  const isGemini = document.getElementById("prov-gemini").checked;
  const panel = document.getElementById("gemini-settings-panel");
  panel.style.display = isGemini ? "block" : "none";
}

function updateActiveBadge(provider, geminiModel) {
  const badge = document.getElementById("active-badge");
  const text = document.getElementById("badge-text");

  if (provider === "gemini") {
    badge.className = "model-badge badge-cloud";
    const modelLabel = geminiModel || "Gemini 3.5 Flash Lite";
    text.innerText = `クラウド推論 (${modelLabel})`;
  } else {
    badge.className = "model-badge badge-local";
    text.innerText = "ローカル推論 (LiteRT-LM GPU)";
  }
}

async function saveAllSettings() {
  const isGemini = document.getElementById("prov-gemini").checked;
  const provider = isGemini ? "gemini" : "litert";
  const apiKey = document.getElementById("gemini-key").value.trim();
  const modelSelect = document.getElementById("gemini-model-select");
  const selectedModel = modelSelect ? modelSelect.value : "gemini-3.5-flash-lite";
  const retentionDays = parseInt(document.getElementById("retention-select").value, 10);

  try {
    // 1. Model / Provider settings
    const resModel = await authFetch("/api/v1/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: provider,
        gemini_api_key: apiKey || undefined,
        gemini_model: selectedModel,
      }),
    });
    if (!resModel.ok) throw new Error("推論設定の保存に失敗しました");

    // 2. Retention settings
    const resRet = await authFetch("/api/v1/settings/retention", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days: retentionDays }),
    });
    if (!resRet.ok) throw new Error("ログ保存期間設定の保存に失敗しました");

    showToast("推論モデルおよびログ保存期間設定（自動パージ）を保存・反映しました！", "success");
    document.getElementById("gemini-key").value = "";
    loadSettings();
  } catch (err) {
    showToast(`設定保存エラー: ${err.message}`, "error");
  }
}

async function discoverGeminiModels() {
  const btn = document.getElementById("btn-discover-models");
  const origBtnText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "<span>取得中... ⏳</span>";

  const keyInput = document.getElementById("gemini-key");
  const apiKey = keyInput ? keyInput.value.trim() : "";

  try {
    const res = await authFetch("/api/v1/models/discover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.message || "モデル一覧の取得に失敗しました");
    }

    const models = data.models || [];
    const modelSelect = document.getElementById("gemini-model-select");
    const currentVal = modelSelect.value;

    // Update select dropdown
    modelSelect.innerHTML = "";
    models.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.innerText = m.name;
      if (m.id === currentVal) {
        opt.selected = true;
      }
      modelSelect.appendChild(opt);
    });

    // Render discovered models list cards
    const section = document.getElementById("discovered-models-section");
    const container = document.getElementById("discovered-models-list");
    const countSpan = document.getElementById("discovered-count");
    const badgeSpan = document.getElementById("discovered-badge");

    if (section && container) {
      section.style.display = "block";
      countSpan.innerText = String(models.length);
      badgeSpan.innerText = data.status === "SUCCESS" ? "● Google公式API接続成功 (最新)" : "● 推奨一覧表示";

      container.innerHTML = "";
      models.forEach(m => {
        const card = document.createElement("div");
        const isSelected = (m.id === modelSelect.value);
        card.className = `discovered-model-card ${isSelected ? "active-model" : ""}`;
        card.id = `model-card-${m.id.replace(/[^a-zA-Z0-9_-]/g, "_")}`;

        let limitsHtml = "";
        if (m.input_token_limit || m.output_token_limit) {
          limitsHtml = `
            <div class="discovered-model-meta">
              ${m.input_token_limit ? `<span>入力上限: ${m.input_token_limit.toLocaleString()} tokens</span>` : ""}
              ${m.output_token_limit ? `<span>出力上限: ${m.output_token_limit.toLocaleString()} tokens</span>` : ""}
            </div>
          `;
        }

        card.innerHTML = `
          <div class="discovered-model-info">
            <div class="discovered-model-title">
              <span>${escapeHtml(m.display_name || m.name)}</span>
              <span class="discovered-model-id">${escapeHtml(m.id)}</span>
            </div>
            <div class="discovered-model-desc">${escapeHtml(m.description || "")}</div>
            ${limitsHtml}
          </div>
          <button type="button" class="btn ${isSelected ? "btn-primary" : "btn-secondary"} btn-xs btn-select-discovered-model" data-model-id="${escapeHtml(m.id)}">
            ${isSelected ? "選択中 ✓" : "このモデルを選択"}
          </button>
        `;
        container.appendChild(card);
      });

      if (!container._securityDelegated) {
        container._securityDelegated = true;
        container.addEventListener("click", (e) => {
          const btn = e.target.closest(".btn-select-discovered-model");
          if (btn && btn.dataset.modelId) {
            selectDiscoveredModel(btn.dataset.modelId);
          }
        });
      }
    }

    showToast(data.message || "公開利用可能なGeminiモデル一覧を取得しました！", data.status === "SUCCESS" ? "success" : "info");

  } catch (err) {
    showToast(`モデル取得失敗: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = origBtnText;
  }
}

function selectDiscoveredModel(modelId) {
  const modelSelect = document.getElementById("gemini-model-select");
  if (modelSelect) {
    modelSelect.value = modelId;
  }
  // Update card UI highlights
  document.querySelectorAll(".discovered-model-card").forEach(c => {
    c.classList.remove("active-model");
    const btn = c.querySelector("button");
    if (btn) {
      btn.className = "btn btn-secondary btn-xs";
      btn.innerText = "このモデルを選択";
    }
  });

  const targetCard = document.getElementById(`model-card-${modelId.replace(/[^a-zA-Z0-9_-]/g, "_")}`);
  if (targetCard) {
    targetCard.classList.add("active-model");
    const btn = targetCard.querySelector("button");
    if (btn) {
      btn.className = "btn btn-primary btn-xs";
      btn.innerText = "選択中 ✓";
    }
  }

  showToast(`モデル『${modelId}』を選択しました。下の「保存」ボタンで確定できます。`, "info");
}

/* ==========================================================================
   Google Workspace SSO & Google Drive Synchronization Logic
   ========================================================================== */

function openGoogleSSOModal() {
  const m = document.getElementById("modal-google-sso");
  if (m) m.style.display = "flex";
}

function closeGoogleSSOModal() {
  const m = document.getElementById("modal-google-sso");
  if (m) m.style.display = "none";
}

// UTF-8 safe Base64URL encoder (btoa() throws on non-Latin1 text such as Japanese names)
function b64urlEncodeUtf8(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  bytes.forEach((b) => (bin += String.fromCharCode(b)));
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

// Store the session issued by Google SSO (previously undefined -> login silently failed)
function saveSession(token, user) {
  authToken = token;
  currentUser = user || null;
  sessionStorage.setItem("auth_token", authToken);
}

// After SSO: fetch full profile (incl. permissions) and enter the app
async function loadInitialData() {
  await verifyAndResumeSession();
}

async function simulateGoogleLogin(email, name) {
  try {
    // Generate valid test JWT payload
    const now = Math.floor(Date.now() / 1000);
    const domain = email.includes("@") ? email.split("@")[1] : "company.com";
    const header = b64urlEncodeUtf8(JSON.stringify({ alg: "RS256", typ: "JWT" }));
    const payload = b64urlEncodeUtf8(JSON.stringify({
      sub: "goog_" + Math.random().toString(36).substring(2, 10),
      email: email,
      name: name,
      hd: domain,
      exp: now + 3600,
      iat: now,
    }));
    const fakeToken = `${header}.${payload}.simulated_signature`;

    const res = await fetch("/api/v1/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: fakeToken }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.message || data.error || "Google SSO認証に失敗しました。");
    }

    closeGoogleSSOModal();
    saveSession(data.token, data.user);

    if (data.is_new_user) {
      showToast(`Google SSOログイン成功: ${data.user.display_name} さん（一般ユーザー権限で自動登録されました）✨`, "success");
    } else {
      showToast(`Google SSOログイン成功: ${data.user.display_name} さん 🚀`, "success");
    }

    loadInitialData();
  } catch (err) {
    console.error("Google SSO error:", err);
    showToast(err.message, "error");
  }
}

async function submitGoogleTokenLogin() {
  const tokenInput = document.getElementById("google-id-token-input");
  const rawToken = tokenInput ? tokenInput.value.trim() : "";
  if (!rawToken) {
    showToast("IDトークンを入力してください。", "warning");
    return;
  }

  try {
    const res = await fetch("/api/v1/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: rawToken }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.message || data.error || "Google SSO認証に失敗しました。");
    }

    closeGoogleSSOModal();
    saveSession(data.token, data.user);
    showToast(`Googleログイン成功: ${data.user.display_name} さん`, "success");
    loadInitialData();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function loadDriveSyncStatus() {
  try {
    const res = await authFetch("/api/v1/drive/status");
    if (!res.ok) return;
    const data = await res.json();

    const stElem = document.getElementById("drive-stat-status");
    const timeElem = document.getElementById("drive-stat-last-time");
    const fileElem = document.getElementById("drive-stat-files");
    const blkElem = document.getElementById("drive-stat-blocks");

    if (stElem) {
      let badgeClass = "badge-dot-active";
      let statusText = "待機中 (IDLE)";
      if (data.status === "SYNCING") {
        statusText = "同期中 (SYNCING)...";
        badgeClass = "badge-dot-syncing";
      } else if (data.status === "SUCCESS") {
        statusText = "最新 (SUCCESS)";
      } else if (data.status === "ERROR") {
        statusText = "エラー (ERROR)";
        badgeClass = "badge-dot-error";
      }
      stElem.innerHTML = `<span class="badge-dot ${badgeClass}"></span> ${statusText}`;
    }

    if (timeElem) timeElem.innerText = data.last_sync_time || "--";
    if (fileElem) fileElem.innerHTML = `${data.synced_file_count || 0} <span style="font-size:13px;font-weight:normal;">件</span>`;
    if (blkElem) blkElem.innerHTML = `${data.indexed_block_count || 0} <span style="font-size:13px;font-weight:normal;">ブロック</span>`;
  } catch (err) {
    console.warn("Failed to load drive sync status:", err);
  }
}

async function triggerDriveSync() {
  if (!authToken) {
    showToast("🔒 ログインが必要です。社内アカウントでログインしてください。", "warning");
    return;
  }
  if (currentUser && currentUser.role !== "admin" && currentUser.role !== "editor") {
    showToast("⚠️ Google Driveの同期実行にはナレッジ編集者（Editor）以上の権限が必要です。", "warning");
    return;
  }

  const btn = document.getElementById("btn-sync-drive");
  const origText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>⏳ 同期中...</span>`;
  }

  try {
    const res = await authFetch("/api/v1/drive/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.message || data.error || "Drive同期に失敗しました。");
    }

    showToast(`Google Drive同期完了！ (追加: ${data.added}件, 更新: ${data.updated}件, 削除: ${data.purged}件)`, "success");
    await loadDriveSyncStatus();
    if (typeof loadKnowledgeBlocks === "function") {
      loadKnowledgeBlocks();
    }
  } catch (err) {
    showToast(`同期エラー: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  }
}

let driveTargetFoldersList = [];

async function openDriveFolderModal() {
  if (!authToken) {
    showToast("🔒 ログインが必要です。社内アカウントでログインしてください。", "warning");
    return;
  }
  if (currentUser && currentUser.role !== "admin" && currentUser.role !== "editor") {
    showToast("⚠️ 同期対象フォルダの設定にはナレッジ編集者（Editor）以上の権限が必要です。", "warning");
    return;
  }

  const m = document.getElementById("modal-drive-folders");
  if (m) m.style.display = "flex";
  await loadDriveFolders();
}

function closeDriveFolderModal() {
  const m = document.getElementById("modal-drive-folders");
  if (m) m.style.display = "none";
}

async function loadDriveFolders() {
  try {
    const res = await authFetch("/api/v1/drive/folders");
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(err.message || "同期対象フォルダ一覧の取得に失敗しました。", "error");
      return;
    }
    const data = await res.json();
    driveTargetFoldersList = data.folders || [];
    renderDriveFolderRows();
  } catch (err) {
    console.warn("Failed to load drive folders:", err);
  }
}

function renderDriveFolderRows() {
  const container = document.getElementById("drive-folders-list");
  if (!container) return;

  if (driveTargetFoldersList.length === 0) {
    container.innerHTML = `<div style="color:var(--text-muted); font-size:13px; padding:12px; text-align:center; background:#f8fafc; border-radius:6px;">現在、同期対象フォルダは未設定です（全Drive監視または個別指定可能）。</div>`;
    return;
  }

  container.innerHTML = driveTargetFoldersList.map((f, idx) => `
    <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 14px; background:#fff; border:1px solid var(--border); border-radius:6px; margin-bottom:6px;">
      <div>
        <strong style="font-size:13.5px;">📁 ${escapeHtml(f.folder_name)}</strong>
        <div style="font-size:11.5px; color:var(--text-muted); font-family:monospace;">ID: ${escapeHtml(f.folder_id)}</div>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <span class="user-role-badge role-${f.required_role || 'viewer'}">${f.required_role === 'admin' ? 'Admin限定' : (f.required_role === 'editor' ? 'Editor以上' : 'Viewer以上')}</span>
        <button class="btn btn-xs btn-outline" style="color:var(--danger);" onclick="removeDriveFolderRow(${idx})">削除</button>
      </div>
    </div>
  `).join("");
}

function addNewFolderRow() {
  const nameInput = document.getElementById("new-folder-name");
  const idInput = document.getElementById("new-folder-id");
  const roleSelect = document.getElementById("new-folder-role");

  const folderName = nameInput ? nameInput.value.trim() : "";
  const folderId = idInput ? idInput.value.trim() : "";
  const role = roleSelect ? roleSelect.value : "viewer";

  if (!folderId) {
    showToast("フォルダIDを入力してください。", "warning");
    return;
  }

  driveTargetFoldersList.push({
    folder_id: folderId,
    folder_name: folderName || folderId,
    required_role: role,
  });

  if (nameInput) nameInput.value = "";
  if (idInput) idInput.value = "";

  renderDriveFolderRows();
}

function removeDriveFolderRow(idx) {
  driveTargetFoldersList.splice(idx, 1);
  renderDriveFolderRows();
}

async function saveDriveFolders() {
  try {
    const res = await authFetch("/api/v1/drive/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folders: driveTargetFoldersList }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.message || "フォルダ設定の保存に失敗しました。");
    }
    showToast("同期対象フォルダ設定を保存しました！", "success");
    closeDriveFolderModal();
    loadDriveSyncStatus();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// =============================================================
// Model Context Protocol (MCP) Server Integration Helpers
// =============================================================
async function testMCPEndpoint() {
  const btn = document.getElementById("btn-test-mcp");
  const origText = btn ? btn.innerHTML : "";
  const resultBox = document.getElementById("mcp-test-result");
  const statusElem = document.getElementById("mcp-test-status");
  const outputElem = document.getElementById("mcp-test-output");

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "<span>⏳ MCP 疎通テスト中...</span>";
  }

  try {
    const res = await fetch("/mcp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: "test-ping-1",
        method: "tools/list",
        params: {}
      })
    });

    const data = await res.json();
    if (resultBox) resultBox.style.display = "block";

    if (res.ok && data.result && data.result.tools) {
      const toolNames = data.result.tools.map(t => t.name).join(", ");
      if (statusElem) {
        statusElem.innerHTML = `<span style="color:var(--success);">✅ 疎通成功 (HTTP 200 OK): MCPサーバーは正常稼働中です！</span><div style="font-size:12px; font-weight:normal; margin-top:4px;">利用可能なツール: <code>${escapeHtml(toolNames)}</code></div>`;
      }
      if (outputElem) {
        outputElem.innerText = JSON.stringify(data, null, 2);
      }
      showToast("⚡ MCP サーバーとの疎通に成功しました！", "success");
    } else {
      if (statusElem) {
        statusElem.innerHTML = `<span style="color:var(--danger);">❌ エラー: 予期しないレスポンスが返却されました</span>`;
      }
      if (outputElem) {
        outputElem.innerText = JSON.stringify(data, null, 2);
      }
      showToast("MCP 疎通テストでエラーが発生しました。", "error");
    }
  } catch (err) {
    if (resultBox) resultBox.style.display = "block";
    if (statusElem) {
      statusElem.innerHTML = `<span style="color:var(--danger);">❌ 通信失敗: ${escapeHtml(err.message)}</span>`;
    }
    if (outputElem) {
      outputElem.innerText = err.stack || err.message;
    }
    showToast(`MCP テスト失敗: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  }
}

function copyMCPConfigSnippet() {
  const snippet = document.getElementById("mcp-config-snippet");
  if (!snippet) return;
  const text = snippet.innerText;
  navigator.clipboard.writeText(text).then(() => {
    showToast("📋 Claude Desktop設定用JSONをクリップボードにコピーしました！", "success");
  }).catch(() => {
    showToast("コピーに失敗しました。テキストを手動で選択してください。", "error");
  });
}


