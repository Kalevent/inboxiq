(() => {
  const form = document.getElementById('activateForm');
  const statusEl = document.getElementById('activateStatus');
  const button = document.getElementById('activateButton');
  const tokenInput = document.getElementById('activationToken');
  const resendForm = document.getElementById('resendForm');
  const resendEmail = document.getElementById('resendEmail');
  const resendButton = document.getElementById('resendButton');
  const resendStatus = document.getElementById('resendStatus');

  const setStatus = function(type, message) {
    if (!statusEl) return;
    const colorMap = {
      success: 'border border-emerald-400 bg-emerald-50 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200',
      error: 'border border-rose-400 bg-rose-50 text-rose-800 dark:bg-rose-900/30 dark:text-rose-200',
      info: 'border border-indigo-300 bg-indigo-50 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-200',
    };
    statusEl.className = `mt-4 text-sm rounded-xl px-3 py-3 ${colorMap[type] || colorMap.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove('hidden');
  };

  const handleActivate = async function(event) {
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
      if (data.account_id !== undefined) localStorage.setItem('inboxiqAccountId', data.account_id);
      if (data.user_id !== undefined) localStorage.setItem('inboxiqUserId', data.user_id);

      if (data.mfa_setup_required) {
        setStatus('success', 'Account activated! Please set up two-factor authentication before continuing.');
        setTimeout(() => { window.location.href = '/settings/security?mfa_required=1'; }, 2000);
        return;
      }
      setStatus('success', 'Your account has been activated successfully. Welcome to InboxIQ! Taking you to your workspace…');
      setTimeout(() => { window.location.href = '/onboarding'; }, 2500);
    } catch (error) {
      setStatus('error', error.message || 'Activation failed.');
    } finally {
      button.disabled = false;
      button.textContent = 'Activate and Sign In';
    }
  };

  if (form) {
    form.addEventListener('submit', handleActivate);
  }

  const setResendStatus = function(type, message) {
    if (!resendStatus) return;
    const colorMap = {
      success: 'border border-emerald-400 bg-emerald-50 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200',
      error: 'border border-rose-400 bg-rose-50 text-rose-800 dark:bg-rose-900/30 dark:text-rose-200',
      info: 'border border-indigo-300 bg-indigo-50 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-200',
    };
    resendStatus.className = `text-sm rounded-xl px-3 py-3 ${colorMap[type] || colorMap.info}`;
    resendStatus.textContent = message;
    resendStatus.classList.remove('hidden');
  };

  const extractTokenFromLink = function(link) {
    try {
      const url = new URL(link);
      return url.searchParams.get('token');
    } catch (e) {
      return null;
    }
  };

  const handleResend = async function(event) {
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
      const response = await fetch('/auth/resend-activation', {  // route: /resend-activation on /auth blueprint
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
  };

  if (resendForm) {
    resendForm.addEventListener('submit', handleResend);
  }
})();
