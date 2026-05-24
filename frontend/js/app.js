// app.js - 全局状态管理和初始化

const App = {
  state: {
    conversationId: null,
    messages: [],
    category: "",
    context: {
      weather: "",
      season: "",
      ingredients: "",
      recipe: "",
      extra: "",
      duration: "60",
    },
    staged: {
      recipe: "",
      cooking_method: "",
      script: "",
    },
    isGenerating: false,
  },

  init() {
    this.bindElements();
    this.bindEvents();
    this.loadApiKey();
    this.createNewConversation();
    this.restoreContext();
    this.restoreFeishuConfig();
  },

  async restoreFeishuConfig() {
    // Push saved Feishu credentials to server on load
    const appId = localStorage.getItem("feishu_app_id") || "";
    const appSecret = localStorage.getItem("feishu_app_secret") || "";
    if (appId && appSecret) {
      try {
        await fetch("/api/feishu/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ app_id: appId, app_secret: appSecret }),
        });
      } catch (e) { /* server might not be ready yet */ }
    }
  },

  bindElements() {
    this.el = {
      conversationList: document.getElementById("conversation-list"),
      chatMessages: document.getElementById("chat-messages"),
      chatInput: document.getElementById("chat-input"),
      btnSend: document.getElementById("btn-send"),
      categoryList: document.getElementById("category-list"),
      btnSettings: document.getElementById("btn-settings"),
      settingsModal: document.getElementById("settings-modal"),
      settingsApiKey: document.getElementById("settings-apikey"),
      settingsFeishuAppId: document.getElementById("settings-feishu-appid"),
      settingsFeishuAppSecret: document.getElementById("settings-feishu-appsecret"),
      settingsFeishuCallback: document.getElementById("settings-feishu-callback"),
      btnSettingsSave: document.getElementById("btn-settings-save"),
      btnSettingsCancel: document.getElementById("btn-settings-cancel"),
      ctxWeather: document.getElementById("ctx-weather"),
      ctxSeason: document.getElementById("ctx-season"),
      ctxIngredients: document.getElementById("ctx-ingredients"),
      ctxRecipe: document.getElementById("ctx-recipe"),
      ctxExtra: document.getElementById("ctx-extra"),
      ctxDuration: document.getElementById("ctx-duration"),
      outputSection: document.getElementById("output-section"),
      outputContent: document.getElementById("output-content"),
      auditContent: document.getElementById("audit-content"),
      btnCopyOutput: document.getElementById("btn-copy-output"),
      toast: document.getElementById("toast"),
      welcome: document.querySelector(".welcome-message"),
    };
  },

  bindEvents() {
    this.el.btnSend.addEventListener("click", () => this.sendMessage());
    this.el.chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    this.el.btnSettings.addEventListener("click", () => this.openSettings());
    if (this.el.categoryList) {
      this.el.categoryList.addEventListener("click", (e) => {
        const btn = e.target.closest(".cat-btn");
        if (!btn) return;
        this.switchCategory(btn.dataset.category);
      });
    }
    this.el.btnSettingsSave.addEventListener("click", () => this.saveSettings());
    this.el.btnSettingsCancel.addEventListener("click", () => this.closeSettings());
    this.el.settingsModal.addEventListener("click", (e) => {
      if (e.target === this.el.settingsModal) this.closeSettings();
    });

    this.el.btnCopyOutput.addEventListener("click", () => this.copyOutput());

    // 上下文自动保存
    ["ctxWeather", "ctxSeason", "ctxIngredients", "ctxRecipe", "ctxExtra", "ctxDuration"].forEach((id) => {
      this.el[id].addEventListener("change", () => this.saveContext());
      this.el[id].addEventListener("input", () => this.saveContext());
    });

    // 快捷按钮在 panels.js 中绑定
  },

  // ===== 对话管理 =====
  switchCategory(categoryId) {
    this.state.category = categoryId;
    this.el.categoryList.querySelectorAll(".cat-btn").forEach(b => b.classList.remove("active"));
    const btn = this.el.categoryList.querySelector(`[data-category="${categoryId}"]`);
    if (btn) btn.classList.add("active");

    const catNames = { "": "自由对话", health_light: "健康简餐", gourmet: "美食料理", health_tea: "养生茶饮", seasonal: "时令养生", tonic: "滋补炖品", fermented: "发酵美食" };
    const name = catNames[categoryId] || "自由对话";
    this.showToast(`已切换到：${name}`);
  },

  async createNewConversation() {
    try {
      const res = await fetch("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "新对话" }),
      });
      const data = await res.json();
      this.state.conversationId = data.conversation.id;
      this.state.messages = [];
      this.renderMessages();
      this.loadConversationList();
      this.hideWelcome(false);
    } catch (e) {
      console.error("创建对话失败:", e);
    }
  },

  async loadConversationList() {
    try {
      const res = await fetch("/api/conversations");
      const data = await res.json();
      this.el.conversationList.innerHTML = data.conversations
        .map(
          (c) => `
        <div class="conv-item${c.id === this.state.conversationId ? " active" : ""}" data-id="${c.id}">
          <span class="conv-title" title="${this.escapeHtml(c.title)}">${this.escapeHtml(c.title)}</span>
          <button class="conv-delete" data-id="${c.id}">✕</button>
        </div>`
        )
        .join("");

      this.el.conversationList.querySelectorAll(".conv-item").forEach((item) => {
        item.addEventListener("click", (e) => {
          if (e.target.classList.contains("conv-delete")) return;
          this.loadConversation(item.dataset.id);
        });
      });

      this.el.conversationList.querySelectorAll(".conv-delete").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          this.deleteConversation(btn.dataset.id);
        });
      });
    } catch (e) {
      console.error("加载对话列表失败:", e);
    }
  },

  async loadConversation(id) {
    try {
      const res = await fetch(`/api/conversations/${id}`);
      if (!res.ok) return;
      const data = await res.json();
      this.state.conversationId = id;
      this.state.messages = data.conversation.messages || [];
      this.renderMessages();
      this.loadConversationList();
      this.hideWelcome(this.state.messages.length > 0);
    } catch (e) {
      console.error("加载对话失败:", e);
    }
  },

  async deleteConversation(id) {
    try {
      await fetch(`/api/conversations/${id}`, { method: "DELETE" });
      if (id === this.state.conversationId) {
        this.createNewConversation();
      } else {
        this.loadConversationList();
      }
    } catch (e) {
      console.error("删除对话失败:", e);
    }
  },

  async saveConversation() {
    if (!this.state.conversationId || this.state.messages.length === 0) return;
    try {
      await fetch(`/api/conversations/${this.state.conversationId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: this.state.messages }),
      });
      this.loadConversationList();
    } catch (e) {
      console.error("保存对话失败:", e);
    }
  },

  // ===== 消息发送 =====
  async sendMessage() {
    const text = this.el.chatInput.value.trim();
    if (!text || this.state.isGenerating) return;

    this.el.chatInput.value = "";
    this.hideWelcome(true);

    const userMsg = { role: "user", content: text };
    this.state.messages.push(userMsg);
    this.renderMessages();

    this.state.isGenerating = true;
    this.el.btnSend.disabled = true;

    const assistantMsg = { role: "assistant", content: "" };
    this.state.messages.push(assistantMsg);

    try {
      const body = this.buildRequestBody();
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") break;
            try {
              const parsed = JSON.parse(data);
              if (parsed.error) {
                assistantMsg.content += parsed.content;
              } else {
                assistantMsg.content += parsed.content;
              }
              this.renderMessages();
            } catch (e) { /* partial chunk, ignore */ }
          }
        }
      }
    } catch (e) {
      assistantMsg.content += `\n\n> ⚠️ 请求失败：${e.message}`;
    }

    this.state.isGenerating = false;
    this.el.btnSend.disabled = false;
    this.renderMessages();
    this.saveConversation();
  },

  buildRequestBody() {
    return {
      messages: this.state.messages.slice(0, -1),
      conversation_id: this.state.conversationId,
      category: this.state.category,
      weather: this.state.context.weather,
      season: this.state.context.season,
      ingredients: this.state.context.ingredients,
      recipe: this.state.context.recipe || this.state.staged.recipe,
      extra: this.state.context.extra,
      duration: this.state.context.duration || "60",
      cooking_method: this.state.staged.cooking_method,
    };
  },

  // ===== 渲染 =====
  renderMessages() {
    const container = this.el.chatMessages;
    container.innerHTML = "";

    if (this.state.messages.length === 0 && this.el.welcome) {
      container.appendChild(this.el.welcome);
      this.el.welcome.style.display = "";
      return;
    }

    this.state.messages.forEach((msg, idx) => {
      const isLast = idx === this.state.messages.length - 1;
      const isStreaming = isLast && this.state.isGenerating && msg.role === "assistant";

      const div = document.createElement("div");
      div.className = `message ${msg.role}`;
      div.innerHTML = `
        <div class="msg-role">${msg.role === "user" ? "🧑 你" : "🤖 助手"}</div>
        <div class="msg-content${isStreaming ? " streaming-cursor" : ""}">${this.renderMarkdown(msg.content)}</div>
        ${msg.role === "assistant" && msg.content && !isStreaming ? '<div class="msg-actions"><button class="btn-msg-copy">📋 复制</button></div>' : ""}
      `;

      const copyBtn = div.querySelector(".btn-msg-copy");
      if (copyBtn) {
        copyBtn.addEventListener("click", () => {
          navigator.clipboard.writeText(msg.content).then(() => {
            copyBtn.textContent = "✓ 已复制";
            setTimeout(() => (copyBtn.textContent = "📋 复制"), 1500);
          });
        });
      }

      container.appendChild(div);
    });

    container.scrollTop = container.scrollHeight;
  },

  renderMarkdown(text) {
    if (!text) return "";
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // 标题
    html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");

    // 粗体
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    // 表格（简单处理）
    html = html.replace(/^\|(.+)\|$/gm, (match) => {
      const cells = match.split("|").filter((c) => c.trim());
      if (cells.every((c) => /^[-:]+$/.test(c.trim()))) return "<!--sep-->";
      const tag = match.includes("<!--sep-->") ? "th" : "td";
      return `<tr>${cells.map((c) => `<${tag}>${c.trim()}</${tag}>`).join("")}</tr>`;
    });

    // 无序列表
    html = html.replace(/^[\*\-] (.+)$/gm, "<li>$1</li>");
    html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

    // 有序列表
    html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

    // 代码块
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    // 引用
    html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

    // 分段
    html = html.replace(/\n\n+/g, "</p><p>");
    html = "<p>" + html + "</p>";
    html = html.replace(/<p>\s*<\/p>/g, "");
    html = html.replace(/<p><h([234])>/g, "<h$1>");
    html = html.replace(/<\/h([234])><\/p>/g, "</h$1>");
    html = html.replace(/<p><ul>/g, "<ul>");
    html = html.replace(/<\/ul><\/p>/g, "</ul>");
    html = html.replace(/<p><blockquote>/g, "<blockquote>");
    html = html.replace(/<\/blockquote><\/p>/g, "</blockquote>");
    html = html.replace(/<p><pre>/g, "<pre>");
    html = html.replace(/<\/pre><\/p>/g, "</pre>");

    // 表格包裹
    if (html.includes("<tr>")) {
      html = html.replace(/((?:<tr>.*?<\/tr>\n?)+)/gs, (match) => {
        const clean = match.replace(/<!--sep-->\n?/g, "");
        return `<table>${clean}</table>`;
      });
    }

    return html;
  },

  hideWelcome(hidden) {
    if (this.el.welcome) {
      this.el.welcome.style.display = hidden ? "none" : "";
    }
  },

  // ===== 设置 =====
  openSettings() {
    this.el.settingsApiKey.value = this.getApiKey();
    this.el.settingsFeishuAppId.value = localStorage.getItem("feishu_app_id") || "";
    this.el.settingsFeishuAppSecret.value = localStorage.getItem("feishu_app_secret") || "";
    // Set callback URL (current host + /api/feishu/event)
    this.el.settingsFeishuCallback.value = window.location.origin + "/api/feishu/event";
    this.el.settingsModal.style.display = "flex";
  },

  closeSettings() {
    this.el.settingsModal.style.display = "none";
  },

  async saveSettings() {
    const key = this.el.settingsApiKey.value.trim();
    localStorage.setItem("deepseek_api_key", key);

    // Push Feishu bot credentials to server
    const appId = this.el.settingsFeishuAppId.value.trim();
    const appSecret = this.el.settingsFeishuAppSecret.value.trim();
    if (appId && appSecret) {
      localStorage.setItem("feishu_app_id", appId);
      localStorage.setItem("feishu_app_secret", appSecret);
      try {
        const res = await fetch("/api/feishu/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ app_id: appId, app_secret: appSecret }),
        });
        const data = await res.json();
        if (data.ok) {
          this.showToast("设置已保存 | 飞书机器人凭证验证通过");
        } else {
          this.showToast("设置已保存 | ⚠️ 飞书凭证验证失败：" + (data.error || "未知错误"));
        }
        this.closeSettings();
        return;
      } catch (e) {
        // Server may not be running, just save locally
        this.showToast("设置已保存（本地），服务器连接失败");
      }
    }

    this.closeSettings();
    this.showToast("设置已保存");
  },

  getApiKey() {
    return localStorage.getItem("deepseek_api_key") || "";
  },

  loadApiKey() {
    // API key is saved in localStorage and sent with requests
  },

  // ===== 上下文 =====
  readContext() {
    this.state.context = {
      weather: this.el.ctxWeather.value.trim(),
      season: this.el.ctxSeason.value,
      ingredients: this.el.ctxIngredients.value.trim(),
      recipe: this.el.ctxRecipe.value.trim(),
      extra: this.el.ctxExtra.value.trim(),
      duration: this.el.ctxDuration.value,
    };
    return this.state.context;
  },

  saveContext() {
    this.readContext();
    localStorage.setItem("writing_context", JSON.stringify(this.state.context));
  },

  restoreContext() {
    try {
      const saved = JSON.parse(localStorage.getItem("writing_context"));
      if (saved) {
        this.state.context = saved;
        this.el.ctxWeather.value = saved.weather || "";
        this.el.ctxSeason.value = saved.season || "";
        this.el.ctxIngredients.value = saved.ingredients || "";
        this.el.ctxRecipe.value = saved.recipe || "";
        this.el.ctxExtra.value = saved.extra || "";
        this.el.ctxDuration.value = saved.duration || "60";
      }
    } catch (e) { /* ignore */ }
  },

  // ===== 工具 =====
  copyOutput() {
    const text = this.el.outputContent.textContent;
    navigator.clipboard.writeText(text).then(() => {
      this.el.btnCopyOutput.textContent = "✓ 已复制";
      this.el.btnCopyOutput.classList.add("copied");
      setTimeout(() => {
        this.el.btnCopyOutput.textContent = "📋 复制";
        this.el.btnCopyOutput.classList.remove("copied");
      }, 1500);
    });
  },

  showToast(message) {
    const toast = this.el.toast;
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2000);
  },

  escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  },
};

document.addEventListener("DOMContentLoaded", () => App.init());
