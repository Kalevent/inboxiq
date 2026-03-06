(() => {
  const form = document.getElementById('loginForm');
  const button = document.getElementById('loginButton');
  const statusEl = document.getElementById('loginStatus');
  function clearFields() {
    if (form?.email) form.email.value = '';
    if (form?.password) form.password.value = '';
  }
  // Nudge browsers to drop any stale autofill (e.g., removed accounts).
  clearFields();

  function setStatus(type, message) {
    if (!statusEl) return;
    const colorMap = {
      success: 'text-emerald-200 bg-emerald-500/10 border-emerald-500/30',
      error: 'text-rose-200 bg-rose-500/10 border-rose-500/30',
      info: 'text-indigo-200 bg-indigo-500/10 border-indigo-500/30',
    };
    statusEl.className = `mt-4 text-sm px-3 py-3 rounded-xl border ${colorMap[type] || colorMap.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove('hidden');
  }

  async function handleLogin(event) {
    event.preventDefault();
    if (!form || !button) return;

    const email = (form.email?.value || '').trim().toLowerCase();
    const password = form.password?.value || '';
    if (!email || !password) {
      setStatus('error', 'Email and password are required.');
      return;
    }

    const payload = { email, password };

    button.disabled = true;
    button.textContent = 'Signing in...';
    setStatus('info', 'Validating your credentials...');

    try {
      const response = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include', // ensure auth cookies are stored
        body: JSON.stringify(payload),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Unable to log in right now.');
      }

      if (data.access_token) {
        localStorage.setItem('inboxiqAccessToken', data.access_token);
      }
      if (data.account_id !== undefined) {
        localStorage.setItem('inboxiqAccountId', data.account_id);
      }
      if (data.user_id !== undefined) {
        localStorage.setItem('inboxiqUserId', data.user_id);
      }

      setStatus('success', 'Signed in. Redirecting...');
      // Send users straight into guided setup/dashboard after login.
      window.location.href = '/dashboard';
    } catch (error) {
      setStatus('error', error.message || 'Login failed.');
    } finally {
      button.disabled = false;
      button.textContent = 'Sign in';
    }
  }

  if (form) {
    form.addEventListener('submit', handleLogin);
  }
})();
