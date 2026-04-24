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

  function calculateROI() {
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
  }

  const roiButton = document.getElementById('roiButton');
  if (roiButton) {
    roiButton.addEventListener('click', calculateROI);
  }

  function setCtaStatus(type, message, options = {}) {
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
  }

  async function handleCtaSubmit(event) {
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
  }

  if (ctaForm) {
    ctaForm.addEventListener('submit', handleCtaSubmit);
  }
})();

// ── Demo Gate ─────────────────────────────────────────────────────────────
(function () {
  var modal      = document.getElementById('demoGateModal');
  var form       = document.getElementById('demoGateForm');
  var emailInput = document.getElementById('demoGateEmail');
  var submitBtn  = document.getElementById('demoGateSubmit');
  var errorEl    = document.getElementById('demoGateError');
  var closeBtn   = document.getElementById('demoGateClose');

  if (!modal) return;

  var SESSION_KEY = 'demo_unlocked';

  // Video src: prefer data attribute on modal, fall back to known static path
  function playVideoInModal() {
    var src = modal.dataset.videoSrc || '/static/demo/InboxIQ.mp4';
    var poster = modal.dataset.posterSrc || '/static/demo/inboxiq-dashboard.png';
    var inner = modal.querySelector('div');
    // Expand modal panel to fit video
    inner.style.maxWidth = '860px';
    inner.innerHTML =
      '<button id="demoGateClose2" style="float:right;font-size:1.2rem;color:#94a3b8;background:none;border:none;cursor:pointer;margin-bottom:8px">✕</button>' +
      '<video src="' + src + '" poster="' + poster + '" controls autoplay playsinline muted' +
      ' style="width:100%;border-radius:12px;display:block"></video>';
    document.getElementById('demoGateClose2').addEventListener('click', function () {
      modal.style.display = 'none';
    });
  }

  // If already unlocked this session, open straight to video
  function openModal() {
    modal.style.display = 'flex';
    if (sessionStorage.getItem(SESSION_KEY)) {
      playVideoInModal();
    } else if (emailInput) {
      emailInput.focus();
    }
  }

  // Legacy play button (kept for backwards compat, may not exist)
  var playBtn = document.getElementById('demoPlayBtn');
  if (playBtn) playBtn.addEventListener('click', openModal);

  if (closeBtn) {
    closeBtn.addEventListener('click', function () { modal.style.display = 'none'; });
  }

  modal.addEventListener('click', function (e) {
    if (e.target === modal) modal.style.display = 'none';
  });

  if (form) {
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var email = (emailInput.value || '').trim().toLowerCase();
      if (!email) return;

      submitBtn.disabled = true;
      submitBtn.textContent = 'Just a sec...';
      errorEl.classList.add('hidden');

      try {
        var resp = await fetch('/api/v1/enterprise/inquiry', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ name: email, email: email, source: 'demo_gate' }),
        });
        if (!resp.ok) throw new Error('Request failed');
        sessionStorage.setItem(SESSION_KEY, '1');
        playVideoInModal();
      } catch (_) {
        errorEl.textContent = 'Something went wrong — please try again.';
        errorEl.classList.remove('hidden');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Watch demo →';
      }
    });
  }

  // Wire any "Watch 60s demo" buttons that open the modal directly
  document.querySelectorAll('[data-open-demo]').forEach(function (btn) {
    btn.addEventListener('click', openModal);
  });

  // Public opener — lets other sections trigger the gate with a custom video
  window._inboxiqOpenVideoModal = function (cfg) {
    if (cfg.videoSrc)  modal.dataset.videoSrc  = cfg.videoSrc;
    if (cfg.posterSrc) modal.dataset.posterSrc = cfg.posterSrc;
    var h3 = modal.querySelector('h3');
    if (h3) h3.textContent = cfg.title || 'Watch the 60-second demo';
    var p = modal.querySelector('div > p');
    if (p) p.textContent = cfg.subtitle || 'Enter your work email and the demo plays instantly.';
    openModal();
  };
})();

// ── Free Trial Modal ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  var tmModal    = document.getElementById('trialModal');
  var tmForm     = document.getElementById('tmForm');
  var tmStatus   = document.getElementById('tmStatus');
  var tmButton   = document.getElementById('tmButton');
  var tmEmail    = document.getElementById('tmEmail');
  var tmAccount  = document.getElementById('tmAccountName');
  var tmTrigger  = document.getElementById('trialModalTrigger');
  var tmClose    = document.getElementById('tmClose');
  var tmBackdrop = document.getElementById('tmBackdrop');

  function openTrialModal() {
    if (!tmModal) return;
    tmModal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    if (tmEmail) tmEmail.focus();
  }

  function closeTrialModal() {
    if (!tmModal) return;
    tmModal.style.display = 'none';
    document.body.style.overflow = '';
  }

  function setTmStatus(type, message) {
    if (!tmStatus) return;
    var cls = type === 'success'
      ? 'rounded-lg px-3 py-2 text-xs bg-emerald-900/60 border border-emerald-700 text-emerald-200'
      : type === 'error'
        ? 'rounded-lg px-3 py-2 text-xs bg-red-900/60 border border-red-700 text-red-200'
        : 'rounded-lg px-3 py-2 text-xs bg-slate-800 border border-slate-600 text-slate-300';
    tmStatus.className = cls;
    tmStatus.textContent = message;
    tmStatus.style.display = 'block';
  }

  async function handleTmSubmit(event) {
    event.preventDefault();
    if (!tmEmail || !tmButton) return;
    var email       = (tmEmail.value || '').trim().toLowerCase();
    var accountName = (tmAccount ? tmAccount.value || '' : '').trim();

    if (!email)       { setTmStatus('error', 'Please provide your work email.'); return; }
    if (!accountName) { setTmStatus('error', 'Please provide an account name.'); return; }

    tmButton.disabled = true;
    tmButton.textContent = 'Creating...';
    setTmStatus('info', 'Creating your workspace…');

    try {
      var response = await fetch('/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ email: email, account_name: accountName }),
      });
      var contentType = response.headers.get('content-type') || '';
      var isJson = contentType.includes('application/json');
      var data = isJson ? await response.json() : await response.text();
      if (!response.ok) {
        throw new Error((isJson && data && data.error) || data || ('Request failed (' + response.status + ')'));
      }
      if (isJson && data && data.account_id !== undefined) {
        localStorage.setItem('inboxiqAccountId', data.account_id);
      }
      var activationLink = isJson ? (data && data.activation_link) : null;
      if (activationLink) {
        try { localStorage.setItem('inboxiqActivationLink', activationLink); } catch (e) {}
      }
      var msg = 'Workspace created! Check ' + email + ' for your activation link.';
      if (activationLink) msg += ' Or open: ' + activationLink;
      setTmStatus('success', msg);
      tmButton.textContent = 'Done!';
    } catch (error) {
      setTmStatus('error', error.message || 'Unable to create workspace.');
      tmButton.disabled = false;
      tmButton.textContent = 'Start Free Trial →';
    }
  }

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
  var modal     = document.getElementById('enterpriseModal');
  var form      = document.getElementById('eiInquiryForm');
  var statusEl  = document.getElementById('eiFormStatus');
  var submitBtn = document.getElementById('eiSubmitBtn');

  function openEnterpriseModal() {
    if (!modal) return;
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    var first = document.getElementById('eiName');
    if (first) setTimeout(function () { first.focus(); }, 50);
  }

  function closeEnterpriseModal() {
    if (!modal) return;
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }

  window.openEnterpriseModal  = openEnterpriseModal;
  window.closeEnterpriseModal = closeEnterpriseModal;

  // Backdrop click
  var backdrop = document.getElementById('eiModalBackdrop');
  if (backdrop) backdrop.addEventListener('click', closeEnterpriseModal);

  // Close button
  var closeBtn = document.getElementById('eiModalClose');
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
  var enterpriseSpan = document.querySelector('span.text-indigo-300.underline');
  if (enterpriseSpan) {
    enterpriseSpan.style.cursor = 'pointer';
    enterpriseSpan.addEventListener('click', openEnterpriseModal);
  }

  function setStatus(type, msg) {
    if (!statusEl) return;
    statusEl.textContent = msg; // textContent — never innerHTML — prevents XSS
    if (!msg) { statusEl.style.display = 'none'; return; }
    statusEl.className = 'rounded-lg px-3 py-2 text-xs border ' + (
      type === 'success'
        ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
        : 'bg-red-950 text-red-300 border-red-800'
    );
    statusEl.style.display = 'block';
  }

  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      handleSubmit();
    });
  }

  async function handleSubmit() {
    var name      = (document.getElementById('eiName').value || '').trim();
    var email     = (document.getElementById('eiEmailInput').value || '').trim();
    var company   = (document.getElementById('eiCompany').value || '').trim();
    var phone     = (document.getElementById('eiPhone').value || '').trim();
    var employees = parseInt(document.getElementById('eiEmployees').value, 10) || null;
    var message   = (document.getElementById('eiMessage').value || '').trim();
    var website   = (document.getElementById('eiWebsite')?.value || '').trim();

    if (!name || !email || !email.includes('@')) {
      setStatus('error', 'Please enter your full name and a valid work email.');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending…';
    setStatus('', '');

    try {
      var r = await fetch('/api/v1/enterprise/inquiry', {
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
      var data = await r.json();
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
