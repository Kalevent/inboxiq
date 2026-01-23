(() => {
  const form = document.getElementById('activateForm');
  const statusEl = document.getElementById('activateStatus');
  const button = document.getElementById('activateButton');
  const tokenInput = document.getElementById('activationToken');
  const resendForm = document.getElementById('resendForm');
  const resendEmail = document.getElementById('resendEmail');
  const resendButton = document.getElementById('resendButton');
  const resendStatus = document.getElementById('resendStatus');

  function setStatus(type, message) {
    if (!statusEl) return;
    const colorMap = {
      success: 'border-emerald-400 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400 bg-indigo-500/10 text-indigo-100',
    };
    statusEl.className = `mt-4 text-sm rounded-xl px-3 py-3 ${colorMap[type] || colorMap.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove('hidden');
  }

  async function handleActivate(event) {
    event.preventDefault();
    if (!form || !button || !tokenInput) return;

    const token = (tokenInput.value || '').trim();
    const password = (form.password?.value || '').trim();
    const confirm = (form.passwordConfirm?.value || '').trim();
    if (!token) {
      setStatus('error', 'Activation token is missing.');
      return;
    }
    if (!password || password.length < 8) {
      setStatus('error', 'Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setStatus('error', 'Passwords do not match.');
      return;
    }

    button.disabled = true;
    button.textContent = 'Activating...';
    setStatus('info', 'Activating your account...');

    try {
      const response = await fetch('/auth/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Unable to activate. Token may be invalid or expired.');
      }
      setStatus('success', 'Account activated! You are now signed in. You can close this tab and go to the app.');
      if (data.account_id !== undefined) {
        localStorage.setItem('inboxiqAccountId', data.account_id);
      }
    } catch (error) {
      setStatus('error', error.message || 'Activation failed.');
    } finally {
      button.disabled = false;
      button.textContent = 'Activate and Sign In';
    }
  }

  if (form) {
    form.addEventListener('submit', handleActivate);
  }

  function setResendStatus(type, message) {
    if (!resendStatus) return;
    const colorMap = {
      success: 'border-emerald-400 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400 bg-indigo-500/10 text-indigo-100',
    };
    resendStatus.className = `text-sm rounded-xl px-3 py-3 ${colorMap[type] || colorMap.info}`;
    resendStatus.textContent = message;
    resendStatus.classList.remove('hidden');
  }

  function extractTokenFromLink(link) {
    try {
      const url = new URL(link);
      return url.searchParams.get('token');
    } catch (e) {
      return null;
    }
  }

  async function handleResend(event) {
    event.preventDefault();
    if (!resendEmail || !resendButton) return;
    const email = (resendEmail.value || '').trim().toLowerCase();
    if (!email) {
      setResendStatus('error', 'Please enter your signup email.');
      return;
    }

    resendButton.disabled = true;
    resendButton.textContent = 'Sending...';
    setResendStatus('info', 'Sending a new activation link...');

    try {
      const response = await fetch('/auth/resend-activation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Unable to resend activation link.');
      }
      const token = data.activation_link ? extractTokenFromLink(data.activation_link) : null;
      if (token && tokenInput) {
        tokenInput.value = token;
        setStatus('info', 'New token applied. Set your password and activate.');
      }
      setResendStatus(
        'success',
        data.message || 'Activation link sent. Check your email (and spam) or use the new link.'
      );
    } catch (error) {
      setResendStatus('error', error.message || 'Unable to resend activation link.');
    } finally {
      resendButton.disabled = false;
      resendButton.textContent = 'Resend activation link';
    }
  }

  if (resendForm) {
    resendForm.addEventListener('submit', handleResend);
  }
})();
