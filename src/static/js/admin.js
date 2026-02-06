async function fetchJSON(url) {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

function renderList(id, items) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = "";
  items.forEach((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    el.appendChild(li);
  });
}

function formatPct(value) {
  if (value === null || value === undefined) return "n/a";
  return `${Math.round(value * 100)}%`;
}

async function loadAdmin() {
  try {
    const [adoption, tickets, integrations, billing, security, agentHealth, dspyEval, triageLabels, blogMetrics] = await Promise.all([
      fetchJSON("/api/v1/admin/adoption"),
      fetchJSON("/api/v1/admin/tickets"),
      fetchJSON("/api/v1/admin/integrations"),
      fetchJSON("/api/v1/admin/billing"),
      fetchJSON("/api/v1/admin/security"),
      fetchJSON("/api/v1/admin/agent-health"),
      fetchJSON("/api/v1/admin/dspy-eval?limit=50"),
      fetchJSON("/api/v1/admin/triage-labels").catch(() => ({ config: { labels: {} } })),
      fetchJSON("/api/v1/admin/blog-metrics"),
    ]);
    renderList("adoption", [
      `Active accounts: ${adoption.active_accounts || 0}`,
      `Inbox connected: ${adoption.connected_accounts || 0}`,
      `Active users (24h/7d): ${adoption.active_users_24h || 0} / ${adoption.active_users_7d || 0}`,
      `Signups in window: ${(adoption.daily_signups || []).reduce((a, b) => a + (b.count || 0), 0)}`,
    ]);
    renderList("tickets", [
      `Total backlog: ${(tickets.backlog_by_status || []).reduce((a, b) => a + (b.count || 0), 0)}`,
      `By status: ${(tickets.backlog_by_status || []).map((x) => `${x.status}:${x.count}`).join(", ") || "n/a"}`,
      `By category: ${(tickets.by_category || []).map((x) => `${x.category}:${x.count}`).join(", ") || "n/a"}`,
      `By priority: ${(tickets.by_priority || []).map((x) => `${x.priority}:${x.count}`).join(", ") || "n/a"}`,
    ]);
    renderList("integrations", [
      `Providers: ${(integrations.providers || []).map((p) => `${p.provider}:${p.count}`).join(", ") || "none"}`,
      `Accounts with polls: ${(integrations.last_polls || []).length}`,
      `Recent errors: ${(integrations.errors || []).length}`,
    ]);
    renderList("billing", [
      `Plan mix entries: ${(billing.plan_mix || []).length || 0}`,
      `Trials expiring: ${(billing.trials_expiring || []).length || 0}`,
      `Failed payments: ${(billing.failed_payments || []).length || 0}`,
    ]);
    renderList("security", [
      `Users total: ${security.users_total || 0}`,
      `Failed logins: ${security.failed_logins || 0}`,
      `Password resets: ${security.password_resets || 0}`,
      `JWT refresh failures: ${security.jwt_refresh_failures || 0}`,
    ]);
    renderList("agentHealth", [
      `Invokes: ${agentHealth.invokes || 0}`,
      `Successes: ${agentHealth.successes || 0}`,
      `Errors: ${agentHealth.errors || 0}`,
      `Retries: ${agentHealth.retries || 0}`,
      `Timeouts: ${agentHealth.timeouts || 0}`,
      `Avg latency: ${agentHealth.avg_latency_ms ? `${Math.round(agentHealth.avg_latency_ms)} ms` : "n/a"}`,
    ]);
    renderList("dspyEval", [
      `Category acc: ${formatPct(dspyEval.metrics?.category_acc)}`,
      `Priority acc: ${formatPct(dspyEval.metrics?.priority_acc)}`,
      `Sentiment acc: ${formatPct(dspyEval.metrics?.sentiment_acc)}`,
      `Intent acc: ${formatPct(dspyEval.metrics?.intent_acc)}`,
      `Action required acc: ${formatPct(dspyEval.metrics?.action_required_acc)}`,
      `Sample size: ${dspyEval.limit ?? "n/a"}`,
    ]);
    const labelsInput = document.getElementById("triageLabelsInput");
    if (labelsInput) {
      labelsInput.value = JSON.stringify(triageLabels.config?.labels || {}, null, 2);
    }
    renderList("blogMetrics", [
      `Published posts: ${blogMetrics.published_posts ?? 0}/${blogMetrics.total_posts ?? 0}`,
      `Avg word count: ${blogMetrics.avg_word_count ? Math.round(blogMetrics.avg_word_count) : "n/a"}`,
      `Avg read time: ${
        blogMetrics.avg_read_time_minutes ? `${Math.round(blogMetrics.avg_read_time_minutes)} min` : "n/a"
      }`,
      `Impressions (GSC): ${blogMetrics.impressions ?? "n/a"}`,
      `Clicks (GSC): ${blogMetrics.clicks ?? "n/a"}`,
    ]);
  } catch (err) {
    console.error("Admin load failed", err);
    renderList("adoption", [`Error: ${err.message}`]);
  }
}

async function inviteTestimonial(evt) {
  evt.preventDefault();
  const accountId = document.getElementById("testimonialAccount").value;
  const userId = document.getElementById("testimonialUser").value;
  const toEmail = document.getElementById("testimonialEmail")?.value || "";
  const sendEmail = !!toEmail;
  const resultEl = document.getElementById("testimonialResult");
  resultEl.textContent = "Generating...";
  try {
    const getCookie = (name) =>
      document.cookie
        .split(";")
        .map((c) => c.trim())
        .find((c) => c.startsWith(name + "="))
        ?.split("=")[1];
    const csrf = getCookie("csrf_access_token") || getCookie("csrf_refresh_token");

    const res = await fetch("/api/v1/admin/actions/invite-testimonial", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRF-TOKEN": csrf } : {})
      },
      credentials: "include",
      body: JSON.stringify({ account_id: accountId || null, user_id: userId || null, to_email: toEmail || null, send_email: sendEmail }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Request failed");
    resultEl.textContent = `Invite link: ${data.link}`;
  } catch (err) {
    resultEl.textContent = `Error: ${err.message}`;
  }
}

document.addEventListener("DOMContentLoaded", loadAdmin);
document.getElementById("testimonialForm")?.addEventListener("submit", inviteTestimonial);
document.getElementById("exportFeedbackBtn")?.addEventListener("click", async () => {
  const statusEl = document.getElementById("exportStatus");
  if (statusEl) {
    statusEl.classList.remove("hidden");
    statusEl.textContent = "Exporting...";
  }
  try {
    const res = await fetch("/api/v1/inboxiq/feedback/export", { credentials: "include" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Export failed");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `inboxiq_feedback_export_${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    if (statusEl) statusEl.textContent = `Exported ${data.count || 0} records.`;
  } catch (err) {
    if (statusEl) statusEl.textContent = `Error: ${err.message}`;
  }
});
document.getElementById("refreshEmbeddingsBtn")?.addEventListener("click", async () => {
  const statusEl = document.getElementById("refreshStatus");
  if (statusEl) {
    statusEl.classList.remove("hidden");
    statusEl.textContent = "Refreshing embeddings...";
  }
  try {
    const getCookie = (name) =>
      document.cookie
        .split(";")
        .map((c) => c.trim())
        .find((c) => c.startsWith(name + "="))
        ?.split("=")[1];
    const csrf = getCookie("csrf_access_token") || getCookie("csrf_refresh_token");

    const res = await fetch("/api/v1/admin/actions/refresh-embeddings", {
      method: "POST",
      headers: csrf ? { "X-CSRF-TOKEN": csrf } : {},
      credentials: "include",
    });
    const contentType = res.headers.get("content-type") || "";
    let data = {};
    if (contentType.includes("application/json")) {
      data = await res.json();
    } else {
      const text = await res.text();
      throw new Error(text || `HTTP ${res.status}`);
    }
    if (!res.ok) throw new Error(data.error || data.message || `HTTP ${res.status}`);
    if (statusEl) statusEl.textContent = data.message || "Refreshed embeddings";
  } catch (err) {
    if (statusEl) statusEl.textContent = `Error: ${err.message}`;
  }
});

document.getElementById("saveTriageLabelsBtn")?.addEventListener("click", async () => {
  const input = document.getElementById("triageLabelsInput");
  const statusEl = document.getElementById("triageLabelsStatus");
  if (!input) return;
  if (statusEl) {
    statusEl.classList.remove("hidden");
    statusEl.textContent = "Saving...";
  }
  let labels = null;
  try {
    labels = JSON.parse(input.value || "{}");
  } catch (err) {
    if (statusEl) statusEl.textContent = "Invalid JSON.";
    return;
  }
  try {
    const getCookie = (name) =>
      document.cookie
        .split(";")
        .map((c) => c.trim())
        .find((c) => c.startsWith(name + "="))
        ?.split("=")[1];
    const csrf = getCookie("csrf_access_token") || getCookie("csrf_refresh_token");

    const res = await fetch("/api/v1/admin/triage-labels", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRF-TOKEN": csrf } : {})
      },
      credentials: "include",
      body: JSON.stringify({ labels }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Save failed");
    if (statusEl) statusEl.textContent = "Saved.";
  } catch (err) {
    if (statusEl) statusEl.textContent = `Error: ${err.message}`;
  }
});

// Simple user menu toggle
(function () {
  const btn = document.getElementById("userMenuBtn");
  const menu = document.getElementById("userMenu");
  if (!btn || !menu) return;
  btn.addEventListener("click", () => {
    menu.classList.toggle("hidden");
  });
  document.addEventListener("click", (e) => {
    if (menu.classList.contains("hidden")) return;
    if (!menu.contains(e.target) && !btn.contains(e.target)) {
      menu.classList.add("hidden");
    }
  });
})();

// Logout with CSRF for cookie-based JWT
(function () {
  const logoutForm = document.getElementById("logoutForm");
  if (!logoutForm) return;
  logoutForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const getCookie = (name) =>
      document.cookie
        .split(";")
        .map((c) => c.trim())
        .find((c) => c.startsWith(name + "="))
        ?.split("=")[1];
    const csrf = getCookie("csrf_access_token") || getCookie("csrf_refresh_token");
    try {
      await fetch("/auth/logout", {
        method: "POST",
        credentials: "include",
        headers: csrf ? { "X-CSRF-TOKEN": csrf } : {},
      });
    } finally {
      window.location.href = "/login";
    }
  });
})();

// Content Generation: Load published posts
async function loadPublishedPosts() {
  const container = document.getElementById("publishedPosts");
  if (!container) return;

  container.innerHTML = '<div class="text-slate-400 text-sm">Loading...</div>';

  try {
    const data = await fetchJSON("/api/v1/admin/content/published-posts?limit=10");

    if (!data.posts || data.posts.length === 0) {
      container.innerHTML = '<div class="text-slate-400 text-sm">No published posts yet. Generate your first blog post!</div>';
      return;
    }

    container.innerHTML = data.posts.map(post => {
      const qualityBadge = post.dspy_quality_score
        ? `<span class="text-xs px-2 py-0.5 rounded ${post.dspy_quality_score >= 0.8 ? 'bg-green-500/20 text-green-400' : post.dspy_quality_score >= 0.6 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400'}">
             Quality: ${Math.round(post.dspy_quality_score * 100)}%
           </span>`
        : '';

      const autoBadge = post.auto_generated
        ? '<span class="text-xs px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-400">🤖 Auto-generated</span>'
        : '';

      return `
        <div class="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
          <div class="flex items-start justify-between">
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-1">
                <h3 class="text-sm font-semibold text-slate-100">${post.title || 'Untitled'}</h3>
                ${autoBadge}
                ${qualityBadge}
              </div>
              <div class="text-xs text-slate-400 space-y-0.5">
                <div>Slug: <span class="text-slate-300">${post.slug || 'N/A'}</span></div>
                <div>Published: <span class="text-slate-300">${post.published_at ? new Date(post.published_at).toLocaleString() : 'N/A'}</span></div>
                <div>Words: <span class="text-slate-300">${post.word_count || 0}</span> | Stage: <span class="text-slate-300">${post.funnel_stage || 'N/A'}</span> | Keyword: <span class="text-slate-300">${post.primary_keyword || 'N/A'}</span></div>
              </div>
            </div>
            <div class="flex gap-2 ml-3">
              <a href="/blog/${post.slug}" target="_blank" class="text-xs px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200">View</a>
              <a href="/api/v1/publishing/blogs/${post.id}" target="_blank" class="text-xs px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200">JSON</a>
            </div>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    container.innerHTML = `<div class="text-red-400 text-sm">Error loading posts: ${err.message}</div>`;
  }
}

// Content Generation: Manual trigger
document.getElementById("generateBlogBtn")?.addEventListener("click", async function() {
  const btn = this;
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Generating...";

  try {
    // Get CSRF token from cookies
    const getCookie = (name) =>
      document.cookie
        .split(";")
        .map((c) => c.trim())
        .find((c) => c.startsWith(name + "="))
        ?.split("=")[1];
    const csrf = getCookie("csrf_access_token") || getCookie("csrf_refresh_token");

    const res = await fetch("/api/v1/admin/content/generate-blog", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRF-TOKEN": csrf } : {})
      },
      credentials: "include",
      body: JSON.stringify({
        auto_publish: true
      })
    });

    const data = await res.json();

    if (!res.ok) throw new Error(data.error || data.message || "Generation failed");

    btn.textContent = "✓ Queued!";
    setTimeout(() => {
      btn.textContent = originalText;
      btn.disabled = false;
    }, 3000);

    // Refresh blog metrics and published posts after 30 seconds
    setTimeout(() => {
      loadAdmin();
      loadPublishedPosts();
    }, 30000);

    alert(`Blog generation queued!\n\nTask ID: ${data.task_id}\n\nThe blog post will be generated, auto-published, and you'll receive an email at support@kalevent.com for review.\n\nCheck back in ~2-3 minutes to see the published post.`);

  } catch (err) {
    btn.textContent = originalText;
    btn.disabled = false;
    alert(`Error: ${err.message}`);
  }
});

// Content Generation: Refresh published posts
document.getElementById("refreshPublishedBtn")?.addEventListener("click", loadPublishedPosts);

// Load published posts on page load (when content section is active)
document.addEventListener("DOMContentLoaded", () => {
  // Load immediately if content section is visible
  const contentSection = document.getElementById("section-content");
  if (contentSection && contentSection.classList.contains("active")) {
    loadPublishedPosts();
  }

  // Also load when user navigates to content section
  document.querySelectorAll('.sidebar-nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const section = item.getAttribute('data-section');
      if (section === 'content') {
        loadPublishedPosts();
      }
    });
  });
});
