(() => {
  const requestForm = document.getElementById('resetRequestForm');
  const requestButton = document.getElementById('resetRequestButton');
  const completeForm = document.getElementById('resetCompleteForm');
  const completeButton = document.getElementById('resetCompleteButton');
  const statusEl = document.getElementById('resetStatus');
  const tokenInput = document.getElementById('resetToken');
  const accountIdInput = document.getElementById('resetAccountId');

  // Autofill token from query string if present
  const params = new URLSearchParams(window.location.search);
  const tokenFromQuery = params.get('token');
  if (tokenFromQuery && tokenInput) {
    tokenInput.value = tokenFromQuery;
  }

  const setStatus = function(type, message) {
    if (!statusEl) return;
    const colorMap = {
      success: 'text-emerald-200 bg-emerald-500/10 border-emerald-500/30',
      error: 'text-rose-200 bg-rose-500/10 border-rose-500/30',
      info: 'text-indigo-200 bg-indigo-500/10 border-indigo-500/30',
    };
    statusEl.className = `mt-6 text-sm px-3 py-3 rounded-xl border ${colorMap[type] || colorMap.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove('hidden');
  };

  const handleRequest = async function(event) {
    event.preventDefault();
    if (!requestForm || !requestButton) return;
    const email = (requestForm.resetEmail?.value || '').trim().toLowerCase();
    const accountId = (accountIdInput?.value || '').trim();
    if (!email) {
      setStatus('error', 'Email is required.');
      return;
    }
    requestButton.disabled = true;
    requestButton.textContent = 'Sending...';
    setStatus('info', 'Sending reset link...');
    const payload = { email };
    if (accountId) payload.account_id = accountId;
    try {
      const resp = await fetch('/auth/reset/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || 'Unable to send reset link.');
      }
      setStatus('success', 'If the account exists, a reset link has been sent. Check your email.');
    } catch (err) {
      setStatus('error', err.message || 'Unable to send reset link.');
    } finally {
      requestButton.disabled = false;
      requestButton.textContent = 'Send reset link';
    }
  };

  const handleComplete = async function(event) {
    event.preventDefault();
    if (!completeForm || !completeButton) return;
    const token = (completeForm.resetToken?.value || '').trim();
    const password = completeForm.newPassword?.value || '';
    if (!token || !password) {
      setStatus('error', 'Token and new password are required.');
      return;
    }
    completeButton.disabled = true;
    completeButton.textContent = 'Resetting...';
    setStatus('info', 'Resetting your password...');
    try {
      const resp = await fetch('/auth/reset/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ token, password }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || 'Unable to reset password.');
      }
      if (data.account_id !== undefined) localStorage.setItem('inboxiqAccountId', data.account_id);
      if (data.user_id !== undefined) localStorage.setItem('inboxiqUserId', data.user_id);
      setStatus('success', 'Password reset. Redirecting to dashboard...');
      setTimeout(() => {
        window.location.href = '/dashboard';
      }, 800);
    } catch (err) {
      setStatus('error', err.message || 'Unable to reset password.');
    } finally {
      completeButton.disabled = false;
      completeButton.textContent = 'Reset password';
    }
  };

  if (requestForm) requestForm.addEventListener('submit', handleRequest);
  if (completeForm) completeForm.addEventListener('submit', handleComplete);
})();
