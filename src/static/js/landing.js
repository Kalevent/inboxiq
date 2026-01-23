(() => {
  const emailsInput = document.getElementById('emailsPerMonth');
  const minutesInput = document.getElementById('minutesPerEmail');
  const hourlyInput = document.getElementById('hourlyRate');
  const resultsEl = document.getElementById('roiResults');
  const yearSpan = document.getElementById('yearSpan');
  const ctaForm = document.getElementById('ctaForm');
  const ctaButton = document.getElementById('ctaButton');
  const ctaStatus = document.getElementById('ctaStatus');
  const ctaEmail = document.getElementById('ctaEmail');
  const ctaAccountName = document.getElementById('ctaAccountName');
  const ctaSeats = document.getElementById('ctaSeats');
  const activationLinkStorageKey = 'inboxiqActivationLink';

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
    const emails = parseFloat(emailsInput?.value) || 2000;
    const minutesPerEmail = parseFloat(minutesInput?.value) || 2;
    const hourlyRate = parseFloat(hourlyInput?.value) || 20;
    const proPrice = 29;

    const minutesSavedPerEmail = minutesPerEmail * 0.8;
    const totalMinutesSaved = emails * minutesSavedPerEmail;
    const hoursSaved = totalMinutesSaved / 60;
    const costSaved = hoursSaved * hourlyRate;

    let paybackText;
    if (costSaved > 0) {
      const monthlyNet = costSaved - proPrice;
      const paybackDays = monthlyNet > 0 ? Math.max(1, Math.round(30 * (proPrice / costSaved))) : null;
      paybackText = paybackDays
        ? `InboxIQ typically pays for itself in about ${paybackDays} day${paybackDays === 1 ? '' : 's'} of use.`
        : 'With these inputs, InboxIQ nearly breaks even. Try increasing your email volume or hourly rate to see potential savings.';
    } else {
      paybackText = 'Please check your inputs—savings appear to be zero.';
    }

    if (resultsEl) {
      resultsEl.innerHTML = `
        <p><strong>Estimated hours saved per month:</strong> ${hoursSaved.toFixed(1)} hours</p>
        <p><strong>Estimated labour cost saved per month:</strong> £${costSaved.toFixed(0)}</p>
        <p><strong>Pro plan cost:</strong> £${proPrice}/month</p>
        <p>${paybackText}</p>
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
    const accountName = (ctaAccountName?.value || '').trim();
    const seatsRaw = (ctaSeats?.value || '').trim();
    const seats = seatsRaw ? parseInt(seatsRaw, 10) : Number.NaN;

    if (!email) {
      setCtaStatus('error', 'Please provide your work email.');
      return;
    }
    if (!accountName) {
      setCtaStatus('error', 'Please provide an account name.');
      return;
    }
    if (!seatsRaw || Number.isNaN(seats) || seats < 1) {
      setCtaStatus('error', 'Please enter how many seats you need (at least 1).');
      return;
    }

    ctaButton.disabled = true;
    ctaButton.textContent = 'Creating...';
    setCtaStatus('info', 'Creating your workspace and sending activation email...');

    try {
      const payload = { email, account_name: accountName, seats };
      const response = await fetch('/auth/signup', {
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
      if (isJson && data?.account_id !== undefined) {
        localStorage.setItem('inboxiqAccountId', data.account_id);
      }
      const activationInfo =
        isJson && data?.activation_link
          ? `Use the activation link sent to ${email} (or copy this for testing: ${data.activation_link}).`
          : `Check your email at ${email} for the activation link.`;
      const activationLink = isJson ? data?.activation_link : null;
      const baseMessage =
        isJson && data?.account_id !== undefined
          ? `Workspace created! ID ${data.account_id}.`
          : 'Workspace created!';
      setCtaStatus('success', `${baseMessage} ${activationInfo}`, {
        activationLink,
        helper: activationLink
          ? 'Link saved locally in case email delivery fails.'
          : 'If email delivery is slow, you can restart and we will generate a new link.',
        persistLink: !!activationLink,
      });
    } catch (error) {
      setCtaStatus('error', error.message || 'Unable to create workspace.');
    } finally {
      ctaButton.disabled = false;
      ctaButton.textContent = 'Start Free Trial →';
    }
  }

  // Show any saved activation link so users can recover without email.
  try {
    const savedLink = localStorage.getItem(activationLinkStorageKey);
    if (savedLink) {
      setCtaStatus('info', 'Resume your activation with your saved link.', {
        activationLink: savedLink,
        helper: 'This stays on your device only. Start a new signup to refresh it.',
      });
    }
  } catch (err) {
    // ignore storage issues
  }

  if (ctaForm) {
    ctaForm.addEventListener('submit', handleCtaSubmit);
  }
})();
