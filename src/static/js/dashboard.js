(() => {
  console.debug('[dashboard] init script loaded');
  const connectBtn = document.getElementById('connectInboxBtn');
  const modal = document.getElementById('connectModal');
  const closeBtn = document.getElementById('closeModalBtn');
  const cancelBtn = document.getElementById('cancelConnect');
  const form = document.getElementById('connectForm');
  const statusEl = document.getElementById('connectStatus');
  const imapFields = document.getElementById('imapFields');
  const step1Status = document.getElementById('step1Status');
  const step1Badge = document.getElementById('step1Badge');
  const step2Card = document.getElementById('step2Card');
  const step3Card = document.getElementById('step3Card');
  const saveCategoriesBtn = document.getElementById('saveCategoriesBtn');
  const runTriageBtn = document.getElementById('runTriageBtn');
  const categoriesModal = document.getElementById('categoriesModal');
  const closeCategories = document.getElementById('closeCategories');
  const cancelCategories = document.getElementById('cancelCategories');
  const categoriesForm = document.getElementById('categoriesForm');
  const categoriesStatus = document.getElementById('categoriesStatus');
  const customCategoryInput = document.getElementById('customCategoryInput');
  const customCategoryAdd = document.getElementById('customCategoryAdd');
  const customCategoriesContainer = document.getElementById('customCategoriesContainer');
  const step2Status = document.getElementById('step2Status');
  const step2Badge = document.getElementById('step2Badge');
  const triageModal = document.getElementById('triageModal');
  const closeTriage = document.getElementById('closeTriage');
  const runTriageConfirm = document.getElementById('runTriageConfirm');
  const triageStatus = document.getElementById('triageStatus');
  const step3Status = document.getElementById('step3Status');
  const step3Badge = document.getElementById('step3Badge');
  const goDashboardBtn = document.getElementById('goDashboardBtn');
  const draftReplySection = document.getElementById('draftReplySection');
  const enableDraftReplyCheckbox = document.getElementById('enableDraftReply');
  const draftReplyPlanNote = document.getElementById('draftReplyPlanNote');

  const STORAGE_KEY = 'inboxiqInboxConnected';
  const STORAGE_CATEGORIES = 'inboxiqCategoriesSaved';
  const STORAGE_TRIAGE = 'inboxiqTriageDone';
  const STORAGE_DRAFT_REPLY = 'inboxiqDraftReplyEnabled';

  function showLayer(el) {
    if (!el) return;
    el.classList.add('modal-visible', 'flex');
    el.classList.remove('modal-hidden');
    el.setAttribute('aria-hidden', 'false');
    console.debug('[dashboard] show layer', el.id, window.getComputedStyle(el).display);
  }
  function hideLayer(el) {
    if (!el) return;
    el.classList.remove('modal-visible', 'flex');
    el.classList.add('modal-hidden');
    el.setAttribute('aria-hidden', 'true');
    console.debug('[dashboard] hide layer', el.id);
  }
  function openModal() {
    showLayer(modal);
  }
  function closeModal() {
    hideLayer(modal);
  }

  function setStatus(type, message) {
    if (!statusEl) return;
    const map = {
      success: 'border border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
      error: 'border border-rose-400/40 bg-rose-500/10 text-rose-100',
      info: 'border border-indigo-400/40 bg-indigo-500/10 text-indigo-100',
    };
    statusEl.className = `text-sm rounded-xl px-3 py-2 ${map[type] || map.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove('hidden');
  }

  function updateStepsAsConnected() {
    try {
      localStorage.setItem(STORAGE_KEY, 'true');
    } catch (e) {
      // ignore
    }
    if (step1Status) step1Status.classList.remove('hidden');
    if (step1Badge) step1Badge.classList.remove('hidden');
    if (step2Card) step2Card.classList.remove('opacity-80');
    if (step3Card) step3Card.classList.remove('opacity-60');
    if (saveCategoriesBtn) {
      saveCategoriesBtn.classList.remove('cursor-not-allowed', 'opacity-80');
      saveCategoriesBtn.disabled = false;
    }
    if (runTriageBtn) {
      runTriageBtn.classList.remove('cursor-not-allowed', 'opacity-60');
      runTriageBtn.disabled = false;
    }
    // Show draft reply section after inbox connection
    if (draftReplySection) {
      draftReplySection.classList.remove('hidden');
      fetchDraftReplyStatus();
    }
  }

  function maybeRestoreConnected() {
    try {
      const flag = localStorage.getItem(STORAGE_KEY);
      if (flag === 'true') {
        updateStepsAsConnected();
      }
    } catch (e) {
      // ignore storage failures
    }
  }

  function updateCategoriesSaved(selected) {
    try {
      localStorage.setItem(STORAGE_CATEGORIES, JSON.stringify(selected || []));
    } catch (e) {
      // ignore
    }
    if (step2Status) step2Status.classList.remove('hidden');
    if (step2Badge) step2Badge.classList.remove('hidden');
    if (step3Card) step3Card.classList.remove('opacity-60');
    if (runTriageBtn) {
      runTriageBtn.classList.remove('cursor-not-allowed', 'opacity-60');
      runTriageBtn.disabled = false;
    }
  }

  function normalizeCategoryLabel(label) {
    return (label || '').trim().replace(/\s+/g, ' ');
  }

  function hasCategory(label) {
    const normalized = normalizeCategoryLabel(label).toLowerCase();
    if (!normalized) return true;
    const existing = categoriesForm?.querySelectorAll('input[name="categories"]') || [];
    for (const input of existing) {
      if ((input.value || '').trim().toLowerCase() === normalized) return true;
    }
    return false;
  }

  function addCustomCategory(label, checked = true) {
    const normalized = normalizeCategoryLabel(label);
    if (!normalized) return false;
    if (hasCategory(normalized)) {
      const existing = categoriesForm?.querySelector(`input[name="categories"][value="${normalized}"]`);
      if (existing) existing.checked = true;
      return false;
    }
    if (!customCategoriesContainer) return false;
    const wrap = document.createElement('label');
    wrap.className = 'flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/70 px-3 py-2 cursor-pointer hover:border-indigo-400/60';
    wrap.innerHTML = `
      <input type="checkbox" name="categories" value="${normalized}" class="h-4 w-4 rounded border-slate-700 bg-slate-900 text-indigo-500" ${checked ? 'checked' : ''}/>
      <span class="text-sm text-slate-100">${normalized}</span>
    `;
    customCategoriesContainer.appendChild(wrap);
    return true;
  }

  function maybeRestoreCategories() {
    try {
      const raw = localStorage.getItem(STORAGE_CATEGORIES);
      if (raw) {
        const selected = JSON.parse(raw);
        selected.forEach((cat) => {
          const input = categoriesForm?.querySelector(`input[name="categories"][value="${cat}"]`);
          if (input) {
            input.checked = true;
          } else {
            addCustomCategory(cat, true);
          }
        });
        updateCategoriesSaved(selected);
      }
    } catch (e) {
      // ignore
    }
  }

  function markTriageDone() {
    try {
      localStorage.setItem(STORAGE_TRIAGE, 'true');
    } catch (e) {
      // ignore
    }
    if (step3Status) step3Status.classList.remove('hidden');
    if (step3Badge) step3Badge.classList.remove('hidden');
    if (goDashboardBtn) goDashboardBtn.classList.remove('hidden');
  }

  function maybeRestoreTriage() {
    try {
      const flag = localStorage.getItem(STORAGE_TRIAGE);
      if (flag === 'true') {
        markTriageDone();
      }
    } catch (e) {
      // ignore
    }
  }

  async function fetchDraftReplyStatus() {
    if (!enableDraftReplyCheckbox) return;

    try {
      const response = await fetch('/api/v1/features/draft-reply', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();

        // Set checkbox state
        enableDraftReplyCheckbox.checked = data.draft_reply_enabled || false;

        // Store in localStorage
        try {
          localStorage.setItem(STORAGE_DRAFT_REPLY, data.draft_reply_enabled ? 'true' : 'false');
        } catch (e) {
          // ignore
        }

        // Show plan note if user doesn't have access
        if (draftReplyPlanNote && !data.has_access) {
          draftReplyPlanNote.classList.remove('hidden');
        }

        // Disable checkbox if user doesn't have access
        if (!data.can_enable) {
          enableDraftReplyCheckbox.disabled = true;
          enableDraftReplyCheckbox.classList.add('opacity-50', 'cursor-not-allowed');
        }

        console.debug('[dashboard] draft reply status loaded', data);
      } else {
        console.error('[dashboard] failed to fetch draft reply status', response.status);
      }
    } catch (err) {
      console.error('[dashboard] error fetching draft reply status', err);
    }
  }

  async function handleDraftReplyToggle(event) {
    const enabled = event.target.checked;

    try {
      const response = await fetch('/api/v1/features/draft-reply', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ enabled }),
      });

      if (response.ok) {
        const data = await response.json();
        console.debug('[dashboard] draft reply updated', data);

        // Store in localStorage
        try {
          localStorage.setItem(STORAGE_DRAFT_REPLY, enabled ? 'true' : 'false');
        } catch (e) {
          // ignore
        }

        // Show brief success message (optional)
        if (statusEl) {
          const msg = enabled ? 'Draft reply feature enabled' : 'Draft reply feature disabled';
          setStatus('success', msg);
          setTimeout(() => {
            statusEl.classList.add('hidden');
          }, 2000);
        }
      } else if (response.status === 403) {
        // Not eligible - revert checkbox
        event.target.checked = !enabled;
        const errorData = await response.json();
        if (statusEl) {
          setStatus('error', errorData.message || 'Draft reply requires Business plan or trial');
          setTimeout(() => {
            statusEl.classList.add('hidden');
          }, 3000);
        }
      } else {
        // Other error - revert checkbox
        event.target.checked = !enabled;
        console.error('[dashboard] failed to update draft reply', response.status);
      }
    } catch (err) {
      // Network error - revert checkbox
      event.target.checked = !enabled;
      console.error('[dashboard] error updating draft reply', err);
    }
  }

  function getAccessToken() {
    // Get JWT token from cookie or localStorage
    const cookies = document.cookie.split(';');
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'access_token_cookie') {
        return value;
      }
    }
    // Fallback to localStorage if used
    return localStorage.getItem('access_token') || '';
  }

  function maybeRestoreDraftReply() {
    try {
      const flag = localStorage.getItem(STORAGE_DRAFT_REPLY);
      const inboxConnected = localStorage.getItem(STORAGE_KEY);

      // Only show draft reply section if inbox is connected
      if (inboxConnected === 'true' && draftReplySection) {
        draftReplySection.classList.remove('hidden');
        fetchDraftReplyStatus();
      }
    } catch (e) {
      // ignore
    }
  }

  // Fallback: if the DOM already shows completed badges (e.g., after refresh without localStorage),
  // infer completion so CTA buttons are usable.
  function reconcileFromDom() {
    const step1Done = step1Badge && !step1Badge.classList.contains('hidden');
    const step2Done = step2Badge && !step2Badge.classList.contains('hidden');
    const step3Done = step3Badge && !step3Badge.classList.contains('hidden');
    if (step1Done) {
      updateStepsAsConnected();
    }
    if (step2Done) {
      updateCategoriesSaved([]);
    }
    if (step3Done) {
      markTriageDone();
    }
  }

  function handleProviderChange(event) {
    if (!imapFields) return;
    const val = event.target.value;
    if (val === 'imap') {
      imapFields.classList.remove('hidden');
    } else {
      imapFields.classList.add('hidden');
    }
  }

  function bindProviderRadios() {
    if (!form) return;
    const radios = form.querySelectorAll('input[name="provider"]');
    radios.forEach((radio) => {
      radio.addEventListener('change', handleProviderChange);
    });
  }

  async function handleConnect(event) {
    event.preventDefault();
    if (!form) return;
    const data = new FormData(form);
    const provider = data.get('provider') || 'gmail';

    if (provider === 'imap') {
      const host = document.getElementById('imapHost')?.value.trim();
      const port = document.getElementById('imapPort')?.value.trim();
      const user = document.getElementById('imapUser')?.value.trim();
      const pass = document.getElementById('imapPass')?.value.trim();
      if (!host || !port || !user || !pass) {
        setStatus('error', 'Please fill IMAP host, port, username, and password.');
        return;
      }
    }

    setStatus('info', 'Connecting to your inbox...');
    try {
      // Placeholder success path; integrate real API call here.
      await new Promise((resolve) => setTimeout(resolve, 600));
      setStatus('success', 'Inbox connected! We will pull messages and unlock the next steps.');
      updateStepsAsConnected();
      setTimeout(closeModal, 400);
    } catch (err) {
      setStatus('error', 'Unable to connect right now. Please try again.');
    }
  }

  if (connectBtn) {
    connectBtn.addEventListener('click', (e) => {
      e.preventDefault();
      console.debug('[dashboard] connect click');
      openModal();
    });
  } else {
    console.warn('[dashboard] connect button not found');
  }
  if (closeBtn) closeBtn.addEventListener('click', (e) => { e.preventDefault(); closeModal(); });
  if (cancelBtn) cancelBtn.addEventListener('click', (e) => { e.preventDefault(); closeModal(); });
  if (form) form.addEventListener('submit', handleConnect);

  bindProviderRadios();
  maybeRestoreConnected();
  maybeRestoreCategories();
  maybeRestoreTriage();
  maybeRestoreDraftReply();
  reconcileFromDom();

  // Draft reply checkbox handler
  if (enableDraftReplyCheckbox) {
    enableDraftReplyCheckbox.addEventListener('change', handleDraftReplyToggle);
  }

  if (saveCategoriesBtn) {
    saveCategoriesBtn.addEventListener('click', () => {
      const disabled = saveCategoriesBtn.disabled || saveCategoriesBtn.classList.contains('cursor-not-allowed');
      if (disabled) return;
      showLayer(categoriesModal);
    });
  }
  if (closeCategories) closeCategories.addEventListener('click', () => hideLayer(categoriesModal));
  if (cancelCategories) cancelCategories.addEventListener('click', () => hideLayer(categoriesModal));
  if (categoriesForm) {
    categoriesForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const selected = Array.from(categoriesForm.querySelectorAll('input[name="categories"]:checked')).map((i) => i.value);
      if (!selected.length) {
        if (categoriesStatus) {
          categoriesStatus.className = 'text-sm rounded-xl px-3 py-2 border border-rose-400/40 bg-rose-500/10 text-rose-100';
          categoriesStatus.textContent = 'Please pick at least one category.';
          categoriesStatus.classList.remove('hidden');
        }
        return;
      }
      if (categoriesStatus) {
        categoriesStatus.className = 'text-sm rounded-xl px-3 py-2 border border-emerald-400/40 bg-emerald-500/10 text-emerald-100';
        categoriesStatus.textContent = 'Categories saved. Moving to triage preview.';
        categoriesStatus.classList.remove('hidden');
      }
      updateCategoriesSaved(selected);
      setTimeout(() => hideLayer(categoriesModal), 400);
    });
  }

  function handleAddCustomCategory() {
    const label = normalizeCategoryLabel(customCategoryInput?.value || '');
    if (!label) return;
    const added = addCustomCategory(label, true);
    if (added && customCategoryInput) customCategoryInput.value = '';
  }

  if (customCategoryAdd) {
    customCategoryAdd.addEventListener('click', handleAddCustomCategory);
  }
  if (customCategoryInput) {
    customCategoryInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAddCustomCategory();
      }
    });
  }

  if (runTriageBtn) {
    runTriageBtn.addEventListener('click', () => {
      const disabled = runTriageBtn.disabled || runTriageBtn.classList.contains('cursor-not-allowed');
      if (disabled) return;
      showLayer(triageModal);
    });
  }
  if (closeTriage) closeTriage.addEventListener('click', () => hideLayer(triageModal));
  if (runTriageConfirm) {
    runTriageConfirm.addEventListener('click', async () => {
      if (triageStatus) {
        triageStatus.textContent = 'Running triage on sample emails...';
        triageStatus.classList.remove('hidden');
      }
      await new Promise((resolve) => setTimeout(resolve, 800));
      markTriageDone();
      if (triageStatus) {
        triageStatus.textContent = 'Triage complete! Redirecting to dashboard…';
      }
      setTimeout(() => {
        window.location.href = '/dashboard';
      }, 600);
    });
  }
})();
