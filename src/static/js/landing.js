(() => {
  const emailsInput = document.getElementById('emailsPerWeek');
  const minutesInput = document.getElementById('minutesPerEmail');
  const hourlyInput = document.getElementById('hourlyRate');
  const resultsEl = document.getElementById('roiResults');
  const yearSpan = document.getElementById('yearSpan');
  const ctaForm = document.getElementById('ctaForm');
  const ctaButton = document.getElementById('ctaButton');
  const ctaStatus = document.getElementById('ctaStatus');
  const ctaEmail = document.getElementById('ctaEmail');
  const ctaAccountName = document.getElementById('ctaAccountName');

  // Dropdowns (e.g., Solutions menu)
  const dropdowns = Array.from(document.querySelectorAll('[data-dropdown]'))
    .map((toggle) => {
      const id = toggle.dataset.dropdown;
      const menu = document.querySelector(`[data-dropdown-menu="${id}"]`);
      if (!menu) return null;
      toggle.setAttribute('aria-haspopup', 'true');
      toggle.setAttribute('aria-expanded', 'false');
      return { toggle, menu };
    })
    .filter(Boolean);

  const closeAllDropdowns = () => {
    dropdowns.forEach(({ toggle, menu }) => {
      if (!menu.classList.contains('hidden')) menu.classList.add('hidden');
      toggle.setAttribute('aria-expanded', 'false');
    });
  };

  dropdowns.forEach(({ toggle, menu }) => {
    toggle.addEventListener('click', (event) => {
      event.preventDefault();
      const isHidden = menu.classList.contains('hidden');
      closeAllDropdowns();
      if (isHidden) {
        const rect = toggle.getBoundingClientRect();

        // Measure the menu to decide whether to drop down or up.
        menu.style.position = 'fixed';
        menu.style.visibility = 'hidden';
        menu.style.display = 'block';
        menu.classList.remove('hidden');
        const menuHeight = menu.offsetHeight || 0;
        const menuWidth = menu.offsetWidth || 0;

        // Choose drop direction based on available viewport space.
        const spaceBelow = window.innerHeight - rect.bottom;
        const dropDown = spaceBelow > menuHeight + 8;
        const top = dropDown ? rect.bottom + 4 : Math.max(8, rect.top - menuHeight - 4);

        // Clamp left within viewport.
        const maxLeft = Math.max(8, window.innerWidth - (menuWidth || rect.width) - 8);
        const left = Math.min(rect.left, maxLeft);

        menu.style.top = `${top}px`;
        menu.style.left = `${left}px`;
        menu.style.minWidth = `${Math.max(rect.width + 20, menuWidth || 0)}px`;
        menu.style.zIndex = menu.style.zIndex || '9000';
        menu.style.visibility = '';
        menu.style.display = '';
        toggle.setAttribute('aria-expanded', 'true');
      }
    });
  });

  document.addEventListener('click', (event) => {
    const isDropdownClick = dropdowns.some(
      ({ toggle, menu }) => toggle.contains(event.target) || menu.contains(event.target)
    );
    if (!isDropdownClick) closeAllDropdowns();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeAllDropdowns();
      dropdowns.forEach(({ toggle }) => toggle.blur());
    }
  });

  if (yearSpan) {
    yearSpan.textContent = new Date().getFullYear();
  }

  const calculateROI = function() {
    const emailsPerWeek = parseFloat(emailsInput?.value) || 80;
    const minutesPerEmail = parseFloat(minutesInput?.value) || 4;
    const hourlyRate = parseFloat(hourlyInput?.value) || 25;
    const proPrice = 99;
    const hireCost = 2917; // £35k/year junior hire ÷ 12

    // InboxIQ drafts ~80% of repetitive emails; review time ~10% of original compose time
    const emailsHandledPerMonth = emailsPerWeek * 4 * 0.8;
    const minutesSavedPerEmail = minutesPerEmail * 0.9; // draft replaces ~90% of compose time
    const hoursSaved = (emailsHandledPerMonth * minutesSavedPerEmail) / 60;
    const costSaved = hoursSaved * hourlyRate;
    const monthlyNet = costSaved - proPrice;

    let conclusion;
    if (monthlyNet > 0) {
      const paybackDays = Math.max(1, Math.round(30 * (proPrice / costSaved)));
      conclusion = `InboxIQ pays for itself in about <strong>${paybackDays} day${paybackDays === 1 ? '' : 's'}</strong> each month.`;
    } else {
      conclusion = 'With these inputs InboxIQ nearly breaks even — try increasing your weekly email volume.';
    }

    if (resultsEl) {
      resultsEl.innerHTML = `
        <p><strong>Hours saved per month:</strong> ${hoursSaved.toFixed(1)} hrs</p>
        <p><strong>Labour cost saved per month:</strong> £${costSaved.toFixed(0)}</p>
        <p><strong>Pro plan:</strong> £${proPrice}/month &nbsp;·&nbsp; <strong>Net saving:</strong> £${Math.max(0, monthlyNet).toFixed(0)}/month</p>
        <hr class="border-slate-700 my-2"/>
        <p class="text-slate-300"><strong>vs. a support hire:</strong> InboxIQ handles this volume for £${proPrice}/month vs. ~£${hireCost.toLocaleString()}/month for a junior hire.</p>
        <p class="mt-2">${conclusion}</p>
      `;
    }
  };

  const roiButton = document.getElementById('roiButton');
  if (roiButton) {
    roiButton.style.display = 'none';
  }

  [emailsInput, minutesInput, hourlyInput].forEach(function (el) {
    if (el) el.addEventListener('input', calculateROI);
  });

  const setCtaStatus = function(type, message, options = {}) {
    if (!ctaStatus) return;
    const { activationLink, helper, persistLink = false } = options;
    const color = type === 'success' ? 'border-emerald-300 text-emerald-50 bg-emerald-500/15' : 'border-white/30 text-white bg-white/10';
    ctaStatus.className = `max-w-3xl mx-auto text-left text-sm rounded-2xl px-4 py-3 space-y-2 ${color}`;
    ctaStatus.innerHTML = '';

    const msg = document.createElement('p');
    msg.textContent = message;
    ctaStatus.appendChild(msg);

    if (activationLink) {
      const linkRow = document.createElement('div');
      linkRow.className = 'flex flex-wrap items-center gap-3 text-indigo-50';

      const link = document.createElement('a');
      link.href = activationLink;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.className = 'underline font-semibold';
      link.textContent = 'Open activation link';
      linkRow.appendChild(link);

      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className =
        'px-3 py-1 rounded-full bg-white/10 border border-white/30 text-xs font-semibold hover:bg-white/20 transition';
      copyBtn.textContent = 'Copy link';
      copyBtn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(activationLink);
          copyBtn.textContent = 'Copied!';
          setTimeout(() => {
            copyBtn.textContent = 'Copy link';
          }, 1500);
        } catch (err) {
          copyBtn.textContent = 'Copy manually';
        }
      });
      linkRow.appendChild(copyBtn);

      ctaStatus.appendChild(linkRow);
    }

    if (helper) {
      const helperText = document.createElement('p');
      helperText.className = 'text-xs text-indigo-100';
      helperText.textContent = helper;
      ctaStatus.appendChild(helperText);
    }

    if (persistLink && activationLink) {
      try {
        localStorage.setItem(activationLinkStorageKey, activationLink);
      } catch (err) {
        // storage might be unavailable; ignore
      }
    }

    ctaStatus.classList.remove('hidden');
  };

  const handleCtaSubmit = async function(event) {
    event.preventDefault();
    if (!ctaEmail || !ctaButton) return;
    const email = (ctaEmail.value || '').trim().toLowerCase();
    const company = (ctaAccountName?.value || '').trim();

    if (!email) {
      setCtaStatus('error', 'Please provide your work email.');
      return;
    }

    ctaButton.disabled = true;
    ctaButton.textContent = 'Sending...';

    try {
      const website = (document.getElementById('ctaWebsite')?.value || '').trim();
      const payload = { name: email, email, company, source: 'homepage_cta', website: website || null };
      const response = await fetch('/api/v1/enterprise/inquiry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(payload),
      });
      const contentType = response.headers.get('content-type') || '';
      const isJson = contentType.includes('application/json');
      const data = isJson ? await response.json() : await response.text();
      if (!response.ok) {
        const message = (isJson && data?.error) || data || `Request failed (${response.status})`;
        throw new Error(message);
      }
      setCtaStatus('success', `Thanks — we'll be in touch at ${email} to arrange a demo.`);
    } catch (error) {
      setCtaStatus('error', error.message || 'Something went wrong. Please try again.');
    } finally {
      ctaButton.disabled = false;
      ctaButton.textContent = 'Talk to sales →';
    }
  };

  if (ctaForm) {
    ctaForm.addEventListener('submit', handleCtaSubmit);
  }
})();

// ── Demo Gate ─────────────────────────────────────────────────────────────
(function () {
  const modal    = document.getElementById('demoGateModal');
  const closeBtn = document.getElementById('demoGateClose');

  if (!modal) return;

  const playVideoInModal = function() {
    const src    = modal.dataset.videoSrc   || '/static/demo/InboxIQ.mp4';
    const poster = modal.dataset.posterSrc  || '/static/demo/inboxiq-dashboard.png';
    const inner  = modal.querySelector('div');
    inner.style.maxWidth = '860px';
    inner.innerHTML =
      '<button id="demoGateClose2" style="float:right;font-size:1.2rem;color:#94a3b8;background:none;border:none;cursor:pointer;margin-bottom:8px">✕</button>' +
      '<video src="' + src + '" poster="' + poster + '" controls autoplay playsinline muted' +
      ' style="width:100%;border-radius:12px;display:block"></video>';
    document.getElementById('demoGateClose2').addEventListener('click', function () {
      modal.style.display = 'none';
    });
  };

  const openModal = function() {
    modal.style.display = 'flex';
    playVideoInModal();
  };

  if (closeBtn) {
    closeBtn.addEventListener('click', function () { modal.style.display = 'none'; });
  }

  modal.addEventListener('click', function (e) {
    if (e.target === modal) modal.style.display = 'none';
  });

  document.querySelectorAll('[data-open-demo]').forEach(function (btn) {
    btn.addEventListener('click', openModal);
  });

  // Public opener — lets other sections trigger the modal with a custom video
  window._inboxiqOpenVideoModal = function (cfg) {
    if (cfg.videoSrc)  modal.dataset.videoSrc  = cfg.videoSrc;
    if (cfg.posterSrc) modal.dataset.posterSrc = cfg.posterSrc;
    openModal();
  };
})();

// ── Free Trial Modal ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const tmModal    = document.getElementById('trialModal');
  const tmForm     = document.getElementById('tmForm');
  const tmStatus   = document.getElementById('tmStatus');
  const tmButton   = document.getElementById('tmButton');
  const tmEmail    = document.getElementById('tmEmail');
  const tmAccount  = document.getElementById('tmAccountName');
  const tmTrigger  = document.getElementById('trialModalTrigger');
  const tmClose    = document.getElementById('tmClose');
  const tmBackdrop = document.getElementById('tmBackdrop');

  const openTrialModal = function() {
    if (!tmModal) return;
    tmModal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    if (tmEmail) tmEmail.focus();
  };

  const closeTrialModal = function() {
    if (!tmModal) return;
    tmModal.style.display = 'none';
    document.body.style.overflow = '';
  };

  const setTmStatus = function(type, message) {
    if (!tmStatus) return;
    const cls = type === 'success'
      ? 'rounded-lg px-3 py-2 text-xs bg-emerald-900/60 border border-emerald-700 text-emerald-200'
      : type === 'error'
        ? 'rounded-lg px-3 py-2 text-xs bg-red-900/60 border border-red-700 text-red-200'
        : 'rounded-lg px-3 py-2 text-xs bg-slate-800 border border-slate-600 text-slate-300';
    tmStatus.className = cls;
    tmStatus.textContent = message;
    tmStatus.style.display = 'block';
  };

  const handleTmSubmit = async function(event) {
    event.preventDefault();
    if (!tmEmail || !tmButton) return;
    const email       = (tmEmail.value || '').trim().toLowerCase();
    const accountName = (tmAccount ? tmAccount.value || '' : '').trim();

    if (!email)       { setTmStatus('error', 'Please provide your work email.'); return; }
    if (!accountName) { setTmStatus('error', 'Please provide an account name.'); return; }

    tmButton.disabled = true;
    tmButton.textContent = 'Creating...';
    setTmStatus('info', 'Creating your workspace…');

    try {
      const response = await fetch('/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ email: email, account_name: accountName }),
      });
      const contentType = response.headers.get('content-type') || '';
      const isJson = contentType.includes('application/json');
      const data = isJson ? await response.json() : await response.text();
      if (!response.ok) {
        throw new Error((isJson && data && data.error) || data || ('Request failed (' + response.status + ')'));
      }
      if (isJson && data && data.account_id !== undefined) {
        localStorage.setItem('inboxiqAccountId', data.account_id);
      }
      const activationLink = isJson ? (data && data.activation_link) : null;
      if (activationLink) {
        try { localStorage.setItem('inboxiqActivationLink', activationLink); } catch (e) {}
      }
      let msg = 'Workspace created! Check ' + email + ' for your activation link.';
      if (activationLink) msg += ' Or open: ' + activationLink;
      setTmStatus('success', msg);
      tmButton.textContent = 'Done!';
    } catch (error) {
      setTmStatus('error', error.message || 'Unable to create workspace.');
      tmButton.disabled = false;
      tmButton.textContent = 'Start Free Trial →';
    }
  };

  if (tmTrigger)  tmTrigger.addEventListener('click', openTrialModal);
  if (tmClose)    tmClose.addEventListener('click', closeTrialModal);
  if (tmBackdrop) tmBackdrop.addEventListener('click', closeTrialModal);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && tmModal && tmModal.style.display !== 'none') closeTrialModal();
  });
  if (tmForm) tmForm.addEventListener('submit', handleTmSubmit);

  // Auto-open when redirected from /signup with ?open_trial=1
  // Strip the query param immediately so a page refresh doesn't re-open the modal.
  if (new URLSearchParams(window.location.search).get('open_trial') === '1') {
    history.replaceState(null, '', window.location.pathname);
    openTrialModal();
  }
});

// ── Enterprise Inquiry Modal ───────────────────────────────────────────────
// Wrapped in DOMContentLoaded: modal HTML sits after this script tag in index.html.
document.addEventListener('DOMContentLoaded', function () {
  const modal     = document.getElementById('enterpriseModal');
  const form      = document.getElementById('eiInquiryForm');
  const statusEl  = document.getElementById('eiFormStatus');
  const submitBtn = document.getElementById('eiSubmitBtn');

  const openEnterpriseModal = function() {
    if (!modal) return;
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    const first = document.getElementById('eiName');
    if (first) setTimeout(function () { first.focus(); }, 50);
  };

  const closeEnterpriseModal = function() {
    if (!modal) return;
    modal.style.display = 'none';
    document.body.style.overflow = '';
  };

  window.openEnterpriseModal  = openEnterpriseModal;
  window.closeEnterpriseModal = closeEnterpriseModal;

  // Backdrop click
  const backdrop = document.getElementById('eiModalBackdrop');
  if (backdrop) backdrop.addEventListener('click', closeEnterpriseModal);

  // Close button
  const closeBtn = document.getElementById('eiModalClose');
  if (closeBtn) closeBtn.addEventListener('click', closeEnterpriseModal);

  // Escape key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modal && modal.style.display !== 'none') closeEnterpriseModal();
  });

  // Wire "Talk to sales" anchor on pricing card
  document.querySelectorAll('a[href="#cta"]').forEach(function (el) {
    if (el.textContent.trim() === 'Talk to sales') {
      el.addEventListener('click', function (e) { e.preventDefault(); openEnterpriseModal(); });
    }
  });

  // Wire "Contact us for Enterprise pricing." span below pricing cards
  const enterpriseSpan = document.querySelector('span.text-indigo-300.underline');
  if (enterpriseSpan) {
    enterpriseSpan.style.cursor = 'pointer';
    enterpriseSpan.addEventListener('click', openEnterpriseModal);
  }

  const setStatus = function(type, msg) {
    if (!statusEl) return;
    statusEl.textContent = msg; // textContent — never innerHTML — prevents XSS
    if (!msg) { statusEl.style.display = 'none'; return; }
    statusEl.className = 'rounded-lg px-3 py-2 text-xs border ' + (
      type === 'success'
        ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
        : 'bg-red-950 text-red-300 border-red-800'
    );
    statusEl.style.display = 'block';
  };

  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      handleSubmit();
    });
  }

  const handleSubmit = async function() {
    const name      = (document.getElementById('eiName').value || '').trim();
    const email     = (document.getElementById('eiEmailInput').value || '').trim();
    const company   = (document.getElementById('eiCompany').value || '').trim();
    const phone     = (document.getElementById('eiPhone').value || '').trim();
    const employees = parseInt(document.getElementById('eiEmployees').value, 10) || null;
    const message   = (document.getElementById('eiMessage').value || '').trim();
    const website   = (document.getElementById('eiWebsite')?.value || '').trim();

    if (!name || !email || !email.includes('@')) {
      setStatus('error', 'Please enter your full name and a valid work email.');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending…';
    setStatus('', '');

    try {
      const r = await fetch('/api/v1/enterprise/inquiry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name:           name,
          email:          email,
          company:        company  || null,
          phone:          phone    || null,
          employee_count: employees,
          message:        message  || null,
          website:        website  || null,
        }),
      });
      const data = await r.json();
      if (r.ok) {
        form.reset();
        submitBtn.style.display = 'none';
        setStatus('success', 'Thank you — our team will be in touch within one business day.');
      } else {
        setStatus('error', data.error || 'Something went wrong. Please try again.');
      }
    } catch (_err) {
      setStatus('error', 'Unable to send. Please check your connection and try again.');
    } finally {
      submitBtn.disabled = false;
      if (submitBtn.style.display !== 'none') submitBtn.textContent = 'Send inquiry →';
    }
  }
});
