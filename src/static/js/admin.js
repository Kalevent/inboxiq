async function fetchJSON(url) {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

function escHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
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
            <div class="flex gap-2 ml-3 flex-wrap justify-end">
              <a href="/blog/${post.slug}" target="_blank" class="text-xs px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200">View</a>
              <a href="/api/v1/publishing/blogs/${post.id}" target="_blank" class="text-xs px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200">JSON</a>
              <button onclick="distributePost('${post.id}', this)" class="text-xs px-2 py-1 rounded ${post.distributed_at ? 'bg-green-700/40 text-green-300' : 'bg-indigo-600 hover:bg-indigo-500 text-white'}">${post.distributed_at ? '✓ Distributed' : 'Distribute'}</button>
              <button onclick="deletePublishedPost('${post.id}', '${post.slug}')" class="text-xs px-2 py-1 rounded bg-rose-700/60 hover:bg-rose-600 text-rose-200">Delete</button>
            </div>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    container.innerHTML = `<div class="text-red-400 text-sm">Error loading posts: ${err.message}</div>`;
  }
}

async function distributePost(postId, btn) {
  btn.disabled = true;
  btn.textContent = 'Distributing…';
  try {
    const csrf = (document.cookie.match(/csrf_access_token=([^;]+)/) || [])[1] || '';
    const resp = await fetch(`/publishing/blog/${postId}/distribute`, {
      method: 'POST',
      headers: { 'X-CSRF-TOKEN': decodeURIComponent(csrf) },
      credentials: 'include',
    });
    if (resp.ok) {
      btn.textContent = '✓ Distributed';
      btn.className = btn.className.replace('bg-indigo-600 hover:bg-indigo-500 text-white', 'bg-green-700/40 text-green-300');
    } else {
      const err = await resp.json().catch(() => ({}));
      alert('Distribute failed: ' + (err.error || resp.status));
      btn.textContent = 'Distribute';
      btn.disabled = false;
    }
  } catch (e) {
    alert('Distribute failed: ' + e.message);
    btn.textContent = 'Distribute';
    btn.disabled = false;
  }
}

async function deletePublishedPost(postId, slug) {
  if (!confirm(`Delete "${slug}"?\n\nThis removes it from the database and the public blog. This cannot be undone.`)) return;
  try {
    const csrf = (document.cookie.match(/csrf_access_token=([^;]+)/) || [])[1] || '';
    const resp = await fetch(`/api/v1/admin/content/published-posts/${postId}`, {
      method: 'DELETE',
      headers: { 'X-CSRF-TOKEN': decodeURIComponent(csrf) },
    });
    if (resp.ok) {
      loadPublishedPosts();
    } else {
      const err = await resp.json().catch(() => ({}));
      alert('Delete failed: ' + (err.error || resp.status));
    }
  } catch (e) {
    alert('Delete failed: ' + e.message);
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

// ── Inbox Tools: DSPy Training Metrics ───────────────────────────────────────
(function () {
  const getCookie = (name) =>
    document.cookie.split(';').map((s) => s.trim()).find((c) => c.startsWith(name + '='))?.split('=')[1];

  const runTrainingBtn     = document.getElementById('runTrainingBtn');
  const runTrainingBtnText = document.getElementById('runTrainingBtnText');
  const runTrainingSpinner = document.getElementById('runTrainingSpinner');
  const trainingReadiness  = document.getElementById('trainingReadiness');
  const trainingStatus     = document.getElementById('trainingStatus');
  const trainingLastRun    = document.getElementById('trainingLastRun');
  const trainingProvider   = document.getElementById('trainingProvider');
  const trainingModel      = document.getElementById('trainingModel');
  const trainingSamples    = document.getElementById('trainingSamples');
  const trainingTrainAcc   = document.getElementById('trainingTrainAcc');
  const trainingEvalAcc    = document.getElementById('trainingEvalAcc');
  const trainingTable      = document.getElementById('trainingTable');
  let trainingLoaded = false;

  const setTrainingStatus = function(kind, msg) {
    if (!trainingStatus) return;
    const map = {
      success: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
      error:   'border-rose-400/40 bg-rose-500/10 text-rose-100',
      info:    'border-indigo-400/40 bg-indigo-500/10 text-indigo-100',
    };
    trainingStatus.className = `text-xs rounded-xl px-3 py-2 border ${map[kind] || map.info}`;
    trainingStatus.textContent = msg;
    trainingStatus.classList.remove('hidden');
  };

  const renderTrainingTable = function(rows = []) {
    if (!trainingTable) return;
    if (!rows.length) {
      trainingTable.innerHTML = '<div class="px-4 py-3 text-slate-400">No training runs yet.</div>';
      return;
    }
    trainingTable.innerHTML = rows.map((row) => {
      const created  = row.created_at ? new Date(row.created_at).toLocaleString() : '—';
      const trainAcc = row.train_accuracy != null ? `${Math.round(row.train_accuracy * 100)}%` : '—';
      const evalAcc  = row.eval_accuracy  != null ? `${Math.round(row.eval_accuracy  * 100)}%` : '—';
      return `<div class="px-4 py-3 grid grid-cols-1 md:grid-cols-6 gap-2">
        <div class="text-slate-200">${created}</div>
        <div>Provider: <span class="text-slate-200">${row.provider || '—'}</span></div>
        <div>Model: <span class="text-slate-200">${row.model_id || '—'}</span></div>
        <div>Samples: <span class="text-slate-200">${row.sample_count ?? 0}</span></div>
        <div>Train: <span class="text-slate-200">${trainAcc}</span></div>
        <div>Eval: <span class="text-slate-200">${evalAcc}</span></div>
      </div>`;
    }).join('');
  };

  window.loadTrainingMetrics = async function () {
    if (trainingLoaded || !trainingTable) return;
    try {
      const resp = await fetch('/api/v1/inboxiq/training-metrics', { credentials: 'include' });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Unable to load training metrics');
      const latest = data.latest || {};
      if (trainingLastRun)  trainingLastRun.textContent  = latest.created_at ? new Date(latest.created_at).toLocaleString() : '—';
      if (trainingProvider) trainingProvider.textContent = latest.provider  || '—';
      if (trainingModel)    trainingModel.textContent    = latest.model_id  || '—';
      if (trainingSamples)  trainingSamples.textContent  = latest.sample_count ?? '—';
      if (trainingTrainAcc) trainingTrainAcc.textContent = latest.train_accuracy != null ? `${Math.round(latest.train_accuracy * 100)}%` : '—';
      if (trainingEvalAcc)  trainingEvalAcc.textContent  = latest.eval_accuracy  != null ? `${Math.round(latest.eval_accuracy  * 100)}%` : '—';
      renderTrainingTable(data.metrics || []);
      trainingLoaded = true;
    } catch (err) {
      setTrainingStatus('error', err.message || 'Failed to load training metrics.');
    }
  };

  window.loadTrainingStatus = async function () {
    if (!runTrainingBtn) return;
    try {
      const resp = await fetch('/api/v1/inboxiq/training/status', { credentials: 'include' });
      const data = await resp.json();
      if (!resp.ok) {
        runTrainingBtn.disabled = true;
        if (trainingReadiness) trainingReadiness.textContent = 'Unable to check status';
        return;
      }
      if (data.can_train) {
        runTrainingBtn.disabled = false;
        if (trainingReadiness) {
          trainingReadiness.textContent = `${data.override_count} overrides + ${data.seed_count} seeds ready`;
          trainingReadiness.className = 'text-xs text-emerald-400';
        }
      } else {
        runTrainingBtn.disabled = true;
        if (trainingReadiness) {
          trainingReadiness.textContent = `Need ${data.samples_needed} more samples (${data.override_count}/${data.min_samples})`;
          trainingReadiness.className = 'text-xs text-amber-400';
        }
      }
    } catch (err) {
      if (runTrainingBtn) runTrainingBtn.disabled = true;
      if (trainingReadiness) trainingReadiness.textContent = 'Status unavailable';
    }
  };

  const triggerTraining = async function() {
    if (!runTrainingBtn) return;
    runTrainingBtn.disabled = true;
    if (runTrainingBtnText) runTrainingBtnText.textContent = 'Queuing...';
    if (runTrainingSpinner) runTrainingSpinner.classList.remove('hidden');
    try {
      const csrf = getCookie('csrf_access_token');
      const resp = await fetch('/api/v1/inboxiq/training/trigger', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrf ? decodeURIComponent(csrf) : '' },
      });
      const data = await resp.json();
      if (resp.ok) {
        setTrainingStatus('success', data.message || 'Training queued successfully');
        if (runTrainingBtnText) runTrainingBtnText.textContent = 'Queued!';
        setTimeout(() => {
          if (runTrainingBtnText) runTrainingBtnText.textContent = 'Run Training';
          window.loadTrainingStatus();
        }, 3000);
      } else {
        setTrainingStatus('error', data.message || 'Failed to queue training');
        if (runTrainingBtnText) runTrainingBtnText.textContent = 'Run Training';
        runTrainingBtn.disabled = false;
      }
    } catch (err) {
      setTrainingStatus('error', 'Network error. Please try again.');
      if (runTrainingBtnText) runTrainingBtnText.textContent = 'Run Training';
      if (runTrainingBtn) runTrainingBtn.disabled = false;
    } finally {
      if (runTrainingSpinner) runTrainingSpinner.classList.add('hidden');
    }
  };

  if (runTrainingBtn) runTrainingBtn.addEventListener('click', triggerTraining);
})();

// ── Inbox Tools: Decision Search ──────────────────────────────────────────────
(function () {
  const searchForm   = document.getElementById('ticketSearchForm');
  const qInput       = document.getElementById('ticketSearchQuery');
  const statusInput  = document.getElementById('ticketStatus');
  const categoryInput= document.getElementById('ticketCategory');
  const priorityInput= document.getElementById('ticketPriority');
  const afterInput   = document.getElementById('ticketAfter');
  const beforeInput  = document.getElementById('ticketBefore');
  const ticketResults= document.getElementById('ticketResults');
  const ticketStatus = document.getElementById('ticketSearchStatus');

  if (!searchForm) return;

  const setTicketStatus = function(kind, msg) {
    if (!ticketStatus) return;
    const map = {
      success: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
      error:   'border-rose-400/40 bg-rose-500/10 text-rose-100',
      info:    'border-indigo-400/40 bg-indigo-500/10 text-indigo-100',
    };
    ticketStatus.className = `text-xs rounded-xl px-3 py-2 border ${map[kind] || map.info}`;
    ticketStatus.textContent = msg;
    ticketStatus.classList.remove('hidden');
  };

  const renderTicketCards = function(items) {
    if (!ticketResults) return;
    ticketResults.innerHTML = '';
    if (!items || !items.length) {
      ticketResults.innerHTML = '<div class="rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-300">No decisions found.</div>';
      return;
    }
    items.forEach((t) => {
      const created = t.created_at ? new Date(t.created_at).toLocaleString() : '';
      const card = document.createElement('div');
      card.className = 'rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200';
      const safeUrl = t.provider_thread_url && /^https?:\/\//.test(t.provider_thread_url) ? escHtml(t.provider_thread_url) : null;
      card.innerHTML = `
        <div class="flex items-center justify-between mb-1">
          <span class="font-semibold text-slate-100">${escHtml(t.subject) || 'Decision'}</span>
          <span class="text-[11px] text-slate-400">${escHtml(created)}</span>
        </div>
        <div class="grid grid-cols-2 gap-2 text-[11px]">
          <div><span class="text-slate-400">Category:</span> ${escHtml(t.category) || '—'}</div>
          <div><span class="text-slate-400">Priority:</span> ${escHtml(t.priority) || '—'}</div>
          <div><span class="text-slate-400">Status:</span> ${escHtml(t.status) || '—'}</div>
          <div><span class="text-slate-400">Channel:</span> ${escHtml(t.channel) || 'email'}</div>
        </div>
        ${t.ai_reason ? `<div class="text-[11px] text-slate-400 mt-1">Why: ${escHtml(t.ai_reason)}</div>` : ''}
        ${safeUrl ? `<a class="text-indigo-300 hover:text-indigo-200 text-[11px] mt-1 inline-block" href="${safeUrl}" target="_blank" rel="noreferrer">Open source →</a>` : ''}
      `;
      ticketResults.appendChild(card);
    });
  };

  const performTicketSearch = async function(event) {
    if (event) event.preventDefault();
    const params = new URLSearchParams();
    params.set('page_size', '20');
    if (qInput?.value)        params.set('q',             qInput.value.trim());
    if (statusInput?.value)   params.set('status',        statusInput.value);
    if (categoryInput?.value) params.set('category',      categoryInput.value);
    if (priorityInput?.value) params.set('priority',      priorityInput.value);
    if (afterInput?.value)    params.set('created_after', afterInput.value);
    if (beforeInput?.value)   params.set('created_before',beforeInput.value);
    setTicketStatus('info', 'Searching…');
    try {
      const resp = await fetch(`/api/v1/inboxiq/tickets?${params.toString()}`, { credentials: 'include' });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Failed to load decisions');
      renderTicketCards(data.tickets || []);
      setTicketStatus('success', `${data.tickets ? data.tickets.length : 0} result(s)`);
    } catch (err) {
      setTicketStatus('error', err.message || 'Search failed');
    }
  };

  searchForm.addEventListener('submit', performTicketSearch);
})();
