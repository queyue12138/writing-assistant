// panels.js - 快捷操作面板和上下文管理

const Panels = {
  init() {
    this.bindQuickActions();
    this.bindPipeline();
    this.bindClearHistory();
    this.bindOutputTabs();
    this.bindFeishuDebug();
    this.loadDbStats();
    this.checkFeishuStatus();
  },

  bindFeishuDebug() {
    document.getElementById("btn-feishu-check")?.addEventListener("click", () => this.checkFeishuStatus());
    document.getElementById("btn-feishu-logs")?.addEventListener("click", () => this.showFeishuLogs());
    document.getElementById("btn-feishu-test")?.addEventListener("click", () => this.testFeishuMessage());
    document.getElementById("btn-feishu-poll-start")?.addEventListener("click", () => this.feishuPollStart());
    document.getElementById("btn-feishu-poll-stop")?.addEventListener("click", () => this.feishuPollStop());
    document.getElementById("btn-feishu-poll-once")?.addEventListener("click", () => this.feishuPollOnce());
  },

  async checkFeishuStatus() {
    const el = document.getElementById("feishu-debug-status");
    if (!el) return;
    el.textContent = "状态：检查中...";
    try {
      const [configRes, pollRes] = await Promise.all([
        fetch("/api/feishu/config"),
        fetch("/api/feishu/polling"),
      ]);
      const config = await configRes.json();
      const polling = await pollRes.json();

      let statusHtml = "";
      if (config.configured) {
        statusHtml = `凭证：<span style="color:var(--accent-green);">✅ 已配置</span> (${config.app_id_masked})`;
      } else {
        statusHtml = `凭证：<span style="color:var(--accent-yellow);">⚠️ 未配置</span>`;
      }
      statusHtml += ` | 轮询：${polling.active
        ? '<span style="color:var(--accent-green);">▶ 运行中</span>'
        : '<span style="color:var(--text-muted);">⏸ 已停止</span>'}`;
      statusHtml += ` | 回调：<code style="color:var(--accent-yellow);font-size:10px;">${window.location.origin}/api/feishu/event</code>`;
      el.innerHTML = statusHtml;

      // Update polling status
      const pollEl = document.getElementById("feishu-polling-status");
      if (pollEl) {
        pollEl.textContent = polling.active
          ? `轮询运行中 · 已处理 ${polling.processed_count} 条消息 · 每8秒检查一次`
          : "轮询未启动，点击下方 ▶ 启动";
      }
    } catch (e) {
      el.textContent = "状态：❌ 检查失败";
    }
  },

  async feishuPollStart() {
    try {
      const res = await fetch("/api/feishu/polling/start", { method: "POST" });
      const data = await res.json();
      App.showToast(data.ok ? "✅ " + data.message : "❌ " + (data.error || "失败"));
      this.checkFeishuStatus();
    } catch (e) {
      App.showToast("❌ 启动失败");
    }
  },

  async feishuPollStop() {
    try {
      const res = await fetch("/api/feishu/polling/stop", { method: "POST" });
      const data = await res.json();
      App.showToast("⏹ " + data.message);
      this.checkFeishuStatus();
    } catch (e) {
      App.showToast("❌ 停止失败");
    }
  },

  async feishuPollOnce() {
    try {
      const res = await fetch("/api/feishu/polling/once", { method: "POST" });
      const data = await res.json();
      if (data.ok) {
        App.showToast(`🔄 轮询完成，处理了 ${data.processed} 条消息`);
        setTimeout(() => this.showFeishuLogs(), 1000);
      } else {
        App.showToast("❌ " + (data.error || "轮询失败"));
      }
    } catch (e) {
      App.showToast("❌ 请求失败");
    }
  },

  async showFeishuLogs() {
    const view = document.getElementById("feishu-log-view");
    if (!view) return;
    try {
      const res = await fetch("/api/feishu/log");
      const data = await res.json();
      if (data.events.length === 0) {
        view.innerHTML = '<span style="color:var(--text-muted);">暂无事件记录。飞书还没有向服务器发送过任何请求。</span>';
      } else {
        view.innerHTML = data.events.map(e =>
          `<div><span style="color:var(--accent-yellow);">[${e._time}]</span> <span style="color:var(--accent);">${e.type}</span> ${e.summary || ''}</div>`
        ).join("");
      }
      view.style.display = "";
    } catch (e) {
      view.innerHTML = "加载失败";
      view.style.display = "";
    }
  },

  async testFeishuMessage() {
    const input = document.getElementById("feishu-test-msg");
    const text = input?.value.trim();
    if (!text) {
      App.showToast("⚠️ 请输入测试消息");
      return;
    }

    const btn = document.getElementById("btn-feishu-test");
    btn.disabled = true;
    btn.textContent = "⏳ 处理中...";

    try {
      const res = await fetch("/api/generate/audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: text,
          simulate_feishu: true,
        }),
      });
      // Actually, let's use the feishu event endpoint directly for testing
      const testRes = await fetch("/api/feishu/event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          schema: "2.0",
          header: { event_type: "im.message.receive_v1" },
          event: {
            message: {
              message_id: "test_" + Date.now(),
              message_type: "text",
              content: JSON.stringify({ text: text }),
            },
            sender: {
              sender_id: { open_id: "test_user" },
            },
          },
        }),
      });

      const data = await testRes.json();
      App.showToast("测试消息已发送，查看控制台和日志了解处理结果");

      // Wait a bit then show logs
      setTimeout(() => this.showFeishuLogs(), 2000);
    } catch (e) {
      App.showToast("❌ 测试失败：" + e.message);
    }

    btn.disabled = false;
    btn.textContent = "🧪 模拟飞书消息（本地测试）";
  },

  _activeTab: "content",

  bindOutputTabs() {
    document.querySelectorAll(".output-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        this._activeTab = tab.dataset.tab;
        document.querySelectorAll(".output-tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById("output-content").style.display = this._activeTab === "content" ? "" : "none";
        document.getElementById("audit-content").style.display = this._activeTab === "audit" ? "" : "none";
      });
    });
  },

  bindQuickActions() {
    document.querySelectorAll(".qa-btn:not(.pipeline-btn)").forEach((btn) => {
      btn.addEventListener("click", () => {
        const action = btn.dataset.action;
        if (action) this.runAction(action, btn);
      });
    });
  },

  bindPipeline() {
    const btn = document.getElementById("btn-pipeline");
    if (btn) {
      btn.addEventListener("click", () => this.runPipeline(btn));
    }
  },

  async runPipeline(btn) {
    App.readContext();
    const ctx = App.state.context;

    if (!ctx.ingredients && !ctx.recipe) {
      App.showToast("⚠️ 请先在右侧面板填写食材或食谱");
      return;
    }

    btn.disabled = true;
    const origText = btn.textContent;
    const pipelineSteps = [
      "生成食谱", "生成烹饪方法", "生成口播文案",
      "审核口播文案", "生成拍摄分镜"
    ];
    let stepIdx = 0;

    try {
      btn.textContent = `⏳ ${pipelineSteps[stepIdx]}...`;

      const userMessage = App.el.chatInput.value.trim();
      const body = {
        ingredients: ctx.ingredients,
        recipe: ctx.recipe || "",
        extra: ctx.extra || "",
        weather: ctx.weather || "",
        season: ctx.season || "",
        duration: ctx.duration || "60",
        user_message: userMessage,
      };

      // Update progress periodically
      const progressInterval = setInterval(() => {
        stepIdx = Math.min(stepIdx + 1, pipelineSteps.length - 1);
        btn.textContent = `⏳ ${pipelineSteps[stepIdx]}...`;
      }, 3000);

      const res = await fetch("/api/generate/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      clearInterval(progressInterval);

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "生成失败");

      // Build full output for content tab
      const parts = [];
      if (data.recipe) parts.push("## 📖 食谱\n\n" + data.recipe);
      if (data.cooking) parts.push("---\n## 🍳 烹饪方法\n\n" + data.cooking);
      if (data.script) parts.push("---\n## 🎙️ 口播文案\n\n" + data.script);
      if (data.storyboard) parts.push("---\n## 🎬 拍摄分镜\n\n" + data.storyboard);
      const fullOutput = parts.join("\n\n");

      App.el.outputSection.style.display = "";
      App.el.outputContent.innerHTML = App.renderMarkdown(fullOutput);
      App.el.outputContent.style.display = "";

      // Render audit result
      if (data.audit) {
        App.el.auditContent.innerHTML = App.renderMarkdown(data.audit);
        App.el.auditContent.style.display = "none";
        this._lastAudit = data.audit;
      }

      // Reset to content tab
      this._activeTab = "content";
      document.querySelectorAll(".output-tab").forEach(t => t.classList.remove("active"));
      const contentTab = document.querySelector('.output-tab[data-tab="content"]');
      if (contentTab) contentTab.classList.add("active");

      // Stage content
      App.state.staged.recipe = data.recipe || "";
      App.state.staged.cooking_method = data.cooking || "";
      App.state.staged.script = data.script || "";
      this.showStaged("staged-recipe", data.recipe || "");
      this.showStaged("staged-cooking", data.cooking || "");
      this.showStaged("staged-script", data.script || "");

      // Count audit issues for toast
      let auditSummary = "";
      if (data.audit) {
        if (data.audit.includes("✅ 通过") || data.audit.includes("✅** 通过")) {
          auditSummary = " | 审核：✅ 通过";
        } else if (data.audit.includes("❌ 违规") || data.audit.includes("❌** 违规")) {
          auditSummary = " | 审核：❌ 违规";
        } else {
          auditSummary = " | 审核：⚠️ 需修改";
        }
      }

      App.state.messages.push({ role: "user", content: `[一键生成] 食材：${ctx.ingredients || "（使用已有食谱）"} | 时长：${ctx.duration}秒` });
      App.state.messages.push({ role: "assistant", content: fullOutput });
      App.renderMessages();
      App.hideWelcome(true);
      App.saveConversation();
      if (data.recipe) this.loadDbStats();

      App.showToast(`✅ 一键生成完成！${auditSummary}`);
    } catch (e) {
      App.showToast(`❌ 生成失败：${e.message}`);
    }

    btn.disabled = false;
    btn.textContent = origText;
  },

  bindClearHistory() {
    const btn = document.getElementById("btn-clear-history");
    if (btn) {
      btn.addEventListener("click", async () => {
        if (!confirm("确定要清空推荐历史记录吗？清空后已推荐过的食材可能会再次出现。")) return;
        try {
          await fetch("/api/db/clear-history", { method: "POST" });
          App.showToast("✅ 推荐历史已清空");
          this.loadDbStats();
        } catch (e) {
          App.showToast("❌ 清空失败");
        }
      });
    }
  },

  async loadDbStats() {
    try {
      const res = await fetch("/api/db/stats");
      const data = await res.json();
      document.getElementById("db-total").textContent = data.total;
      document.getElementById("db-recent").textContent = data.recently_recommended_count;
    } catch (e) { /* ignore */ }
  },

  async runAction(action, btn) {
    App.readContext();
    const ctx = App.state.context;

    // Special: audit action
    if (action === "audit") {
      return this.runAudit(btn);
    }

    if (!ctx.weather && !ctx.ingredients && !ctx.recipe) {
      App.showToast("⚠️ 请先填写天气、食材或食谱信息");
      return;
    }

    btn.disabled = true;
    btn.classList.add("loading");
    const origText = btn.textContent;
    btn.textContent = "⏳ 生成中...";

    try {
      const userMessage = App.el.chatInput.value.trim();
      const body = {
        weather: ctx.weather,
        season: ctx.season,
        ingredients: ctx.ingredients,
        extra: ctx.extra,
        recipe: ctx.recipe || "",
        duration: ctx.duration || "60",
        user_message: userMessage,
      };

      // For downstream steps, include staged content
      if (action === "cooking" && App.state.staged.recipe) {
        body.recipe = App.state.staged.recipe;
      }
      if ((action === "script" || action === "storyboard") && App.state.staged.cooking_method) {
        body.content = App.state.staged.cooking_method;
      } else if (action === "script" || action === "storyboard") {
        body.content = App.state.staged.recipe || ctx.recipe || ctx.ingredients;
      }
      if (action === "storyboard") {
        body.script_duration = ctx.duration || "60";
      }

      const res = await fetch(`/api/generate/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "请求失败" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      const content = data.content || "";

      // Show in output
      App.el.outputSection.style.display = "";
      App.el.auditContent.style.display = "none";
      this._activeTab = "content";
      document.querySelectorAll(".output-tab").forEach(t => t.classList.remove("active"));
      const contentTab = document.querySelector('.output-tab[data-tab="content"]');
      if (contentTab) contentTab.classList.add("active");
      App.el.outputContent.style.display = "";
      App.el.outputContent.innerHTML = App.renderMarkdown(content);

      // Stage content
      this.stageContent(action, content);

      // Auto-audit for script generation
      if (action === "script" && content) {
        btn.textContent = "⏳ 审核中...";
        try {
          const auditRes = await fetch("/api/generate/audit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: content }),
          });
          const auditData = await auditRes.json();
          if (auditData.ok && auditData.content) {
            App.el.auditContent.innerHTML = App.renderMarkdown(auditData.content);
            this._lastAudit = auditData.content;
            App.showToast("✅ 口播文案已生成并完成审核");
          }
        } catch (e) { /* audit optional */ }
      }

      // Sync to chat
      const actionLabels = {
        ingredients: "养生食材推荐",
        recipe: "食谱生成",
        cooking: "烹饪方法生成",
        script: "口播文案生成",
        storyboard: "拍摄分镜生成",
        audit: "内容审核",
      };
      App.state.messages.push({
        role: "user",
        content: `[快捷操作] ${actionLabels[action]}`,
      });
      App.state.messages.push({ role: "assistant", content: content });
      App.renderMessages();
      App.hideWelcome(true);
      App.saveConversation();

      if (action === "ingredients") this.loadDbStats();
      if (action !== "script") App.showToast(`✅ ${actionLabels[action]} 完成`);
    } catch (e) {
      App.showToast(`❌ 生成失败：${e.message}`);
      console.error("快捷操作失败:", e);
    }

    btn.disabled = false;
    btn.classList.remove("loading");
    btn.textContent = origText;
  },

  async runAudit(btn) {
    const script = App.state.staged.script;
    if (!script) {
      App.showToast("⚠️ 暂无口播文案可审核，请先生成口播文案");
      return;
    }

    btn.disabled = true;
    const origText = btn.textContent;
    btn.textContent = "⏳ 审核中...";

    try {
      const res = await fetch("/api/generate/audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: script }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "审核失败");

      App.el.outputSection.style.display = "";
      App.el.auditContent.innerHTML = App.renderMarkdown(data.content);
      App.el.auditContent.style.display = "";
      App.el.outputContent.style.display = "none";
      this._activeTab = "audit";
      document.querySelectorAll(".output-tab").forEach(t => t.classList.remove("active"));
      const auditTab = document.querySelector('.output-tab[data-tab="audit"]');
      if (auditTab) auditTab.classList.add("active");
      this._lastAudit = data.content;

      App.showToast("✅ 审核完成，请查看审核结果Tab");
    } catch (e) {
      App.showToast(`❌ 审核失败：${e.message}`);
    }

    btn.disabled = false;
    btn.textContent = origText;
  },

  stageContent(action, content) {
    switch (action) {
      case "ingredients":
      case "recipe":
        App.state.staged.recipe = content;
        this.showStaged("staged-recipe", content);
        break;
      case "cooking":
        App.state.staged.cooking_method = content;
        this.showStaged("staged-cooking", content);
        break;
      case "script":
        App.state.staged.script = content;
        this.showStaged("staged-script", content);
        break;
      case "storyboard":
        break;
    }
  },

  showStaged(id, content) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.display = "";
    const preview = el.querySelector(".staged-preview");
    if (preview) {
      preview.textContent = content.replace(/[#*\n\|]/g, "").slice(0, 50) + "...";
    }
  },
};

document.addEventListener("DOMContentLoaded", () => Panels.init());
