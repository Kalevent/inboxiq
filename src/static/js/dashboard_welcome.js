(() => {
  const sendBtn = document.getElementById('sendTestEmailBtn');
  const statusEl = document.getElementById('testEmailStatus');
  const emailInput = document.getElementById('testEmailInput');
  const triageResults = document.getElementById('triageResults');
  const triageList = document.getElementById('triageList');
  const connectGmailBtn = document.getElementById('connectGmailBtn');
  const connectOutlookBtn = document.getElementById('connectOutlookBtn');
  const connectStatus = document.getElementById('connectStatus');
  const rawConnectionId = connectStatus?.dataset?.connectionId;
  const normalizedConnectionId = (rawConnectionId || '').trim();
  const hasConnectionId = normalizedConnectionId && !['none', 'null', 'undefined'].includes(normalizedConnectionId.toLowerCase());
  const getConnectionId = () => (hasConnectionId ? normalizedConnectionId : '');
  const pollNowBtn = document.getElementById('pollNowBtn');
  const pollStatus = document.getElementById('pollStatus');
  const lastPollLine = document.getElementById('lastPollLine');

  const getCookie = (name) => {
    return document.cookie
      .split(';')
      .map((c) => c.trim())
      .find((c) => c.startsWith(name + '='))?.split('=')[1];
  };

  function setStatus(type, message) {
    if (!statusEl) return;
    const map = {
      success: 'border-emerald-400/50 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400/50 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400/50 bg-indigo-500/10 text-indigo-100',
    };
    statusEl.className = `mt-3 text-xs rounded-xl border px-3 py-2 ${map[type] || map.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove('hidden');
  }

  async function handleSend() {
    if (!sendBtn) return;
    const toEmail = (emailInput?.value || '').trim();
    if (!toEmail) {
      setStatus('error', 'Please enter a destination email.');
      return;
    }
    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending...';
    setStatus('info', `Sending a test email to ${toEmail}...`);
    try {
      const response = await fetch('/api/test-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to_email: toEmail }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Unable to send test email.');
      }
      setStatus('success', data.message || 'Test email sent.');
      if (Array.isArray(data.triage)) {
        renderTriage(data.triage);
      }
    } catch (err) {
      setStatus('error', err.message || 'Failed to send test email.');
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = 'Send test email →';
    }
  }

  function renderTriage(items) {
    if (!triageResults || !triageList) return;
    triageList.innerHTML = '';
    items.forEach((item) => {
      const card = document.createElement('div');
      card.className = 'rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200';
      card.innerHTML = `
        <div class="flex items-center justify-between mb-1">
          <span class="font-semibold text-slate-100">${item.subject || 'Email'}</span>
          <span class="text-[11px] text-slate-400">${item.created_at ? new Date(item.created_at).toLocaleString() : ''}</span>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div><span class="text-slate-400">Category:</span> ${item.category || '-'}</div>
          <div><span class="text-slate-400">Priority:</span> ${item.priority || '-'}</div>
          <div><span class="text-slate-400">Sentiment:</span> ${item.sentiment || '-'}</div>
          <div><span class="text-slate-400">Ticket:</span> ${item.ticket || '-'}</div>
        </div>
      `;
      triageList.appendChild(card);
    });
    triageResults.classList.remove('hidden');
  }

  if (sendBtn) {
    sendBtn.addEventListener('click', handleSend);
  }

  // Auto-refresh recent triage every 10 seconds
  let refreshInterval = null;

  async function refreshTickets() {
    try {
      const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const resp = await fetch('/api/v1/inboxiq/tickets?page_size=5', {
        headers,
        credentials: 'include',
      });
      const data = await resp.json();
      if (resp.ok && data.tickets) {
        renderTriage(data.tickets);
      } else if (resp.status === 401) {
        setStatus('error', 'Please sign in to view live triage.');
        if (refreshInterval) {
          clearInterval(refreshInterval);
          refreshInterval = null;
        }
      }
    } catch (err) {
      // silent
    }
  }
  refreshInterval = setInterval(refreshTickets, 10000);
  refreshTickets();

  async function startConnect(provider) {
    const url = provider === 'gmail' ? '/api/v1/auth/google/start' : '/api/v1/auth/outlook/start';
    connectStatus.textContent = `Connecting to ${provider}...`;
    window.location = url;
  }

  // One-time poll trigger when a connection exists
  async function pollInboxOnce() {
    const connectionId = getConnectionId();
    if (!connectionId) return;
    try {
      const csrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
      const resp = await fetch(`/api/v1/inboxiq/poll/${connectionId}`, {
        method: 'POST',
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-TOKEN': csrf } : {},
      });
      const data = await resp.json();
      if (resp.ok) {
        connectStatus.textContent = `Polled inbox: ${data.summary.created} new, ${data.summary.duplicates} duplicates, ${data.summary.errors} errors.`;
      } else {
        connectStatus.textContent = data.error || `Polling failed (HTTP ${resp.status})`;
      }
    } catch (err) {
      connectStatus.textContent = 'Connected — polling in the background.';
    }
  }
  pollInboxOnce();

  // Refresh last poll info from server metadata
  async function refreshLastPoll() {
    if (!lastPollLine) return;
    try {
      const resp = await fetch('/api/v1/inboxiq/connections/mine', { credentials: 'include' });
      const data = await resp.json();
      if (!resp.ok) return;
      const lp = data.last_poll || {};
      const health = data.poll_health || {};
      if (lp.last_poll_at) {
        let text = `Last poll: ${lp.last_poll_at}`;
        if (lp.last_poll_status) text += ` (${lp.last_poll_status})`;
        if (lp.last_poll_error) text += ` • Error: ${lp.last_poll_error}`;
        lastPollLine.textContent = text;
      } else if (lp.last_poll_status && lp.last_poll_status !== 'never') {
        let text = `Last poll: ${lp.last_poll_status}`;
        if (lp.last_poll_error) text += ` • Error: ${lp.last_poll_error}`;
        lastPollLine.textContent = text;
      }
      const badge = document.getElementById('pollHealthBadge');
      if (badge) {
        const status = health.status || 'unknown';
        badge.textContent = status === 'ok' ? 'healthy' : status;
        badge.className = 'text-slate-400';
        if (status === 'ok') badge.className = 'text-emerald-300';
        else if (status === 'stale') badge.className = 'text-amber-300';
        else if (status === 'error') badge.className = 'text-rose-300';
      }
    } catch (err) {
      // silent
    }
  }
  refreshLastPoll();

  if (pollNowBtn) {
    pollNowBtn.addEventListener('click', async () => {
      if (pollStatus) {
        pollStatus.classList.remove('hidden');
        pollStatus.textContent = 'Polling inbox...';
      }
      const connectionId = getConnectionId();
      try {
        const csrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
        if (!connectionId || !connectionId.trim()) {
          if (pollStatus) pollStatus.textContent = 'No connected inbox id found.';
          return;
        }
        const resp = await fetch(`/api/v1/inboxiq/poll/${connectionId}`, {
          method: 'POST',
          credentials: 'include',
          headers: csrf ? { 'X-CSRF-TOKEN': csrf } : {},
        });
        const contentType = resp.headers.get('content-type') || '';
        const data = contentType.includes('application/json') ? await resp.json() : {};
        if (!resp.ok) {
          const msg = data.error || data.message || `HTTP ${resp.status}`;
          if (pollStatus) pollStatus.textContent = `Error: ${msg}${resp.status === 401 ? ' (please log in again)' : ''}`;
        } else {
          if (pollStatus) pollStatus.textContent = 'Poll triggered. Refreshing...';
          window.location.reload();
        }
      } catch (err) {
        if (pollStatus) pollStatus.textContent = `Error: ${err.message}`;
      }
    });
  }

  // Ticket search + filters
  const searchForm = document.getElementById('ticketSearchForm');
  const qInput = document.getElementById('ticketSearchQuery');
  const statusInput = document.getElementById('ticketStatus');
  const categoryInput = document.getElementById('ticketCategory');
  const priorityInput = document.getElementById('ticketPriority');
  const afterInput = document.getElementById('ticketAfter');
  const beforeInput = document.getElementById('ticketBefore');
  const ticketResults = document.getElementById('ticketResults');
  const ticketStatus = document.getElementById('ticketSearchStatus');
  const testimonialMsg = document.getElementById('testimonialMessage');
  const testimonialRating = document.getElementById('testimonialRating');
  const testimonialConsent = document.getElementById('testimonialConsent');
  const testimonialStatus = document.getElementById('testimonialStatus');
  const submitTestimonialBtn = document.getElementById('submitTestimonialBtn');
  const actionSearchInput = document.getElementById('actionSearchInput');
  const actionPriorityFilter = document.getElementById('actionPriorityFilter');
  let actionCards = Array.from(document.querySelectorAll('.action-card'));
  const actionCountSpan = document.getElementById('actionRequiredCount');
  const impactScope = document.getElementById('impactScope');
  const showActionOnlyToggle = document.getElementById('showActionOnly');
  const actionOnlyHint = document.getElementById('actionOnlyHint');
  const actionRequiredList = document.getElementById('actionRequiredList');
  const optionalList = document.getElementById('optionalList');
  const autoHandledEmailList = document.getElementById('autoHandledEmailList');
  const autoHandledFeedbackList = document.getElementById('autoHandledFeedbackList');
  const metricActionRequired = document.getElementById('metricActionRequired');
  const metricOptional = document.getElementById('metricOptional');
  const metricAutoHandledEmail = document.getElementById('metricAutoHandledEmail');
  const metricAutoHandledOther = document.getElementById('metricAutoHandledOther');
  const metricActionable = document.getElementById('metricActionable');
  const metricAutoHandled = document.getElementById('metricAutoHandled');
  const metricEliminated = document.getElementById('metricEliminated');
  const metricMissed = document.getElementById('metricMissed');

  function setTicketStatus(kind, msg) {
    if (!ticketStatus) return;
    const map = {
      success: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400/40 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400/40 bg-indigo-500/10 text-indigo-100',
    };
    ticketStatus.className = `text-xs rounded-xl px-3 py-2 border ${map[kind] || map.info}`;
    ticketStatus.textContent = msg;
    ticketStatus.classList.remove('hidden');
  }

  function applyActionFilters() {
    loadDashboardData();
  }

  function updateActionOnlyHint() {
    if (!actionOnlyHint || !showActionOnlyToggle) return;
    actionOnlyHint.classList.toggle('hidden', !showActionOnlyToggle.checked);
  }

  if (actionSearchInput) {
    actionSearchInput.addEventListener('input', () => {
      applyActionFilters();
    });
  }
  if (actionPriorityFilter) {
    actionPriorityFilter.addEventListener('change', applyActionFilters);
  }
  if (impactScope) {
    impactScope.addEventListener('change', loadDashboardData);
  }
  if (showActionOnlyToggle) {
    showActionOnlyToggle.addEventListener('change', () => {
      updateActionOnlyHint();
      loadDashboardData();
    });
  }

  function updateMetrics(counts = {}) {
    if (metricActionRequired) metricActionRequired.textContent = counts.action_required ?? 0;
    if (metricOptional) metricOptional.textContent = counts.optional ?? 0;
    if (metricAutoHandledEmail) metricAutoHandledEmail.textContent = counts.auto_handled_email ?? 0;
    if (metricAutoHandledOther) metricAutoHandledOther.textContent = counts.auto_handled_other ?? 0;
    if (metricActionable) metricActionable.textContent = counts.actionable_surfaced ?? 0;
    if (metricAutoHandled) metricAutoHandled.textContent = counts.auto_handled_metric ?? 0;
    if (metricEliminated) metricEliminated.textContent = `${counts.triage_eliminated_pct ?? 0}%`;
    if (metricMissed) metricMissed.textContent = counts.missed_emails ?? 0;
    if (actionCountSpan) actionCountSpan.textContent = `(${counts.action_required ?? 0})`;
  }

  function buildQueueCard(item, kind = 'action') {
    const badge = kind === 'action' ? 'Action Required' : kind === 'optional' ? 'Optional' : 'INFO';
    const badgeClass =
      kind === 'action'
        ? 'badge-primary'
        : kind === 'optional'
        ? 'badge-optional'
        : 'text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-700/40 text-slate-300 border border-slate-700';
    const priority = (item.priority || 'P2').toUpperCase();
    const priorityBadge = `<span class="badge-pill badge-priority badge-priority-${priority.toLowerCase()}">${priority}</span>`;
    const subject = item.subject || 'Ticket';
    const provider = item.provider ? `<span>·</span><span>Provider: <span class="text-slate-200">${item.provider}</span></span>` : '';
    const aiReason = item.ai_reason || (kind === 'auto' ? 'Informational / auto-handled.' : 'Action required — customer needs help.');
    const owner = item.owner || 'Support';
    const sla = item.sla || item.due_at || '—';
    const openThreadLink = item.provider_url
      ? `<a href="${item.provider_url}" target="_blank" rel="noreferrer" class="text-slate-400 hover:text-slate-300 underline">Open thread</a>`
      : '';
    const actionBadge =
      kind === 'auto'
        ? `<span class="${badgeClass}">${badge}</span>`
        : `<span class="badge-pill ${badgeClass}">${badge}</span>`;
    const optionalMeta =
      kind === 'optional'
        ? `<div class="text-xs text-slate-400 flex flex-wrap gap-2"><span>Category: <span class="text-slate-200">${item.category || 'general'}</span></span><span>·</span><span>Intent: <span class="text-slate-200">${item.intent || 'unknown'}</span></span><span>·</span><span>Sentiment: <span class="text-slate-200">${item.sentiment || 'neutral'}</span></span></div>`
        : '';

    if (kind === 'auto') {
      return `
        <div class="p-4 bg-slate-950/40">
          <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                ${actionBadge}
                <div class="font-semibold text-slate-200 truncate">${subject}</div>
              </div>
              <div class="text-xs text-slate-500 mt-1">
                Type: <span class="text-slate-300">${item.category || 'informational'}</span>
                · Action required: <span class="text-slate-300">no</span>
              </div>
              <div class="text-xs text-slate-400 mt-2">
                <span class="font-semibold">Why auto-handled:</span>
                ${aiReason}
              </div>
            </div>
            <div class="shrink-0 text-xs text-slate-500 flex flex-col gap-1 items-end text-right">
              <div>Owner: <span class="text-slate-300 font-semibold">${owner}</span></div>
              <div>SLA: <span class="text-slate-300 font-semibold">${sla}</span></div>
              <a href="${item.url || '#'}" class="text-slate-400 hover:text-slate-300 underline">View</a>
            </div>
          </div>
        </div>
      `;
    }

    return `
      <div
        class="rounded-2xl border border-slate-800 bg-slate-900/40 px-5 py-4 hover:bg-slate-900/50 transition action-card"
        data-priority="${priority}"
        data-text="${(subject + ' ' + (item.category || '') + ' ' + (item.intent || '') + ' ' + (item.sentiment || '')).toLowerCase()}"
      >
        <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-4 md:gap-6">
          <div class="min-w-0 space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              ${priorityBadge}
              ${actionBadge}
              <div class="font-semibold text-slate-50 truncate">${subject}</div>
            </div>
            ${optionalMeta || `<div class="text-xs text-slate-400 flex flex-wrap gap-2">
              <span>Category: <span class="text-slate-200">${item.category || 'general'}</span></span>
              <span>·</span>
              <span>Intent: <span class="text-slate-200">${item.intent || 'unknown'}</span></span>
              <span>·</span>
              <span>Sentiment: <span class="text-slate-200">${item.sentiment || 'neutral'}</span></span>
              ${provider}
            </div>`}
            <div class="text-sm text-slate-100">
              <span class="font-semibold text-slate-50">AI decision:</span>
              ${aiReason}
            </div>
          </div>
            <div class="shrink-0 text-xs text-slate-300 flex flex-col gap-1 items-end text-right">
              <div>Assigned: <span class="text-slate-50 font-semibold">${owner}</span></div>
              <div>SLA: <span class="text-slate-50 font-semibold">${sla}</span></div>
              <a href="${item.url || '#'}" class="text-indigo-300 hover:text-indigo-200 underline underline-offset-2">Open ticket</a>
              ${openThreadLink}
            </div>
        </div>
      </div>
    `;
  }

  function renderList(listEl, items, kind) {
    if (!listEl) return;
    if (!items || !items.length) {
      listEl.innerHTML =
        kind === 'auto'
          ? '<div class="p-4 text-xs text-slate-400">No auto-handled items to show yet.</div>'
          : '<div class="px-5 py-4 text-sm text-slate-400 rounded-xl border border-slate-800 bg-slate-900/30">No items for this filter.</div>';
      return;
    }
    listEl.innerHTML = items.map((item) => buildQueueCard(item, kind)).join('');
    if (kind === 'action') {
      actionCards = Array.from(listEl.querySelectorAll('.action-card'));
    }
  }

  async function loadDashboardData() {
    const params = new URLSearchParams();
    if (impactScope?.value) params.set('scope', impactScope.value);
    if (actionPriorityFilter?.value) params.set('priority', actionPriorityFilter.value);
    if (actionSearchInput?.value) params.set('q', actionSearchInput.value.trim());
    if (showActionOnlyToggle && !showActionOnlyToggle.checked) params.set('action_only', 'false');

    try {
      const resp = await fetch(`/api/v1/inboxiq/dashboard-data?${params.toString()}`, { credentials: 'include' });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Unable to load dashboard data');
      updateMetrics(data.counts || {});
      renderList(actionRequiredList, data.action_required || [], 'action');
      renderList(optionalList, data.optional || [], 'optional');
      renderList(autoHandledEmailList, data.auto_handled || [], 'auto');
      renderList(autoHandledFeedbackList, data.auto_handled_feedback || [], 'auto');
    } catch (err) {
      console.warn('dashboard data fetch failed', err);
    }
  }

  updateActionOnlyHint();

  function renderTicketCards(items) {
    if (!ticketResults) return;
    ticketResults.innerHTML = '';
    if (!items || !items.length) {
      ticketResults.innerHTML =
        '<div class="rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-300">No tickets found for this filter.</div>';
      return;
    }
    items.forEach((t) => {
      const created = t.created_at ? new Date(t.created_at).toLocaleString() : '';
      const dueAt = t.due_at ? new Date(t.due_at).toLocaleString() : '';
      const breachSoon = t.due_at && Date.parse(t.due_at) < Date.now() + 60 * 60 * 1000;
      const ticketId = t.id || '';
      const ticketIdDisplay = ticketId
        ? `<span class="text-[11px] text-slate-400 font-mono">ID: ${ticketId}</span>`
        : '';
      const threadLink = t.provider_thread_url
        ? `<a class="text-indigo-300 hover:text-indigo-200 text-[11px]" href="${t.provider_thread_url}" target="_blank" rel="noreferrer">Open thread</a>`
        : '';
      const lastQuestion = t.last_question
        ? `<div class="text-[11px] text-slate-400 mt-1"><span class="text-slate-500">Last question:</span> ${t.last_question}</div>`
        : '';
      const summaryText = (t.summary || "").trim();
      const bodyText = (t.body_preview || "").trim();
      const summary =
        summaryText && summaryText !== bodyText
          ? `<div class="text-[11px] text-slate-300 mt-1">${summaryText}</div>`
          : '';
      const bodyPreview = bodyText
        ? `<div class="text-[11px] text-slate-400 mt-1 line-clamp-3">${bodyText}</div>`
        : '';
      const intent = t.intent ? `<div class="text-[11px] text-slate-400">Intent: ${t.intent}</div>` : '';
      const owner = t.owner ? `<div class="text-[11px] text-slate-400">Owner: ${t.owner}</div>` : '';
      const assignedTo = t.assigned_to ? `<div class="text-[11px] text-slate-400">Assigned to: ${t.assigned_to}</div>` : '';
      const team = t.team ? `<div class="text-[11px] text-slate-400">Team: ${t.team}</div>` : '';
      const risk = t.risk_flag ? '<span class="ml-1 px-2 py-[2px] rounded-full bg-amber-500/10 text-amber-200 text-[10px]">risk</span>' : '';
      const card = document.createElement('div');
      card.className = 'rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200';
      card.innerHTML = `
        <div class="flex items-center justify-between mb-1">
          <div class="flex flex-col">
            <span class="font-semibold text-slate-100">${t.subject || 'Ticket'} ${risk}</span>
            ${ticketIdDisplay}
          </div>
          <span class="text-[11px] text-slate-400">${created}</span>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div><span class="text-slate-400">Category:</span> ${t.category || '-'}</div>
          <div><span class="text-slate-400">Priority:</span> ${t.priority || '-'}</div>
          <div><span class="text-slate-400">Sentiment:</span> ${t.sentiment || '-'}</div>
          <div><span class="text-slate-400">Provider:</span> ${t.provider || 'n/a'}</div>
          <div><span class="text-slate-400">Due:</span> ${dueAt || 'n/a'} ${breachSoon ? '<span class="ml-1 px-2 py-[2px] rounded-full bg-rose-500/10 text-rose-200 text-[10px]">breach soon</span>' : ''}</div>
          <div>${threadLink}</div>
        </div>
        ${intent}
        ${team}
        ${owner}
        ${assignedTo}
        ${bodyPreview}
        ${summary}
        ${lastQuestion}
        <div class="flex items-center gap-2 mt-2">
          <button class="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px]" data-ticket="${t.id}" data-feedback="true">Triage correct</button>
          <button class="px-3 py-1 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-[11px]" data-ticket="${t.id}" data-feedback="false">Needs fix</button>
        </div>
      `;
      ticketResults.appendChild(card);
    });
    ticketResults.querySelectorAll('button[data-feedback]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const ticketId = btn.dataset.ticket;
        const correct = btn.dataset.feedback === 'true';
        btn.disabled = true;
        try {
          let category = null;
          let priority = null;
          let team = null;
          let assignedTo = null;
          if (!correct) {
            const catInput = prompt('Override category? (leave blank to keep current)');
            const priInput = prompt('Override priority? (P0/P1/P2; leave blank to keep current)');
            const teamInput = prompt('Assign to team? (e.g., Billing, Engineering, Support)');
            const ownerInput = prompt('Assign to owner/queue?');
            category = catInput && catInput.trim() ? catInput.trim() : null;
            priority = priInput && priInput.trim() ? priInput.trim() : null;
            team = teamInput && teamInput.trim() ? teamInput.trim() : null;
            assignedTo = ownerInput && ownerInput.trim() ? ownerInput.trim() : null;
          }
          const resp = await fetch(`/api/v1/inboxiq/tickets/${ticketId}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ correct, category, priority, team, assigned_to: assignedTo }),
          });
          const data = await resp.json();
          if (!resp.ok) {
            throw new Error(data.error || `Feedback failed (status ${resp.status})`);
          }
          setTicketStatus('success', correct ? 'Marked as correct' : 'Sent for re-triage');
          // Refresh the ticket list so the updated category/assignment shows immediately.
          performTicketSearch();
        } catch (err) {
          setTicketStatus('error', err.message || 'Feedback failed');
        } finally {
          btn.disabled = false;
        }
      });
    });
  }

  async function performTicketSearch(event) {
    if (event) event.preventDefault();
    const params = new URLSearchParams();
    params.set('page_size', '10');
    if (qInput?.value) params.set('q', qInput.value.trim());
    if (statusInput?.value) params.set('status', statusInput.value);
    if (categoryInput?.value) params.set('category', categoryInput.value);
    if (priorityInput?.value) params.set('priority', priorityInput.value);
    if (afterInput?.value) params.set('created_after', afterInput.value);
    if (beforeInput?.value) params.set('created_before', beforeInput.value);

    setTicketStatus('info', 'Loading tickets…');
    try {
      const resp = await fetch(`/api/v1/inboxiq/tickets?${params.toString()}`, {
        credentials: 'include',
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || 'Failed to load tickets');
      }
      renderTicketCards(data.tickets || []);
      setTicketStatus('success', `Loaded ${data.tickets ? data.tickets.length : 0} tickets`);
    } catch (err) {
      setTicketStatus('error', err.message || 'Unable to load tickets');
    }
  }

  if (searchForm) {
    searchForm.addEventListener('submit', performTicketSearch);
  }

  async function submitTestimonial() {
    if (!submitTestimonialBtn) return;
    const message = (testimonialMsg?.value || '').trim();
    const rating = testimonialRating?.value || '5';
    const consent_public = testimonialConsent?.checked || false;
    if (!message) {
      if (testimonialStatus) {
        testimonialStatus.className = 'text-xs rounded-xl border border-rose-400/40 bg-rose-500/10 text-rose-100 px-3 py-2';
        testimonialStatus.textContent = 'Please enter a short testimonial.';
        testimonialStatus.classList.remove('hidden');
      }
      return;
    }
    submitTestimonialBtn.disabled = true;
    try {
      const resp = await fetch('/api/v1/testimonials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ message, rating, consent_public }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        const msg = data.error === 'insufficient_usage'
          ? 'Please use the product a bit more before submitting a testimonial.'
          : (data.error || 'Unable to submit right now.');
        throw new Error(msg);
      }
      if (testimonialStatus) {
        testimonialStatus.className = 'text-xs rounded-xl border border-emerald-400/40 bg-emerald-500/10 text-emerald-100 px-3 py-2';
        testimonialStatus.textContent = 'Thank you! Submitted.';
        testimonialStatus.classList.remove('hidden');
      }
      if (testimonialMsg) testimonialMsg.value = '';
    } catch (err) {
      if (testimonialStatus) {
        testimonialStatus.className = 'text-xs rounded-xl border border-rose-400/40 bg-rose-500/10 text-rose-100 px-3 py-2';
        testimonialStatus.textContent = err.message || 'Unable to submit testimonial.';
        testimonialStatus.classList.remove('hidden');
      }
    } finally {
      submitTestimonialBtn.disabled = false;
    }
  }

  if (connectGmailBtn) {
    connectGmailBtn.addEventListener('click', () => startConnect('gmail'));
  }
  if (connectOutlookBtn) {
    connectOutlookBtn.addEventListener('click', () => startConnect('outlook'));
  }

  if (pollNowBtn) {
    pollNowBtn.addEventListener('click', async () => {
      if (pollStatus) {
        pollStatus.classList.remove('hidden');
        pollStatus.textContent = 'Polling inbox...';
      }
      try {
        const csrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
        const resp = await fetch('/api/v1/inboxiq/poll/mine', {
          method: 'POST',
          credentials: 'include',
          headers: csrf ? { 'X-CSRF-TOKEN': csrf } : {},
        });
        const contentType = resp.headers.get('content-type') || '';
        const data = contentType.includes('application/json') ? await resp.json() : {};
        if (!resp.ok) throw new Error(data.error || data.message || `HTTP ${resp.status}`);
        if (pollStatus) pollStatus.textContent = 'Poll triggered. Refreshing...';
        window.location.reload();
      } catch (err) {
        if (pollStatus) pollStatus.textContent = `Error: ${err.message}`;
      }
    });
  }
  if (submitTestimonialBtn) {
    submitTestimonialBtn.addEventListener('click', submitTestimonial);
  }

  // Initial data load for dashboard filters/metrics
  loadDashboardData();

  const logoutForm = document.getElementById('logoutForm');
  if (logoutForm) {
    logoutForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const csrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
      try {
        await fetch('/auth/logout', {
          method: 'POST',
          credentials: 'include',
          headers: csrf ? { 'X-CSRF-TOKEN': csrf } : {},
        });
      } finally {
        window.location.href = '/login';
      }
    });
  }

  // User menu toggle (CSP-safe)
  (function () {
    const btn = document.getElementById('userMenuBtn');
    const menu = document.getElementById('userMenu');
    if (!btn || !menu) return;
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      menu.classList.toggle('hidden');
    });
    document.addEventListener('click', (e) => {
      if (menu.classList.contains('hidden')) return;
      if (!menu.contains(e.target) && !btn.contains(e.target)) {
        menu.classList.add('hidden');
      }
    });
  })();
})();
